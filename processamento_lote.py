"""Lote com salvamento único por tentativa e diário persistente local.

Núcleo de referência com interface injetável para demonstração offline.
SALVO_NOTIFICACAO exige uma nova mensagem de sucesso e o fechamento do formulário.
SALVO_INTERFACE é preservado apenas para o histórico da versão anterior.
"""
import csv
import hashlib
import io
import json
import os
import sqlite3
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import configuracao_publica as config
import sys
from automacao import (
    abrir_formulario_lancamento, criar_navegador, preencher_campos_basicos,
)
from leitor_csv import COLUNAS_OBRIGATORIAS, converter_linha, validar_colunas
from acesso_sistema import entrar_no_extrato
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


COLUNAS_LOG = (
    "registro", "linha_csv_inicio", "linha_csv_fim", "id_original", "tipo",
    "descricao", "valor", "data", "status", "etapa", "tipo_erro", "mensagem",
    "atualizado_em",
)
IGNORAR_REINICIO = {
    "SALVO_INTERFACE", "SALVO_NOTIFICACAO", "VERIFICAR_NO_EXTRATO", "ERRO", "ERRO_LEITURA",
    "INTERROMPIDO_ANTES_DE_SALVAR",
}


def agora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def preparar_leitor_csv(texto, caminho):
    """Detecta o delimitador pelo cabeçalho, sem usar os valores financeiros."""
    fluxo = io.StringIO(texto, newline="")
    deslocamento = 0
    separador_declarado = None
    while True:
        posicao = fluxo.tell()
        linha = fluxo.readline()
        if not linha:
            raise ValueError(f"CSV vazio ou sem cabeçalho: {caminho}")
        if not linha.strip():
            deslocamento += 1
            continue
        if linha.strip().lower().startswith("sep="):
            if separador_declarado is not None:
                raise ValueError("O CSV possui mais de uma declaração sep=.")
            separador_declarado = linha.lstrip().rstrip("\r\n")[4:]
            if separador_declarado not in (",", ";", "\t", "|"):
                raise ValueError(f"Separador declarado não suportado: {separador_declarado!r}")
            deslocamento += 1
            continue
        fluxo.seek(posicao)
        break
    inicio_cabecalho = fluxo.tell()
    candidatos = []
    for separador in ([separador_declarado] if separador_declarado else [",", ";", "\t", "|"]):
        fluxo.seek(inicio_cabecalho)
        try:
            cabecalho = next(csv.reader(fluxo, delimiter=separador,
                                       skipinitialspace=True, strict=True))
        except (csv.Error, StopIteration):
            continue
        cabecalho = [coluna.strip() for coluna in cabecalho]
        acertos = len(set(cabecalho) & COLUNAS_OBRIGATORIAS)
        candidatos.append((acertos, separador, cabecalho))
    if not candidatos or max(c[0] for c in candidatos) == 0:
        fluxo.seek(inicio_cabecalho)
        amostra = fluxo.readline().strip()[:400]
        raise ValueError(
            f"Nenhuma coluna financeira reconhecida no cabeçalho de {caminho}. "
            f"Cabeçalho encontrado (até 400 caracteres): {amostra!r}. "
            "Confira CAMINHO_CSV: selecione o relatório financeiro original, "
            "com id, Tipo, Valor, Descrição e as demais colunas; não um arquivo de log."
        )
    maior = max(c[0] for c in candidatos)
    melhores = [c for c in candidatos if c[0] == maior]
    if len(melhores) != 1:
        raise ValueError("Separador do CSV ambíguo. Exporte novamente com vírgula ou ponto e vírgula.")
    _, separador, cabecalho = melhores[0]
    if len(set(cabecalho)) != len(cabecalho):
        raise ValueError("O CSV possui nomes de colunas duplicados após remover espaços nas extremidades.")
    try:
        validar_colunas(cabecalho)
    except ValueError as erro:
        raise ValueError(
            f"{erro} | Separador detectado: {separador!r}. "
            f"Colunas encontradas: {cabecalho!r}. Arquivo: {caminho}"
        ) from erro
    fluxo.seek(inicio_cabecalho)
    leitor = csv.DictReader(fluxo, delimiter=separador, skipinitialspace=True, strict=True)
    # Lê o cabeçalho original para preservar a numeração física e normaliza só
    # seus nomes; os valores e o conteúdo do arquivo não são reescritos.
    _ = leitor.fieldnames
    leitor.fieldnames = cabecalho
    print(f"Separador do CSV detectado: {separador!r} | Colunas: {len(cabecalho)}")
    return leitor, deslocamento


def carregar_registros(caminho):
    # Uma cópia estável: mudanças no arquivo durante o lote não trocam os dados.
    conteudo = Path(caminho).read_bytes()
    assinatura = hashlib.sha256(conteudo).hexdigest()
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as erro:
        raise ValueError(
            "O CSV não está em UTF-8. Exporte como CSV UTF-8 e confira CAMINHO_CSV."
        ) from erro
    leitor, deslocamento = preparar_leitor_csv(texto, caminho)
    registros = []
    while True:
        inicio = leitor.line_num + 1 + deslocamento
        try:
            linha = next(leitor)
        except StopIteration:
            break
        # CSV estruturalmente quebrado interrompe antes de abrir o navegador:
        # não é seguro adivinhar onde começa a próxima linha nesse caso.
        registros.append({
            "registro": len(registros) + 1,
            "linha_csv_inicio": inicio,
            "linha_csv_fim": leitor.line_num + deslocamento,
            "dados": linha,
        })
    if not registros:
        raise ValueError("O CSV não possui lançamentos.")
    return assinatura, registros


class Diario:
    def __init__(self, pasta, registros):
        pasta.mkdir(parents=True, exist_ok=True)
        self.pasta = pasta
        self.con = sqlite3.connect(pasta / "progresso.sqlite3")
        self.con.execute("PRAGMA synchronous=FULL")
        self.con.execute("""CREATE TABLE IF NOT EXISTS resultados (
            registro INTEGER PRIMARY KEY, conteudo TEXT NOT NULL
        )""")
        with self.con:
            for item in registros:
                d = item["dados"]
                r = {k: "" for k in COLUNAS_LOG}
                r.update({k: item[k] for k in ("registro", "linha_csv_inicio", "linha_csv_fim")})
                r.update(id_original=d.get("id") or "", tipo=d.get("Tipo") or "",
                         descricao=d.get("Descrição") or "", valor=d.get("Valor") or "",
                         data=d.get("Data") or "", status="NAO_PROCESSADO", atualizado_em=agora())
                self.con.execute("INSERT OR IGNORE INTO resultados VALUES (?, ?)",
                                 (item["registro"], json.dumps(r, ensure_ascii=False)))
        # Uma tentativa interrompida após o marco durável de salvar é incerta.
        for r in self.todos():
            if r["status"] in ("SALVANDO", "EM_PROCESSAMENTO"):
                status = ("VERIFICAR_NO_EXTRATO" if r["status"] == "SALVANDO"
                          else "INTERROMPIDO_ANTES_DE_SALVAR")
                self.registrar(r["registro"], status, "Retomada", "InterrupcaoAnterior",
                               "Execução anterior interrompida. Não será reenviado automaticamente.")
        self.exportar()

    def obter(self, numero):
        row = self.con.execute("SELECT conteudo FROM resultados WHERE registro=?", (numero,)).fetchone()
        return json.loads(row[0])

    def todos(self):
        return [json.loads(row[0]) for row in self.con.execute(
            "SELECT conteudo FROM resultados ORDER BY registro")]

    def registrar(self, numero, status, etapa="", tipo_erro="", mensagem=""):
        r = self.obter(numero)
        r.update(status=status, etapa=etapa, tipo_erro=tipo_erro,
                 mensagem=mensagem, atualizado_em=agora())
        with self.con:
            self.con.execute("UPDATE resultados SET conteudo=? WHERE registro=?",
                             (json.dumps(r, ensure_ascii=False), numero))
        caminho = self.pasta / "eventos.csv"
        novo = not caminho.exists() or caminho.stat().st_size == 0
        with caminho.open("a", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_LOG, delimiter=";")
            if novo:
                escritor.writeheader()
            escritor.writerow({k: ("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@"))
                                   else v) for k, v in r.items()})
            arquivo.flush()
            os.fsync(arquivo.fileno())

    def exportar(self):
        resultados = self.todos()
        for nome, linhas in (
            ("resultados.csv", resultados),
            ("pendencias.csv", [r for r in resultados if r["status"] not in
                                ("SALVO_INTERFACE", "SALVO_NOTIFICACAO", "TESTE_SEM_SALVAR")]),
        ):
            temporario = self.pasta / (nome + ".tmp")
            with temporario.open("w", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_LOG, delimiter=";")
                escritor.writeheader()
                for r in linhas:
                    # Evita executar conteúdo do CSV como fórmula ao abrir no Excel.
                    seguro = {k: ("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@"))
                                  else v) for k, v in r.items()}
                    escritor.writerow(seguro)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self.pasta / nome)

    def fechar(self):
        self.con.close()


def espera(driver):
    return WebDriverWait(driver, max(30, config.TEMPO_ESPERA),
                         ignored_exceptions=(StaleElementReferenceException,))


def extrato_pronto(driver):
    url = urlsplit(driver.current_url)
    if (url.scheme, url.netloc, url.path.rstrip("/")) != (
        "https", "example.invalid", "/demonstracao/extrato"
    ):
        return False
    return all(any(e.is_displayed() and e.is_enabled()
                   for e in driver.find_elements(By.ID, identificador))
               for identificador in (config.ID_BOTAO_NOVA_RECEITA, config.ID_BOTAO_NOVA_DESPESA))


def formularios_financeiros(driver):
    return [form for form in driver.find_elements(By.TAG_NAME, "form")
            if form.is_displayed()
            and any(e.is_displayed() for e in form.find_elements(
                By.CSS_SELECTOR, f'input[name="{config.CAMPO_VALOR}"]'))
            and form.find_elements(By.NAME, config.CAMPO_DESCRICAO)]


def preparar_salvamento(driver):
    def localizar(d):
        forms = formularios_financeiros(d)
        if len(forms) > 1:
            raise ValueError("Mais de um formulário financeiro visível. Salvamento cancelado.")
        if not forms:
            return False
        form = forms[0]
        botoes = [b for b in form.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                  if b.is_displayed() and b.is_enabled()
                  and " ".join(b.text.split()).upper() == "SALVAR"]
        if len(botoes) > 1:
            raise ValueError("Mais de um botão SALVAR visível no formulário.")
        return (form, botoes[0]) if botoes else False
    form, botao = espera(driver).until(localizar, "Botão SALVAR não encontrado no formulário ativo.")
    # Não dispara submissão: verifica apenas validações nativas do formulário.
    problemas = driver.execute_script("""
        return Array.from(arguments[0].elements)
            .filter(e => e.willValidate && e.validity && !e.validity.valid)
            .map(e => (e.name || e.id || 'campo') + ': ' + e.validationMessage);
    """, form)
    if problemas:
        raise ValueError("Validação do formulário: " + " | ".join(problemas))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", botao)
    return form, botao


# Executado antes do clique. Guarda notificações mesmo que sumam entre polls.
SCRIPT_OBSERVAR_NOTIFICACOES = r"""
const chave = '__demoLoteNotificacoes';
if (window[chave]?.observer) window[chave].observer.disconnect();
const raiz = document.querySelector('.demo-notifications');
if (!raiz) throw new Error('Área .demo-notifications não encontrada antes de Salvar.');
const antigas = new WeakSet();
const idsAntigos = new Set();
raiz.querySelectorAll('.notification').forEach(el => {
    antigas.add(el);
    const id = el.getAttribute('data-reactid');
    if (id) idsAntigos.add(id);
});
const vistos = new WeakMap();
const estado = { eventos: [], excesso: false, raiz, observer: null };
window[chave] = estado;
const normalizar = t => (t || '').replace(/\s+/g, ' ').trim();
function capturar(el) {
    if (!el || el.nodeType !== 1 || !el.matches('.notification')) return;
    const id = el.getAttribute('data-reactid') || '';
    if (antigas.has(el) || (id && idsAntigos.has(id))) return;
    const titulo = normalizar(el.querySelector('.notification-title')?.textContent);
    const mensagem = normalizar(el.querySelector('.notification-message')?.textContent);
    if (!titulo || !mensagem) return;
    const assinatura = titulo + '\n' + mensagem;
    let assinaturas = vistos.get(el);
    if (!assinaturas) { assinaturas = new Set(); vistos.set(el, assinaturas); }
    if (assinaturas.has(assinatura)) return;
    assinaturas.add(assinatura);
    if (estado.eventos.length >= 100) { estado.excesso = true; return; }
    estado.eventos.push({ titulo, mensagem, id });
}
function examinar(no) {
    const el = no?.nodeType === 1 ? no : no?.parentElement;
    if (!el) return;
    capturar(el.closest?.('.notification'));
    el.querySelectorAll?.('.notification').forEach(capturar);
}
estado.observer = new MutationObserver(mudancas => {
    // Os nós removidos também são inspecionados: a mensagem pode durar menos
    // que o intervalo de consulta do Selenium. Tudo vem da raiz observada.
    for (const m of mudancas) {
        examinar(m.target);
        m.addedNodes.forEach(examinar);
        m.removedNodes.forEach(examinar);
    }
    examinar(raiz);
});
estado.observer.observe(raiz, { childList: true, subtree: true, characterData: true });
return true;
"""

SCRIPT_LER_NOTIFICACOES = r"""
const estado = window.__demoLoteNotificacoes;
if (!estado || !estado.raiz.isConnected) return null;
return { eventos: estado.eventos, excesso: estado.excesso };
"""


def observar_notificacoes(driver):
    driver.execute_script(SCRIPT_OBSERVAR_NOTIFICACOES)


def encerrar_observador(driver):
    # Não encobre o resultado financeiro com erro de limpeza após navegação.
    try:
        driver.execute_script("""
            window.__demoLoteNotificacoes?.observer?.disconnect();
            delete window.__demoLoteNotificacoes;
        """)
    except Exception:
        pass


class NotificacaoFinanceiraInesperada(RuntimeError):
    pass


def mensagem_de_sucesso(estado):
    if estado is None:
        raise RuntimeError("Monitor de notificações perdido. Verifique o lançamento no extrato.")
    if estado.get("excesso"):
        raise RuntimeError("Excesso de notificações; confirmação interrompida para conferência.")
    financeiras = [e for e in estado.get("eventos", [])
                   if e.get("titulo", "").strip().casefold() == "finanças"]
    for evento in financeiras:
        if evento.get("mensagem", "").strip() != "Transação salva com sucesso.":
            # Ainda não temos o HTML de erros. Preserva o texto sem presumir
            # que uma notificação desconhecida significa sucesso ou rejeição.
            raise NotificacaoFinanceiraInesperada(
                "Nova notificação de Finanças: " + evento.get("mensagem", "")
            )
    return bool(financeiras)


def confirmar_salvamento(driver, form):
    def concluido(d):
        sucesso = mensagem_de_sucesso(d.execute_script(SCRIPT_LER_NOTIFICACOES))
        if not sucesso:
            return False
        try:
            if form.is_displayed():
                return False
        except StaleElementReferenceException:
            pass
        return extrato_pronto(d) and not formularios_financeiros(d)
    espera(driver).until(
        concluido,
        'Não foi possível confirmar uma NOVA notificação "Transação salva com sucesso." '
        "junto com o fechamento do formulário e a disponibilidade do extrato."
    )

def tela_login_visivel(driver):
    url = urlsplit(driver.current_url)
    if (url.scheme, url.netloc) != ("https", "example.invalid"):
        return False
    return all(any(e.is_displayed() for e in driver.find_elements(By.CSS_SELECTOR, seletor))
               for seletor in ('input[type="email"][name="email"]',
                               'input[type="password"][name="password"]'))


def recuperar(driver):
    # Equivalente ao F5. Não envia o usuário para a página de login sem necessidade.
    driver.refresh()
    def identificar_estado(d):
        if extrato_pronto(d):
            return "extrato"
        if tela_login_visivel(d):
            return "login"
        return False
    estado = espera(driver).until(
        identificar_estado,
        "Após recarregar, não foi identificado o extrato nem a tela de login. "
        "A recuperação foi interrompida sem tentar autenticar novamente."
    )
    if estado == "login":
        print("Tela de login detectada após recarregar. Autenticando novamente...")
        entrar_no_extrato(driver)
        espera(driver).until(extrato_pronto, "O extrato não ficou disponível após autenticar.")
    else:
        print("Página recarregada. Sessão ativa; continuando sem refazer o login.")
    espera(driver).until(lambda d: not formularios_financeiros(d),
                        "O formulário anterior permaneceu aberto após recarregar.")


def registrar_trace(pasta, numero):
    with (pasta / "detalhes_tecnicos.txt").open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"\n{agora()} | Registro {numero}\n{traceback.format_exc()}\n")
        arquivo.flush()
        os.fsync(arquivo.fileno())


def processar(registros, diario, navegador, modo_teste, interface=None):
    """Executa o lote; a demo injeta uma interface inteiramente em memória."""
    interface = interface if interface is not None else sys.modules[__name__]
    precisa_recuperar = False
    for item in registros:
        numero = item["registro"]
        if diario.obter(numero)["status"] in IGNORAR_REINICIO:
            print(f"Registro {numero}: já registrado no histórico; ignorado.")
            continue
        # Não segue interagindo se o F5/login não puder restabelecer o extrato.
        if precisa_recuperar:
            try:
                interface.recuperar(navegador)
                precisa_recuperar = False
            except Exception as erro:
                diario.registrar(numero, "NAO_PROCESSADO", "Recuperar o extrato",
                                  type(erro).__name__, str(erro))
                registrar_trace(diario.pasta, numero)
                print("Não foi possível interface.recuperar o navegador. Restantes constam como NAO_PROCESSADO.")
                return 1
        etapa = "Converter a linha do CSV"
        try:
            dados = item["dados"]
            if None in dados or any(v is None for v in dados.values()):
                raise ValueError("Quantidade de campos diferente do cabeçalho do CSV.")
            lancamento = converter_linha(dados)
            if not lancamento.valor.is_finite():
                raise ValueError("Valor precisa ser um número financeiro finito.")
        except Exception as erro:
            diario.registrar(numero, "ERRO_LEITURA", etapa, type(erro).__name__, str(erro))
            registrar_trace(diario.pasta, numero)
            print(f"Registro {numero}: ERRO_LEITURA — {erro}")
            # Nenhum formulário foi aberto: não há estado da tela para limpar.
            continue

        diario.registrar(numero, "EM_PROCESSAMENTO", "Abrir formulário")
        try:
            etapa = "Abrir formulário de " + lancamento.tipo
            print(f"\nRegistro {numero} | Linha {item['linha_csv_inicio']} | {lancamento.tipo}")
            interface.espera(navegador).until(interface.extrato_pronto, "Extrato não está pronto para o próximo lançamento.")
            interface.abrir_formulario_lancamento(navegador, lancamento.tipo)
            etapa = "Preencher campos"
            interface.preencher_campos_basicos(navegador, lancamento)
            etapa = "Localizar e validar Salvar"
            form, botao = interface.preparar_salvamento(navegador)
            if not modo_teste:
                etapa = "Preparar captura de notificações"
                interface.observar_notificacoes(navegador)
        except Exception as erro:
            diario.registrar(numero, "ERRO", etapa, type(erro).__name__, str(erro))
            registrar_trace(diario.pasta, numero)
            print(f"Registro {numero}: ERRO em {etapa} — {type(erro).__name__}: {erro}")
            precisa_recuperar = True
            continue

        if modo_teste:
            diario.registrar(numero, "TESTE_SEM_SALVAR", "Preenchimento concluído",
                              mensagem="Botão Salvar localizado; nenhum clique de salvamento realizado.")
            precisa_recuperar = True
            continue

        # Se o diário não puder ser gravado, para ANTES de clicar em Salvar.
        diario.registrar(numero, "SALVANDO", "Enviar salvamento",
                          mensagem="Tentativa iniciada; se interromper, verificar no extrato.")
        try:
            etapa = "Clicar em Salvar"
            botao.click()  # Uma única tentativa. Não há retry de salvamento.
            etapa = "Confirmar notificação de sucesso e fechamento"
            interface.confirmar_salvamento(navegador, form)
        except Exception as erro:
            diario.registrar(numero, "VERIFICAR_NO_EXTRATO", etapa,
                              type(erro).__name__, str(erro) or "Confirmação de salvamento ausente.")
            registrar_trace(diario.pasta, numero)
            print(f"Registro {numero}: VERIFICAR_NO_EXTRATO — {type(erro).__name__}: {erro}")
            precisa_recuperar = True
            continue
        finally:
            interface.encerrar_observador(navegador)
        diario.registrar(numero, "SALVO_NOTIFICACAO", etapa,
                          mensagem="Nova notificação: Transação salva com sucesso. Formulário fechou e extrato disponível.")
        print(f"Registro {numero}: SALVO_NOTIFICACAO")
    return 0


def liberar_erros_leitura(diario):
    quantidade = 0
    for r in diario.todos():
        if r["status"] == "ERRO_LEITURA":
            diario.registrar(r["registro"], "NAO_PROCESSADO", "Repetição de erro de leitura",
                              mensagem="Nova tentativa solicitada; o erro anterior permanece em eventos.csv.")
            quantidade += 1
    print(f"Erros de leitura liberados para nova tentativa: {quantidade}")
    return quantidade


def liberar_registro(diario, numero):
    resultado = next((r for r in diario.todos() if r["registro"] == numero), None)
    if resultado is None:
        raise ValueError(f"Registro {numero} não encontrado no histórico deste lote.")
    if resultado["status"] not in ("ERRO", "ERRO_LEITURA"):
        raise ValueError(
            f"Registro {numero} está com status {resultado['status']}. "
            "A repetição individual só aceita ERRO ou ERRO_LEITURA anteriores ao clique em Salvar."
        )
    diario.registrar(numero, "NAO_PROCESSADO", "Repetição individual",
                      mensagem="Nova tentativa solicitada para este registro. Histórico anterior preservado.")


def executar(repetir_erros_leitura=False, repetir_registro=None):
    if repetir_erros_leitura and repetir_registro is not None:
        raise ValueError("Use somente uma opção de repetição por execução.")
    assinatura, registros = carregar_registros(config.CAMINHO_CSV)
    modo_teste = config.MODO_TESTE
    if not isinstance(modo_teste, bool):
        raise ValueError("MODO_TESTE deve ser True ou False, sem aspas.")
    if modo_teste:
        limite = getattr(config, "LIMITE_REGISTROS", 1)
        if not isinstance(limite, int) or isinstance(limite, bool) or limite < 1:
            raise ValueError("LIMITE_REGISTROS deve ser um inteiro maior que zero para teste.")
        registros = registros[:limite]
    registros_execucao = registros
    if repetir_registro is not None:
        registros_execucao = [r for r in registros if r["registro"] == repetir_registro]
        if not registros_execucao:
            raise ValueError(f"Registro {repetir_registro} não existe entre os registros selecionados do CSV.")
    raiz = Path(__file__).resolve().parent / "logs"
    modo = "teste" if modo_teste else "gravacao"
    pasta = raiz / f"{modo}_{assinatura}"
    if (repetir_erros_leitura or repetir_registro is not None) and not (pasta / "progresso.sqlite3").is_file():
        raise ValueError("O histórico deste CSV não foi encontrado. Repetição cancelada sem criar um lote novo.")
    print(f"Modo: {'TESTE SEM SALVAR' if modo_teste else 'SALVAMENTO REAL'}")
    print(f"Registros selecionados: {len(registros_execucao)}")
    print(f"Logs: {pasta}")
    raiz.mkdir(parents=True, exist_ok=True)
    # Trava de processo liberada pelo SO mesmo em encerramento abrupto.
    # Global ao projeto: não permite duas execuções simultâneas, mesmo com CSVs diferentes.
    with (raiz / "execucao.lock").open("a+b") as trava:
        trava.seek(0, os.SEEK_END)
        if trava.tell() == 0:
            trava.write(b"0")
            trava.flush()
        trava.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(trava.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Já existe uma execução em andamento neste projeto.") from None
        diario = Diario(pasta, registros)
        try:
            if repetir_erros_leitura:
                numeros_erros = {r["registro"] for r in diario.todos() if r["status"] == "ERRO_LEITURA"}
                registros_execucao = [r for r in registros_execucao if r["registro"] in numeros_erros]
                liberar_erros_leitura(diario)
                print(f"Somente erros de leitura selecionados: {len(registros_execucao)}")
            if repetir_registro is not None:
                liberar_registro(diario, repetir_registro)
            if all(diario.obter(r["registro"])["status"] in IGNORAR_REINICIO for r in registros_execucao):
                print("Todos os registros já possuem resultado. Nenhum será reenviado.")
                codigo = 0
            else:
                navegador = criar_navegador()
                navegador.set_page_load_timeout(60)
                entrar_no_extrato(navegador)
                codigo = processar(registros_execucao, diario, navegador, modo_teste)
            contagem = Counter(r["status"] for r in diario.todos())
            print("\nRESUMO:")
            for status, quantidade in sorted(contagem.items()):
                print(f"  {status}: {quantidade}")
            if any(status not in ("SALVO_INTERFACE", "SALVO_NOTIFICACAO", "TESTE_SEM_SALVAR") for status in contagem):
                codigo = 1
            return codigo
        except BaseException:
            # O diário já contém todos os registros, incluindo os ainda não iniciados.
            registrar_trace(pasta, "execucao")
            raise
        finally:
            try:
                diario.exportar()
            finally:
                diario.fechar()
                print(f"\nResultados: {pasta / 'resultados.csv'}")
                print(f"Pendências: {pasta / 'pendencias.csv'}")

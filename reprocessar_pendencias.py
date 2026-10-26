"""Reprocessa exclusivamente erros listados no relatório de pendências indicado."""
import csv
import io
import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import processamento_lote as lote

ELEGIVEIS = {"ERRO", "ERRO_LEITURA"}
# O relatório de erros fornecido delimita a fila. NAO_PROCESSADO no diário
# atual não invalida esse erro de origem; sucessos e tentativas incertas bloqueiam.
HISTORICO_PERMITE_RELATORIO = ELEGIVEIS | {"NAO_PROCESSADO"}
CAMPOS_CONFERENCIA = {
    "id_original": "id", "tipo": "Tipo", "descricao": "Descrição",
    "valor": "Valor", "data": "Data",
}


def ler_relatorio(conteudo):
    texto = conteudo.decode("utf-8-sig")
    candidatos = []
    obrigatorias = {"linha_csv_inicio", "status", *CAMPOS_CONFERENCIA}
    for separador in (";", ",", "\t", "|"):
        stream = io.StringIO(texto, newline="")
        primeiro = stream.readline()
        if not primeiro.strip().lower().startswith("sep="):
            stream.seek(0)
        leitor = csv.DictReader(stream, delimiter=separador, strict=True)
        try:
            cabecalho = leitor.fieldnames or []
        except csv.Error:
            continue
        cabecalho = [c.strip() for c in cabecalho]
        if obrigatorias <= set(cabecalho):
            if len(set(cabecalho)) != len(cabecalho):
                raise ValueError("Relatório com colunas duplicadas.")
            leitor.fieldnames = cabecalho
            candidatos.append(list(leitor))
    if len(candidatos) != 1:
        raise ValueError("Informe o pendencias.csv gerado pelo programa, com linha_csv_inicio, status, ID e dados originais.")
    for r in candidatos[0]:
        if None in r or any(v is None for v in r.values()):
            raise ValueError("Relatório de pendências com quantidade incorreta de campos.")
    return candidatos[0]


def conferir_campos(item, referencia, origem):
    for campo_log, campo_csv in CAMPOS_CONFERENCIA.items():
        esperado = str(item["dados"].get(campo_csv) or "").strip()
        protegido = "'" + esperado if esperado.lstrip().startswith(("=", "+", "-", "@")) else esperado
        recebido = str(referencia.get(campo_log) or "").strip()
        if recebido not in (esperado, protegido):
            raise ValueError(
                f"Linha CSV {item['linha_csv_inicio']}: {campo_log} não coincide com {origem}. "
                "Este registro não será enviado. Confira os dados desta movimentação."
            )


def selecionar_pendencias(relatorio, registros, historico):
    # IDs são texto: preservar zeros iniciais e não converter para número.
    por_id = {}
    for item in registros:
        identidade = str(item["dados"].get("id") or "").strip()
        if identidade:
            # O relatório pode conter apóstrofo de proteção para Excel.
            chaves = {identidade}
            if identidade.startswith(("=", "+", "-", "@")):
                chaves.add("'" + identidade)
            for chave in chaves:
                por_id.setdefault(chave, []).append(item)
    historico_por_id = {}
    for numero, anterior in historico.items():
        identidade = str(anterior.get("id_original") or "").strip()
        historico_por_id.setdefault(identidade, []).append((numero, anterior))
    selecionados, decisoes, vistos = [], [], set()
    for posicao, r in enumerate(relatorio, 1):
        status = r.get("status", "").strip()
        identidade = str(r.get("id_original") or "").strip()
        decisao = {
            "posicao_relatorio": posicao,
            "linha_csv_inicio": r.get("linha_csv_inicio", ""),
            "linha_csv_atual": "", "registro": "", "id_original": identidade,
            "status_relatorio": status, "status_historico": "", "decisao": "",
        }
        decisoes.append(decisao)
        if status not in ELEGIVEIS:
            decisao["decisao"] = "IGNORADO: não é ERRO nem ERRO_LEITURA"
            continue
        candidatos = por_id.get(identidade, [])
        if not identidade or not candidatos:
            decisao["decisao"] = "PENDENTE: ID vazio ou ausente no CSV atual"
            continue
        if len(candidatos) != 1:
            decisao["decisao"] = "PENDENTE: ID duplicado no CSV atual"
            continue
        item = candidatos[0]
        decisao.update(registro=item["registro"], linha_csv_atual=item["linha_csv_inicio"])
        try:
            conferir_campos(item, r, "o relatório de pendências")
        except ValueError as erro:
            decisao["decisao"] = "PENDENTE: " + str(erro)
            continue
        id_csv = str(item["dados"].get("id") or "").strip()
        anteriores = historico_por_id.get(id_csv, [])
        if len(anteriores) != 1:
            decisao["decisao"] = "PENDENTE: ID ausente ou duplicado no histórico atual"
            continue
        numero, anterior = anteriores[0]
        decisao["status_historico"] = anterior.get("status", "")
        # O diário grava por ordinal; validar esse vínculo antes de qualquer escrita.
        if numero != item["registro"] or str(anterior.get("linha_csv_inicio")) != str(item["linha_csv_inicio"]):
            decisao["decisao"] = "PENDENTE: posição do registro diverge do histórico atual"
            continue
        try:
            conferir_campos(item, anterior, "o histórico")
        except ValueError as erro:
            decisao["decisao"] = "PENDENTE: " + str(erro)
            continue
        if anterior.get("status") not in HISTORICO_PERMITE_RELATORIO:
            decisao["decisao"] = "IGNORADO: histórico atual não autoriza repetir (salvo, incerto ou outro status)"
        elif item["registro"] in vistos:
            decisao["decisao"] = "IGNORADO: ID repetido no relatório"
        else:
            vistos.add(item["registro"])
            selecionados.append(item)
            decisao["decisao"] = "SELECIONADO"
    return sorted(selecionados, key=lambda r: r["linha_csv_inicio"]), decisoes


@contextmanager
def travar(raiz):
    raiz.mkdir(parents=True, exist_ok=True)
    with (raiz / "execucao.lock").open("a+b") as arquivo:
        arquivo.seek(0, os.SEEK_END)
        if arquivo.tell() == 0:
            arquivo.write(b"0"); arquivo.flush()
        arquivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Já existe uma execução ativa neste projeto.") from None
        yield


def executar_pendencias(caminho_relatorio, somente_conferir=False):
    assinatura, registros = lote.carregar_registros(lote.config.CAMINHO_CSV)
    caminho_relatorio = Path(caminho_relatorio).expanduser().resolve()
    # Lê tudo antes de Diario exportar novamente o pendencias.csv do lote.
    conteudo_relatorio = caminho_relatorio.read_bytes()
    relatorio = ler_relatorio(conteudo_relatorio)
    raiz = Path(lote.__file__).resolve().parent / "logs"
    pasta = raiz / f"gravacao_{assinatura}"
    banco = pasta / "progresso.sqlite3"
    if not banco.is_file():
        raise ValueError(
            "O histórico de gravação deste CSV não foi encontrado. O reprocessamento foi interrompido, "
            "sem criar um lote novo. Preserve/restaure os logs e use o CSV original sem alterações."
        )
    if not somente_conferir and lote.config.MODO_TESTE is not False:
        raise ValueError("Use --conferir-pendencias para conferir sem gravar, ou MODO_TESTE=False para reprocessar.")
    with travar(raiz):
        con = sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            historico = {n: json.loads(texto) for n, texto in con.execute("SELECT registro, conteudo FROM resultados")}
        finally:
            con.close()
        selecionados, decisoes = selecionar_pendencias(relatorio, registros, historico)
        destino = pasta / "reprocessamentos" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destino.mkdir(parents=True)
        (destino / "pendencias_origem.csv").write_bytes(conteudo_relatorio)
        with (destino / "selecao.csv").open("w", encoding="utf-8-sig", newline="") as arquivo:
            writer = csv.DictWriter(arquivo, delimiter=";", fieldnames=(
                "posicao_relatorio", "linha_csv_inicio", "linha_csv_atual", "registro", "id_original",
                "status_relatorio", "status_historico", "decisao"))
            writer.writeheader()
            for decisao in decisoes:
                writer.writerow({k: ("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v)
                                 for k, v in decisao.items()})
        print("\nMODO: SOMENTE ERROS DO RELATÓRIO DE PENDÊNCIAS — BUSCA POR ID")
        print(f"Relatório: {caminho_relatorio}")
        print(f"Erros elegíveis: {len(selecionados)} de {len(relatorio)} entradas do relatório")
        print("Decisões da seleção:")
        for motivo, quantidade in Counter(d["decisao"] for d in decisoes).items():
            print(f"  {quantidade}: {motivo}")
        print("A fila contém somente IDs de ERRO/ERRO_LEITURA do relatório informado.")
        print(f"Conferência da seleção: {destino / 'selecao.csv'}")
        if somente_conferir or not selecionados:
            print("Nenhum navegador aberto e nenhum lançamento enviado.")
            return 1 if any(d["decisao"].startswith("PENDENTE:") for d in decisoes) else 0
        diario = lote.Diario(pasta, registros)
        try:
            for item in selecionados:
                diario.registrar(item["registro"], "NAO_PROCESSADO", "Reprocessamento por relatório",
                                  mensagem=f"Selecionado por erro no relatório e ID único; linha atual={item['linha_csv_inicio']}; histórico anterior={historico[item['registro']]['status']}.")
            navegador = lote.criar_navegador()
            navegador.set_page_load_timeout(60)
            lote.entrar_no_extrato(navegador)
            # Nunca passa a lista completa à função de preenchimento/salvamento.
            codigo = lote.processar(selecionados, diario, navegador, False)
            print("\nRESUMO DESTA SELEÇÃO:")
            for item in selecionados:
                print(f"Linha {item['linha_csv_inicio']}: {diario.obter(item['registro'])['status']}")
            if any(diario.obter(item["registro"])["status"] != "SALVO_NOTIFICACAO" for item in selecionados):
                codigo = 1
            return 1 if any(d["decisao"].startswith("PENDENTE:") for d in decisoes) else codigo
        except BaseException:
            lote.registrar_trace(destino, "reprocessamento")
            raise
        finally:
            try:
                for item in selecionados:
                    resultado = diario.obter(item["registro"])
                    if resultado["status"] == "NAO_PROCESSADO":
                        anterior = historico[item["registro"]]
                        diario.registrar(item["registro"], anterior["status"], anterior["etapa"],
                                          anterior["tipo_erro"], anterior["mensagem"])
                diario.exportar()
            finally:
                diario.fechar()

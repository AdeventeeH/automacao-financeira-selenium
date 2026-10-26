from datetime import date
from decimal import Decimal

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

from configuracao_publica import (
    CAMPO_CATEGORIA,
    CAMPO_CONTA,
    CAMPO_CONVENIO,
    CAMPO_DATA_PAGAMENTO,
    CAMPO_DESCRICAO,
    CAMPO_FORMA_PAGAMENTO,
    CAMPO_PACIENTE,
    CAMPO_PROFISSIONAL,
    CAMPO_VALOR,
    CAMPO_VENCIMENTO,
    CHECKBOX_PAGO,
    ID_BOTAO_NOVA_DESPESA,
    ID_BOTAO_NOVA_RECEITA,
    TEMPO_ESPERA,
)


# Ativado para resolver as pendências com escolha manual do paciente.
SELECAO_MANUAL_PACIENTE = True


def criar_navegador() -> webdriver.Chrome:
    """
    Cria e configura uma janela do Google Chrome.
    """

    raise RuntimeError("Navegador real desabilitado nesta versão pública. Use python main.py.")

def criar_espera(
    navegador: webdriver.Chrome
) -> WebDriverWait:
    """
    Cria uma espera explícita para os elementos.
    """

    return WebDriverWait(
        navegador,
        TEMPO_ESPERA
    )


def localizar_botao_lancamento(
    navegador: webdriver.Chrome,
    tipo: str
):
    """
    Localiza o botão de Receita ou Despesa,
    de acordo com o tipo do lançamento.

    Esta função apenas encontra o botão.
    Ela ainda não clica.
    """

    espera = criar_espera(navegador)

    if tipo == "receita":
        id_botao = ID_BOTAO_NOVA_RECEITA

    elif tipo == "despesa":
        id_botao = ID_BOTAO_NOVA_DESPESA

    else:
        raise ValueError(
            f"Tipo inválido: {tipo!r}"
        )

    botao = espera.until(
        EC.element_to_be_clickable(
            (By.ID, id_botao)
        )
    )

    return botao


def abrir_formulario_lancamento(
    navegador: webdriver.Chrome,
    tipo: str
) -> None:
    """
    Localiza e clica no formulário correspondente.
    """

    botao = localizar_botao_lancamento(
        navegador=navegador,
        tipo=tipo
    )

    botao.click()

def formatar_valor_para_formulario(
    valor: Decimal
) -> str:
    """
    Converte um valor Decimal para o formato
    esperado pelo formulário.

    Exemplo:
    Decimal("200.50") -> "200,50"
    """

    return f"{valor:.2f}".replace(".", ",")


def formatar_data_para_formulario(
    valor: date
) -> str:
    """
    Converte uma data para DD/MM/AAAA.
    """

    return valor.strftime("%d/%m/%Y")


def preencher_campo(
    navegador: webdriver.Chrome,
    nome_campo: str,
    valor: str
) -> None:
    """
    Localiza um campo visível e habilitado,
    limpa seu conteúdo e digita o novo valor.
    """

    espera = criar_espera(navegador)

    campo = espera.until(
        EC.element_to_be_clickable(
            (By.NAME, nome_campo)
        )
    )

    navegador.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        campo
    )

    campo.clear()
    campo.send_keys(valor)

def definir_checkbox(
    navegador: webdriver.Chrome,
    nome_checkbox: str,
    marcado: bool
) -> None:
    """
    Marca ou desmarca um checkbox,
    disparando a interação necessária na página.
    """

    espera = criar_espera(navegador)

    checkbox = espera.until(
        EC.presence_of_element_located(
            (By.NAME, nome_checkbox)
        )
    )

    esta_marcado = checkbox.is_selected()

    if esta_marcado == marcado:
        return

    try:
        checkbox.click()

    except Exception:
        navegador.execute_script(
            "arguments[0].click();",
            checkbox
        )

def selecionar_forma_pagamento(
    navegador: webdriver.Chrome,
    forma_pagamento: str | None
) -> None:
    """
    Seleciona a forma de pagamento no select
    utilizado pelo Bootstrap Select.
    """

    if not forma_pagamento:
        print(
            "Forma de pagamento vazia. "
            "Campo será ignorado."
        )
        return

    espera = criar_espera(navegador)

    elemento = espera.until(
        EC.presence_of_element_located(
            (
                By.NAME,
                CAMPO_FORMA_PAGAMENTO
            )
        )
    )

    opcoes = elemento.find_elements(
        By.TAG_NAME,
        "option"
    )

    opcao_encontrada = None

    for opcao in opcoes:
        if (
            opcao.text.strip().casefold()
            == forma_pagamento.strip().casefold()
        ):
            opcao_encontrada = opcao
            break

    if opcao_encontrada is None:
        opcoes_disponiveis = [
            opcao.text.strip()
            for opcao in opcoes
        ]

        raise ValueError(
            f"Forma de pagamento "
            f"{forma_pagamento!r} não encontrada. "
            f"Opções disponíveis: "
            f"{opcoes_disponiveis}"
        )

    valor_opcao = opcao_encontrada.get_attribute(
        "value"
    )

    navegador.execute_script(
        """
        const select = arguments[0];
        const valor = arguments[1];

        select.value = valor;

        select.dispatchEvent(
            new Event('change', {
                bubbles: true
            })
        );

        if (
            window.jQuery
            && jQuery(select).selectpicker
        ) {
            jQuery(select).selectpicker('refresh');
        }
        """,
        elemento,
        valor_opcao
    )

def selecionar_opcao_segura(
    navegador: webdriver.Chrome,
    nome_campo: str,
    texto_desejado: str | None,
    nome_amigavel: str
) -> None:
    """Seleciona no formulário ativo, incluindo selects ocultos pelo Bootstrap.

    Profissional exige correspondência única. Convênio usa a primeira opção
    exata conforme autorizado pelo usuário. Aguarda opções carregadas e
    confirma o valor selecionado depois de disparar o evento change.
    """
    if not texto_desejado:
        print(f"     {nome_amigavel} vazio. Campo ignorado.")
        return

    espera = criar_espera(navegador)
    estado = {"campo_encontrado": False, "opcoes": []}

    def normalizar(texto):
        return " ".join((texto or "").split()).casefold()

    def localizar_select(driver):
        formularios = [
            f for f in driver.find_elements(By.TAG_NAME, "form")
            if f.is_displayed()
            and any(e.is_displayed() for e in f.find_elements(
                By.CSS_SELECTOR, f'input[name="{CAMPO_VALOR}"]'))
            and f.find_elements(By.NAME, CAMPO_DESCRICAO)
        ]
        if len(formularios) > 1:
            raise ValueError(f"{nome_amigavel}: mais de um formulário financeiro visível.")
        if not formularios:
            return False
        candidatos = []
        for select in formularios[0].find_elements(
            By.CSS_SELECTOR, f'select[name="{nome_campo}"]'
        ):
            if not select.is_enabled():
                continue
            wrappers = select.find_elements(
                By.XPATH,
                "./ancestor::div[contains(concat(' ', normalize-space(@class), ' '), "
                "' bootstrap-select ')][1]"
            )
            if wrappers:
                # O select nativo pode estar oculto; o componente é que precisa
                # estar visível e habilitado para o usuário no formulário aberto.
                wrapper = wrappers[0]
                botoes = wrapper.find_elements(By.CSS_SELECTOR, 'button.dropdown-toggle')
                ativo = wrapper.is_displayed() and any(
                    b.is_displayed() and b.is_enabled() for b in botoes
                )
            else:
                ativo = select.is_displayed()
            if ativo:
                candidatos.append(select)
        if len(candidatos) > 1:
            raise ValueError(f"{nome_amigavel}: mais de um select ativo no mesmo formulário.")
        return candidatos[0] if candidatos else False

    def localizar_correspondencia(driver):
        try:
            select = localizar_select(driver)
            if not select:
                return False
            estado["campo_encontrado"] = True
            opcoes = select.find_elements(By.TAG_NAME, "option")
            # .text pode ficar vazio quando o select nativo está oculto.
            pares = [(o, (o.get_attribute("textContent") or "").strip()) for o in opcoes]
            estado["opcoes"] = [texto for _, texto in pares]
            correspondencias = [
                (o, texto) for o, texto in pares
                if normalizar(texto) == normalizar(texto_desejado)
                and o.is_enabled()
            ]
            if not correspondencias:
                return False  # As opções ainda podem estar sendo carregadas.
            if len(correspondencias) > 1 and nome_campo != CAMPO_CONVENIO:
                ids = [o.get_attribute("value") for o, _ in correspondencias]
                raise ValueError(
                    f"{nome_amigavel} ambíguo: {texto_desejado!r}. IDs encontrados: {ids}."
                )
            opcao, texto = correspondencias[0]
            valor = opcao.get_attribute("value")
            if valor is None or valor == "":
                raise ValueError(f"{nome_amigavel}: a opção encontrada não possui um ID válido.")
            return select, valor, texto, len(correspondencias)
        except StaleElementReferenceException:
            return False

    try:
        select, valor, texto, quantidade = espera.until(localizar_correspondencia)
    except TimeoutException as erro:
        if not estado["campo_encontrado"]:
            raise ValueError(
                f"{nome_amigavel}: campo ativo não encontrado no formulário financeiro aberto."
            ) from erro
        raise ValueError(
            f"{nome_amigavel} {texto_desejado!r} não encontrado após aguardar o carregamento. "
            f"Opções disponíveis no formulário ativo: {estado['opcoes']}"
        ) from erro

    navegador.execute_script(
        """
        const select = arguments[0];
        select.value = arguments[1];
        select.dispatchEvent(new Event('change', { bubbles: true }));
        if (window.jQuery && jQuery(select).selectpicker) {
            jQuery(select).selectpicker('refresh');
        }
        """,
        select, valor
    )

    def escolha_confirmada(driver):
        try:
            atual = localizar_select(driver)
            return bool(atual and atual.get_attribute("value") == valor)
        except StaleElementReferenceException:
            return False

    espera.until(
        escolha_confirmada,
        message=f"{nome_amigavel}: a escolha de {texto!r} (ID {valor}) não permaneceu selecionada."
    )
    print(f"     {nome_amigavel} selecionado: {texto} | ID: {valor}")
    if nome_campo == CAMPO_CONVENIO and quantidade > 1:
        print(f"     Primeira de {quantidade} correspondências exatas, conforme configurado.")


# Equivalências explícitas entre nomes do CSV e nomes cadastrados no sistema.
# As chaves são comparadas em minúsculas, sem espaços extras.
EQUIVALENCIAS_CATEGORIA = {}

# Para nomes de Categoria equivalentes, usa a primeira sugestão na ordem do site.
USAR_PRIMEIRA_CATEGORIA_DUPLICADA = True


def ajustar_nome_categoria(texto: str) -> str:
    chave = " ".join(texto.split()).casefold()
    return EQUIVALENCIAS_CATEGORIA.get(chave, texto.strip())


def selecionar_autocomplete(
    navegador: webdriver.Chrome,
    nome_campo: str,
    texto_desejado: str | None,
    nome_amigavel: str
) -> None:
    """
    Digita em um campo Typeahead e seleciona
    exatamente a sugestão correspondente.

    Se o valor estiver vazio, ignora.
    Se não encontrar sugestão exata, gera erro.
    """

    if not texto_desejado:
        print(
            f"     {nome_amigavel} vazio. "
            "Campo ignorado."
        )
        return

    if nome_campo == CAMPO_CATEGORIA:
        categoria_original = texto_desejado
        texto_desejado = ajustar_nome_categoria(texto_desejado)
        if texto_desejado != categoria_original:
            print(f"     Categoria ajustada: {categoria_original!r} → {texto_desejado!r}")

    espera = criar_espera(navegador)

    def localizar_campo_interativo(driver):
        """
        Encontra o campo Typeahead que esteja
        visível e habilitado para interação.
        """

        campos = driver.find_elements(
            By.CSS_SELECTOR,
            f'input[name="{nome_campo}"].tt-input'
        )

        for campo_encontrado in campos:
            if (
                campo_encontrado.is_displayed()
                and campo_encontrado.is_enabled()
            ):
                return campo_encontrado

        return False

    campo = espera.until(
        localizar_campo_interativo
    )

    navegador.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        campo
    )

    campo.click()

    # Seleciona todo o conteúdo e apaga pelo teclado.
    campo.send_keys(Keys.CONTROL, "a")
    campo.send_keys(Keys.BACKSPACE)

    espera.until(
        lambda driver: campo.get_attribute("value") == "",
        message=(
            f"{nome_amigavel}: não foi possível "
            "limpar o campo antes de digitar."
        )
    )

    campo.send_keys(texto_desejado)

    print(
        f"     {nome_amigavel} — conteúdo após digitar: "
        f"{campo.get_attribute('value')!r}"
    )

    componente = campo.find_element(
        By.XPATH,
        "./ancestor::span"
        "[contains(@class, 'twitter-typeahead')][1]"
    )

    sugestoes = espera.until(
        lambda driver: [
            elemento
            for elemento in componente.find_elements(
                By.CSS_SELECTOR,
                ".tt-suggestion.tt-selectable"
            )
            if elemento.is_displayed()
        ],
        message=(
            f"{nome_amigavel}: nenhuma sugestão visível "
            f"ao pesquisar {texto_desejado!r}."
        )
    )

    def normalizar_texto(texto: str) -> str:
        texto = texto.strip()

        # Categoria: ignora o complemento após " - ".
        # Preserva hífens que fazem parte do próprio nome.
        if nome_campo == CAMPO_CATEGORIA:
            texto = texto.split(" - ", 1)[0].strip()

        return texto.casefold()

    texto_procurado = normalizar_texto(texto_desejado)

    correspondencias = [
        sugestao
        for sugestao in sugestoes
        if normalizar_texto(sugestao.text) == texto_procurado
    ]

    if len(correspondencias) == 0:
        textos_encontrados = [
            sugestao.text.strip()
            for sugestao in sugestoes
        ]

        raise ValueError(
            f"{nome_amigavel} "
            f"{texto_desejado!r} não encontrado. "
            f"Sugestões exibidas: "
            f"{textos_encontrados}"
        )

    if len(correspondencias) > 1:
        if nome_campo == CAMPO_CATEGORIA and USAR_PRIMEIRA_CATEGORIA_DUPLICADA:
            print(
                f"     Categoria: usando a primeira de {len(correspondencias)} "
                f"correspondências: {correspondencias[0].text.strip()!r}"
            )
        else:
            raise ValueError(
                f"{nome_amigavel} ambíguo: "
                f"{texto_desejado!r} apareceu "
                f"{len(correspondencias)} vezes."
            )

    correspondencias[0].click()

def selecionar_paciente_manualmente(navegador, nome_paciente) -> None:
    """Digita a pesquisa; a escolha pertence ao usuário na janela do Chrome."""
    def localizar_campo(driver):
        campos = [c for c in driver.find_elements(
            By.CSS_SELECTOR, f'input[name="{CAMPO_PACIENTE}"].tt-input'
        ) if c.is_displayed() and c.is_enabled()]
        if len(campos) > 1:
            raise ValueError("Há mais de um campo Paciente ativo. Feche os formulários extras.")
        return campos[0] if campos else False

    campo = criar_espera(navegador).until(localizar_campo)
    grupo = campo.find_element(
        By.XPATH,
        "./ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' form-group ')][1]",
    )
    ocultos = grupo.find_elements(By.CSS_SELECTOR, 'input[type="hidden"][name="patient"]')
    if len(ocultos) != 1:
        raise ValueError("Não foi possível identificar o ID do paciente neste formulário.")
    oculto = ocultos[0]
    # Exige um formulário novo, sem associação residual de outra movimentação.
    if (oculto.get_attribute("value") or "").strip():
        raise ValueError("O formulário já contém um paciente selecionado. Reabra antes de tentar novamente.")
    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
    campo.click()
    campo.send_keys(Keys.CONTROL, "a")
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(nome_paciente.strip())
    print("\nSelecione o paciente correto nas sugestões do Chrome.")
    print("Você pode ajustar a pesquisa no campo, se necessário.")
    print("Depois volte a este terminal e pressione ENTER para continuar.")
    print("Digite PULAR para deixar este registro com erro; Ctrl+C encerra a execução.")
    while True:
        resposta = input("Paciente selecionado? ENTER para continuar ou PULAR: ").strip().upper()
        if resposta == "PULAR":
            raise ValueError("Seleção manual de paciente pulada pelo usuário; lançamento não enviado.")
        if resposta:
            print("Use ENTER após selecionar, ou digite PULAR.")
            continue
        try:
            if not campo.is_displayed() or not campo.is_enabled():
                raise ValueError("O formulário foi fechado ou deixou de estar ativo durante a seleção.")
            id_paciente = (oculto.get_attribute("value") or "").strip()
            texto = (campo.get_attribute("value") or "").strip()
            invalido = (campo.get_attribute("aria-invalid") or "").lower() == "true"
        except StaleElementReferenceException as erro:
            raise ValueError("A página ou o formulário mudou durante a seleção manual.") from erro
        if id_paciente and texto and not invalido:
            print("     Seleção registrada. Continuando o lançamento...")
            return
        print("A seleção ainda não foi registrada. Clique em uma sugestão no Chrome e pressione ENTER novamente.")


def selecionar_paciente(
    navegador: webdriver.Chrome,
    nome_paciente: str | None
) -> None:
    """
    Pesquisa o paciente e, no modo manual, aguarda a escolha do usuário.
    Fora do modo manual, exige correspondência exata nas sugestões.

    Confirma a seleção verificando se o campo
    oculto 'patient' recebeu o ID do paciente.
    """

    if not nome_paciente or not nome_paciente.strip():
        print(
            "     Paciente vazio. "
            "Campo ignorado."
        )
        return

    if SELECAO_MANUAL_PACIENTE:
        selecionar_paciente_manualmente(navegador, nome_paciente)
        return

    espera = criar_espera(navegador)

    campo = espera.until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                f'input[name="{CAMPO_PACIENTE}"].tt-input'
            )
        )
    )

    navegador.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        campo
    )

    campo.click()
    campo.clear()
    campo.send_keys(nome_paciente)

    # Encontra somente as sugestões pertencentes
    # ao autocomplete do campo Paciente.
    def localizar_sugestoes_paciente(driver):
        elementos = campo.find_elements(
            By.XPATH,
            (
                "./ancestor::span"
                "[contains(@class, 'twitter-typeahead')]"
                "//div[contains(@class, 'tt-suggestion') "
                "and contains(@class, 'tt-selectable')]"
            )
        )

        sugestoes_visiveis = [
            elemento
            for elemento in elementos
            if elemento.is_displayed()
        ]

        return sugestoes_visiveis or False

    sugestoes = espera.until(
        localizar_sugestoes_paciente
    )

    texto_procurado = (
        nome_paciente
        .strip()
        .casefold()
    )

    correspondencias = [
        sugestao
        for sugestao in sugestoes
        if (
            sugestao.text
            .strip()
            .casefold()
            == texto_procurado
        )
    ]

    if len(correspondencias) == 0:
        textos_encontrados = [
            sugestao.text.strip()
            for sugestao in sugestoes
        ]

        raise ValueError(
            f"Paciente {nome_paciente!r} "
            "não encontrado exatamente. "
            f"Sugestões exibidas: {textos_encontrados}"
        )

    if len(correspondencias) > 1:
        raise ValueError(
            f"Paciente ambíguo: {nome_paciente!r} "
            f"apareceu {len(correspondencias)} vezes. "
            "A seleção foi interrompida para evitar "
            "associar o lançamento ao paciente errado."
        )

    correspondencias[0].click()

    # Confirma que a escolha realmente foi registrada.
    espera.until(
        lambda driver: (
            driver.find_element(
                By.NAME,
                "patient"
            ).get_attribute("value")
            or False
        )
    )

def preencher_campos_basicos(
    navegador: webdriver.Chrome,
    lancamento
) -> None:

    print()
    print("Iniciando preenchimento...")

    # PACIENTE
    print("1/11 - Selecionando Paciente...")

    selecionar_paciente(
    navegador=navegador,
    nome_paciente=lancamento.paciente
    )

    print("     OK")

    # PROFISSIONAL
    print("2/11 - Selecionando Profissional...")

    selecionar_opcao_segura(
        navegador=navegador,
        nome_campo=CAMPO_PROFISSIONAL,
        texto_desejado=lancamento.profissional,
        nome_amigavel="Profissional"
    )

    print("     OK")

    # CONVÊNIO
    print("3/11 - Selecionando Convênio...")

    selecionar_opcao_segura(
        navegador=navegador,
        nome_campo=CAMPO_CONVENIO,
        texto_desejado=lancamento.convenio,
        nome_amigavel="Convênio"
    )

    print("     OK")

    # VALOR
    print("4/11 - Preenchendo Valor...")

    preencher_campo(
        navegador=navegador,
        nome_campo=CAMPO_VALOR,
        valor=formatar_valor_para_formulario(
            lancamento.valor
        )
    )

    print("     OK")

    # DESCRIÇÃO
    print("5/11 - Preenchendo Descrição...")

    preencher_campo(
        navegador=navegador,
        nome_campo=CAMPO_DESCRICAO,
        valor=lancamento.descricao
    )

    print("     OK")

    # CATEGORIA
    print("6/11 - Selecionando Categoria...")

    selecionar_autocomplete(
        navegador=navegador,
        nome_campo=CAMPO_CATEGORIA,
        texto_desejado=lancamento.categoria,
        nome_amigavel="Categoria"
    )

    print("     OK")

    # CONTA
    print("7/11 - Selecionando Conta...")

    selecionar_autocomplete(
        navegador=navegador,
        nome_campo=CAMPO_CONTA,
        texto_desejado=lancamento.conta,
        nome_amigavel="Conta"
    )

    print("     OK")

    # FORMA DE PAGAMENTO
    print(
        "8/11 - Selecionando "
        "Forma de Pagamento..."
    )

    selecionar_forma_pagamento(
        navegador=navegador,
        forma_pagamento=lancamento.forma_pagamento
    )

    print("     OK")

    # VENCIMENTO
    print("9/11 - Preenchendo Vencimento...")

    preencher_campo(
        navegador=navegador,
        nome_campo=CAMPO_VENCIMENTO,
        valor=formatar_data_para_formulario(
            lancamento.data
        )
    )

    print("     OK")

    # PAGO / RECEBIDO
    print(
        "10/11 - Configurando "
        "Pago/Recebido..."
    )

    definir_checkbox(
        navegador=navegador,
        nome_checkbox=CHECKBOX_PAGO,
        marcado=lancamento.pago
    )

    print("     OK")

    # DATA DE PAGAMENTO
    print(
        "11/11 - Verificando "
        "Data de Pagamento..."
    )

    if (
        lancamento.pago
        and lancamento.data_pagamento
    ):
        preencher_data_pagamento(
            navegador=navegador,
            valor=lancamento.data_pagamento
        )

        print("     OK")

    else:
        print(
            "     Ignorado: lançamento "
            "não está pago/recebido."
        )

    print()
    print(
        "Preenchimento desta etapa concluído."
    )

def preencher_data_pagamento(
    navegador: webdriver.Chrome,
    valor: date
) -> None:
    """
    Aguarda o campo de pagamento/recebimento
    ser habilitado depois de marcar o checkbox.
    """

    espera = criar_espera(navegador)

    campo = espera.until(
        lambda driver: (
            elemento
            if (
                (
                    elemento := driver.find_element(
                        By.NAME,
                        CAMPO_DATA_PAGAMENTO
                    )
                ).is_displayed()
                and elemento.is_enabled()
            )
            else False
        )
    )

    navegador.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        campo
    )

    campo.clear()

    campo.send_keys(
        formatar_data_para_formulario(
            valor
        )
    )

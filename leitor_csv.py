"""Leitor financeiro: datas brasileiras com barras/hífens e Centro de Custo vazio.

No lote, processamento_lote.py detecta o separador e chama converter_linha().
"""
import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


COLUNAS_OBRIGATORIAS = {
    "id", "Clínica", "Categoria", "Centro de Custo", "Conta",
    "Profissional de Saúde", "PK Paciente", "Paciente", "Convênio",
    "Procedimento", "Tipo", "Descrição", "Valor", "Data", "Data de Pagamento",
    "Pago?", "Forma de Pagamento", "Quantidade de Recorrências",
    "Número da Recorrência", "Data da Inserção",
}


@dataclass
class LancamentoFinanceiro:
    id: str
    clinica: str | None
    categoria: str
    centro_custo: str
    conta: str
    profissional: str | None
    pk_paciente: str | None
    paciente: str | None
    convenio: str | None
    procedimento: str | None
    tipo: str
    descricao: str
    valor: Decimal
    data: date
    data_pagamento: date | None
    pago: bool
    forma_pagamento: str | None
    quantidade_recorrencias: int | None
    numero_recorrencia: int | None
    data_insercao: date | None


def limpar_texto(valor: str | None) -> str:
    return "" if valor is None else valor.strip()


def texto_opcional(valor: str | None) -> str | None:
    return limpar_texto(valor) or None


def normalizar_texto(valor: str | None) -> str:
    texto = unicodedata.normalize("NFD", limpar_texto(valor).lower())
    texto_sem_acentos = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto_sem_acentos)


def converter_valor(valor: str | None) -> Decimal:
    texto = limpar_texto(valor)
    if not texto:
        # Convenção desta demonstração: valor em branco equivale a zero.
        return Decimal("0.00")
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(f"Valor financeiro inválido: {valor!r}") from erro


def converter_data(valor: str | None, obrigatoria: bool = False) -> date | None:
    texto = limpar_texto(valor)
    if not texto:
        if obrigatoria:
            raise ValueError("O campo de data está vazio.")
        return None
    formatos = (
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
    )
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
    except ValueError as erro:
        raise ValueError(f"Data inválida: {valor!r}") from erro


def converter_pago(valor: str | None) -> bool:
    texto = normalizar_texto(valor)
    if texto in {"sim", "s", "true", "1", "pago", "recebido", "quitado"}:
        return True
    # Convenção desta demonstração: vazio ou somente espaços significa não pago.
    if texto in {"", "nao", "n", "false", "0", "em aberto", "aberto", "pendente"}:
        return False
    raise ValueError(f"Valor não reconhecido no campo Pago?: {valor!r}")


def converter_tipo(valor: str | None) -> str:
    texto = normalizar_texto(valor)
    if texto in {"receita", "entrada", "credito", "r"}:
        return "receita"
    if texto in {"despesa", "saida", "debito", "d"}:
        return "despesa"
    raise ValueError(f"Tipo de lançamento não reconhecido: {valor!r}")


def converter_inteiro(valor: str | None) -> int | None:
    texto = limpar_texto(valor)
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError as erro:
        raise ValueError(f"Número inteiro inválido: {valor!r}") from erro


def exigir_texto(linha: dict[str, str], coluna: str) -> str:
    valor = limpar_texto(linha.get(coluna))
    if not valor:
        raise ValueError(f"O campo obrigatório {coluna!r} está vazio.")
    return valor


def converter_linha(linha: dict[str, str]) -> LancamentoFinanceiro:
    pago = converter_pago(linha.get("Pago?"))
    data_pagamento = converter_data(linha.get("Data de Pagamento"))
    if pago and data_pagamento is None:
        raise ValueError(
            "O lançamento está marcado como pago, mas a Data de Pagamento está vazia."
        )
    return LancamentoFinanceiro(
        id=exigir_texto(linha, "id"),
        clinica=texto_opcional(linha.get("Clínica")),
        categoria=exigir_texto(linha, "Categoria"),
        # A coluna é esperada no cabeçalho, mas seu VALOR pode ficar vazio.
        centro_custo=limpar_texto(linha.get("Centro de Custo")),
        conta=exigir_texto(linha, "Conta"),
        profissional=texto_opcional(linha.get("Profissional de Saúde")),
        pk_paciente=texto_opcional(linha.get("PK Paciente")),
        paciente=texto_opcional(linha.get("Paciente")),
        convenio=texto_opcional(linha.get("Convênio")),
        procedimento=texto_opcional(linha.get("Procedimento")),
        tipo=converter_tipo(linha.get("Tipo")),
        descricao=exigir_texto(linha, "Descrição"),
        valor=converter_valor(linha.get("Valor")),
        data=converter_data(linha.get("Data"), obrigatoria=True),
        data_pagamento=data_pagamento,
        pago=pago,
        forma_pagamento=texto_opcional(linha.get("Forma de Pagamento")),
        quantidade_recorrencias=converter_inteiro(linha.get("Quantidade de Recorrências")),
        numero_recorrencia=converter_inteiro(linha.get("Número da Recorrência")),
        data_insercao=converter_data(linha.get("Data da Inserção")),
    )


def validar_colunas(colunas_encontradas: list[str] | None) -> None:
    if colunas_encontradas is None:
        raise ValueError("O arquivo CSV não possui cabeçalho.")
    ausentes = COLUNAS_OBRIGATORIAS - set(colunas_encontradas)
    if ausentes:
        raise ValueError("Colunas ausentes no CSV: " + ", ".join(sorted(ausentes)))


def ler_csv(caminho: str | Path) -> list[LancamentoFinanceiro]:
    """API anterior, para CSV com vírgulas. O lote usa seu próprio leitor flexível."""
    arquivo = Path(caminho)
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {arquivo}")
    lancamentos = []
    with arquivo.open("r", encoding="utf-8-sig", newline="") as arquivo_csv:
        leitor = csv.DictReader(arquivo_csv)
        validar_colunas(leitor.fieldnames)
        for numero_linha, linha in enumerate(leitor, start=2):
            try:
                lancamentos.append(converter_linha(linha))
            except Exception as erro:
                raise ValueError(f"Erro na linha {numero_linha}: {erro}") from erro
    return lancamentos

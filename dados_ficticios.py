"""Dados sintéticos escritos do zero, sem leitura de arquivos externos."""
import csv
import io

from leitor_csv import COLUNAS_OBRIGATORIAS


def criar_linhas(incluir_erro=False):
    linhas = []
    for numero, tipo, valor in (
        (1, "Receita", "123,45"),
        (2, "Despesa", "23,45"),
        (3, "Receita", "50,00"),
    ):
        linha = dict.fromkeys(sorted(COLUNAS_OBRIGATORIAS), "")
        linha.update({
            "id": f"DEMO-MOV-{numero:03}",
            "Clínica": "Clínica Fictícia de Demonstração",
            "Categoria": "Categoria Fictícia",
            "Conta": "Conta Fictícia",
            "Profissional de Saúde": "Profissional Fictício A",
            "PK Paciente": f"DEMO-PAC-{numero:03}",
            "Paciente": f"Paciente Fictício {numero:03}",
            "Convênio": "Convênio Fictício",
            "Tipo": tipo,
            "Descrição": f"Movimentação fictícia {numero:03}",
            "Valor": valor,
            "Data": "15/01/2030",
            "Data de Pagamento": "15/01/2030" if numero != 3 else "",
            "Pago?": "Sim" if numero != 3 else "Não",
            "Forma de Pagamento": "Forma Fictícia",
        })
        linhas.append(linha)
    if incluir_erro:
        invalida = dict(linhas[0])
        invalida.update({
            "id": "DEMO-MOV-004", "Descrição": "Erro de demonstração",
            "Pago?": "Sim", "Data de Pagamento": "",
        })
        linhas.append(invalida)
    return linhas


def criar_csv(incluir_erro=False, separador=";"):
    fluxo = io.StringIO(newline="")
    escritor = csv.DictWriter(
        fluxo, fieldnames=sorted(COLUNAS_OBRIGATORIAS), delimiter=separador,
    )
    escritor.writeheader()
    escritor.writerows(criar_linhas(incluir_erro))
    return fluxo.getvalue()

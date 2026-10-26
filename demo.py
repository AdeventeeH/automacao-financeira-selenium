"""Demonstração offline do leitor, processamento e diário reais do projeto."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from dados_ficticios import criar_csv
from processamento_lote import Diario, carregar_registros, processar


class InterfaceSimulada:
    """Simula um formulário em memória; não instancia navegador ou conexão."""

    def __init__(self):
        self.preenchidos = []
        self.abertos = []

    def espera(self, navegador):
        return self

    def until(self, condicao, mensagem=""):
        if not condicao(None):
            raise RuntimeError(mensagem)
        return True

    def extrato_pronto(self, navegador):
        return True

    def recuperar(self, navegador):
        pass

    def abrir_formulario_lancamento(self, navegador, tipo):
        self.abertos.append(tipo)

    def preencher_campos_basicos(self, navegador, lancamento):
        self.preenchidos.append(lancamento)

    def preparar_salvamento(self, navegador):
        return None, self

    def click(self):
        raise AssertionError("A demonstração nunca deve clicar em Salvar.")


def executar_demo(incluir_erro=False):
    """Gera CSV e SQLite temporários novos e apaga apenas esses temporários."""
    interface = InterfaceSimulada()
    with TemporaryDirectory(prefix="portfolio_demo_") as temporario:
        raiz = Path(temporario)
        entrada = raiz / "demonstracao.csv"
        entrada.write_text(criar_csv(incluir_erro), encoding="utf-8", newline="")
        _, registros = carregar_registros(entrada)
        diario = Diario(raiz / "diario", registros)
        try:
            processar(registros, diario, None, True, interface=interface)
            resultados = diario.todos()
        finally:
            diario.fechar()
    return resultados


def mostrar_resumo(resultados):
    print("\nDEMONSTRAÇÃO OFFLINE — valores e identidades fictícios")
    for status, quantidade in sorted(Counter(r["status"] for r in resultados).items()):
        print(f"  {status}: {quantidade}")
    print("Nenhum acesso externo. Arquivos temporários da demo removidos.")

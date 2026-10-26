"""Exemplo documental. A demo usa apenas configuracao_publica.py.

Não é necessário copiar nem editar este arquivo para executar a demonstração.
Os caminhos abaixo são relativos a esta distribuição pública.
"""
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent
CAMINHO_CSV = PASTA_PROJETO / "dados" / "demonstracao.csv"
MODO_TESTE = True
LIMITE_REGISTROS = 3
TEMPO_ESPERA = 20

# Endereço reservado para documentação; nenhuma chamada é feita a ele.
URL_SISTEMA_EXEMPLO = "https://example.invalid/demonstracao/"

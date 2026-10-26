"""Ponto de integração deliberadamente desativado na distribuição pública."""


def entrar_no_extrato(navegador, tempo_espera=30):
    raise RuntimeError(
        "Acesso externo desabilitado nesta versão pública. Use python main.py."
    )

"""Entrada pública: executa exclusivamente dados fictícios em modo offline."""
import argparse

from demo import executar_demo, mostrar_resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--incluir-erro", action="store_true",
        help="Adiciona um registro fictício inválido para demonstrar ERRO_LEITURA.",
    )
    args = parser.parse_args()
    resultados = executar_demo(args.incluir_erro)
    mostrar_resumo(resultados)
    esperados = ["TESTE_SEM_SALVAR"] * 3
    if args.incluir_erro:
        esperados.append("ERRO_LEITURA")
    return 0 if [r["status"] for r in resultados] == esperados else 1


if __name__ == "__main__":
    raise SystemExit(main())

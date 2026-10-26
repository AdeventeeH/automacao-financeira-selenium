"""Audita a lista pública e padrões sensíveis sem imprimir valores encontrados.

Esta verificação heurística complementa a revisão humana; não certifica ausência
universal de dados pessoais. Não consulta diretórios externos, rede ou cofres.
"""
import argparse
import hashlib
from pathlib import Path
import re


ARQUIVOS = {
    ".gitignore", "README.md", "LICENSE", "requirements.txt", "config.example.py",
    "configuracao_publica.py", "acesso_sistema.py", "automacao.py", "leitor_csv.py",
    "processamento_lote.py", "reprocessar_pendencias.py", "dados_ficticios.py",
    "demo.py", "main.py", "tests/test_projeto.py", "scripts/auditar_publicacao.py",
    "REVISAO_PUBLICACAO.md", "MANIFESTO_PUBLICACAO.sha256",
}

PADROES = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "caminho_pessoal": r"(?i)(?:[a-z]:[\\/](?:users|documents and settings)[\\/]|/(?:home|users)/)[^\s]+",
    "chave_privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "token_conhecido": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    "segredo_literal": r'''(?i)\b(?:senha|password|token|secret|api_key|cookie|authorization)\s*[:=]\s*["'][^"'\r\n]{4,}["']''',
    "cpf_cnpj_formatado": r"\b(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b",
    "identificador_numerico_longo": r"\b\d{8,}\b",
    "uuid": r"(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b",
    "url_externa": r"https?://(?!example\.invalid(?:[/\s\"']|$))[^\s\"'<>]+",
}


def auditar(raiz):
    problemas = []
    encontrados = set()
    for caminho in sorted(raiz.rglob("*")):
        relativo = caminho.relative_to(raiz).as_posix()
        # Metadados internos de um futuro repositório não fazem parte do pacote.
        if relativo == ".git" or relativo.startswith(".git/"):
            continue
        if caminho.is_symlink():
            problemas.append((relativo, 0, "link simbólico não permitido"))
            continue
        if caminho.is_dir():
            if relativo not in {"scripts", "tests"}:
                problemas.append((relativo, 0, "diretório fora da lista permitida"))
            continue
        encontrados.add(relativo)
        if relativo not in ARQUIVOS:
            problemas.append((relativo, 0, "arquivo fora da lista permitida"))
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except UnicodeError:
            problemas.append((relativo, 0, "arquivo não textual UTF-8"))
            continue
        # Manifesto contém somente hashes validados separadamente.
        if relativo == "MANIFESTO_PUBLICACAO.sha256":
            continue
        for linha, conteudo in enumerate(texto.splitlines(), 1):
            for categoria, padrao in PADROES.items():
                if re.search(padrao, conteudo):
                    problemas.append((relativo, linha, categoria))
    for ausente in sorted(ARQUIVOS - encontrados):
        problemas.append((ausente, 0, "arquivo obrigatório ausente"))
    return problemas


def conteudo_manifesto(raiz):
    return "".join(
        f"{hashlib.sha256((raiz / nome).read_bytes()).hexdigest()}  {nome}\n"
        for nome in sorted(ARQUIVOS - {"MANIFESTO_PUBLICACAO.sha256"})
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gerar-manifesto", action="store_true")
    args = parser.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    problemas = auditar(raiz)
    if args.gerar_manifesto:
        problemas = [p for p in problemas if p != (
            "MANIFESTO_PUBLICACAO.sha256", 0, "arquivo obrigatório ausente",
        )]
    if problemas:
        for arquivo, linha, categoria in problemas:
            print(f"REVISAR {arquivo}:{linha} — {categoria}")
        return 1
    manifesto = raiz / "MANIFESTO_PUBLICACAO.sha256"
    esperado = conteudo_manifesto(raiz)
    if args.gerar_manifesto:
        manifesto.write_text(esperado, encoding="utf-8", newline="\n")
    elif manifesto.read_text(encoding="utf-8") != esperado:
        print("REVISAR: arquivos alterados após a geração do manifesto.")
        return 1
    print(f"OK: {len(ARQUIVOS)} arquivos permitidos; padrões sensíveis não detectados; manifesto válido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

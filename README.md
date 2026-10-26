# Automação de lançamentos — demonstração de portfólio

Versão pública anonimizada de um projeto Python de processamento em lote e
automação de formulários. Demonstra validação de CSV, precisão decimal, controle
de estado persistente e recuperação cuidadosa de falhas.

**A demonstração é offline e utiliza somente dados fictícios criados do zero.**
Não é necessário possuir conta em qualquer sistema. Nenhum navegador é aberto.

Este é um projeto independente e demonstrativo, sem vínculo, afiliação ou endosso oficial de qualquer plataforma ou empresa citada.

## Executar

Requer Python 3.10 ou superior. Execute os comandos dentro desta pasta.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B main.py
python -B main.py --incluir-erro
```

No Linux/macOS, ative o ambiente com `source .venv/bin/activate`.
A instalação inicial pode precisar de internet; a execução da demo é local.

A primeira execução produz três registros `TESTE_SEM_SALVAR`. A opção
`--incluir-erro` acrescenta um registro fictício pago sem data de pagamento,
gerando um `ERRO_LEITURA`. Esse erro é intencional e a demonstração retorna
código zero quando o resultado esperado é confirmado.

O CSV sintético, os relatórios e o banco SQLite são criados em um diretório
temporário exclusivo e removidos ao final. Não são distribuídos no repositório.
Valores como `123,45` e identificadores `DEMO-MOV-001` são inteiramente fictícios.

## O que o código demonstra

- Detecção de delimitador pelo cabeçalho, suporte a BOM e registros multilinha.
- Conversão de valores com `Decimal`, datas brasileiras e campos opcionais.
- Diário SQLite com registro durável antes da tentativa de salvamento.
- Bloqueio de reenvio automático quando o resultado anterior é incerto.
- Seleção de pendências por identidade única, conteúdo e histórico compatíveis.
- Exportação de relatórios com proteção contra fórmulas de planilha.
- Interface injetável: o mesmo processamento recebe uma simulação em memória.
- Adaptador Selenium de referência com esperas explícitas e verificação de estado.

## Organização

| Arquivo | Responsabilidade |
| --- | --- |
| `main.py`, `demo.py` | Entrada pública e formulário simulado |
| `dados_ficticios.py` | Geração determinística de dados sintéticos |
| `leitor_csv.py` | Modelo de lançamento e validação |
| `processamento_lote.py` | Leitura flexível, diário e processamento |
| `reprocessar_pendencias.py` | Regras de seleção e retomada |
| `automacao.py` | Adaptador Selenium de referência; criação de navegador bloqueada |
| `acesso_sistema.py` | Integração externa desativada |
| `configuracao_publica.py` | Parâmetros seguros e seletores genéricos de campos |
| `config.example.py` | Exemplo documental sem segredos ou caminhos pessoais |
| `tests/test_projeto.py` | Testes isolados com dados fictícios |
| `scripts/auditar_publicacao.py` | Lista permitida, busca de padrões sensíveis e hashes |

## Testar e revisar

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/auditar_publicacao.py
```

Os testes exercitam erros de leitura, retomada, bloqueio de duplicação, falha
de persistência antes de salvar, exportação segura e demonstração com rede e
criação do Chrome bloqueadas por mocks.

O auditor exige que a pasta contenha apenas os arquivos públicos aprovados.
Por isso, ambientes `.venv` e caches locais fazem a auditoria estrita falhar:
execute-a sobre uma cópia limpa destinada à publicação, usando um interpretador
externo a essa cópia. `-B` evita a geração de caches Python.

Consulte [REVISAO_PUBLICACAO.md](REVISAO_PUBLICACAO.md) para a relação completa
de arquivos, critérios de anonimização e limites da validação.
O manifesto SHA-256 registra o conteúdo revisado. Depois de qualquer alteração,
revise novamente e use `python -B scripts/auditar_publicacao.py --gerar-manifesto`.

## Limites da versão pública

O login e o acesso ao cofre de credenciais foram retirados. A criação de um
navegador real e a entrada no sistema geram uma exceção explícita, mesmo que
alguém altere `MODO_TESTE`. O endereço de documentação usa `example.invalid`.
`config.example.py` não é carregado automaticamente e não habilita integrações.

Os seletores HTML e as rotinas de confirmação de interface servem como referência
de implementação; não foram testados contra um serviço externo nesta versão.
A simulação não comprova funcionamento de uma integração real. As rotinas de
retomada são verificadas em testes locais; a CLI pública oferece apenas a demo.

O controle de estado reduz reenvios, mas não garante execução exatamente uma vez
em sistemas externos. A combinação de uma mensagem nova de sucesso e fechamento
do formulário é uma evidência de interface, não uma consulta transacional ao servidor.

## Licença

MIT — veja [LICENSE](LICENSE). A atribuição pública usa o nome
`Lucas Adevente da Silva`, conforme autorizado pelo autor.

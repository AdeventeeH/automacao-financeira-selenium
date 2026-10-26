# Revisão da versão pública

## Escopo

Cópia separada preparada para revisão antes de publicação. Nenhum push foi
executado. O pacote público contém somente os 18 arquivos abaixo; não inclui
histórico Git, ambientes virtuais ou artefatos produzidos pela execução.

```text
versao_publica_github/
├── .gitignore
├── README.md
├── LICENSE
├── requirements.txt
├── config.example.py
├── configuracao_publica.py
├── acesso_sistema.py
├── automacao.py
├── leitor_csv.py
├── processamento_lote.py
├── reprocessar_pendencias.py
├── dados_ficticios.py
├── demo.py
├── main.py
├── MANIFESTO_PUBLICACAO.sha256
├── REVISAO_PUBLICACAO.md
├── scripts/
│   └── auditar_publicacao.py
└── tests/
    └── test_projeto.py
```

## Anonimização

- Cópia seletiva de quatro módulos de código, seguida de revisão e adaptação.
- Configuração local original não copiada; parâmetros públicos criados separadamente.
- Login, leitura do cofre, credenciais e endpoints do serviço real retirados.
- Referências de domínio e namespace de interface substituídas por exemplos genéricos.
- Mapeamento específico de categorias retirado.
- Documentação original substituída por documentação nova para o portfólio.
- Dados de demonstração escritos do zero: pessoas, clínica, conta, convênio,
  identificadores, descrições, datas e valores fictícios.
- Nenhum CSV, log, SQLite, arquivo financeiro, cache, cookie, token ou chave
  existente foi copiado. A demo só gera arquivos novos e temporários.
- Licença MIT com atribuição a Lucas Adevente da Silva, expressamente autorizada
  pelo autor. Esse nome público de autoria é uma exceção intencional à anonimização;
  nenhum e-mail pessoal foi incluído nos arquivos.
- README com aviso explícito de independência e ausência de vínculo, afiliação
  ou endosso oficial de plataformas e empresas citadas.

## Verificações

A revisão inclui pesquisa de credenciais, e-mails, senhas, tokens, cookies,
identificadores, documentos, URLs e caminhos pessoais. Os termos encontrados
como nomes de campos HTML, variáveis e padrões do auditor não são credenciais.
IDs de campos como `patient_name` são seletores de interface; as identidades
dos exemplos usam o prefixo `DEMO-`.

O auditor reproduz a pesquisa de padrões sensíveis, rejeita arquivos fora da
lista permitida e verifica o manifesto. Ele não exibe o conteúdo de achados.
A revisão contextual complementa os padrões: nomes livres e segredos com
formatos desconhecidos não podem ser excluídos apenas por expressões regulares.

Validação local concluída: 19 testes automatizados aprovados; demonstração
normal e demonstração com erro intencional concluídas com código zero;
auditoria da lista permitida e manifesto SHA-256 aprovados.
Os testes usam diretórios temporários e não executam login ou operações remotas.
O adaptador de navegador não foi validado contra um serviço externo.

Verificações adicionais: o auditor detectou um e-mail sintético e um CSV
não permitido inseridos em uma cópia temporária. As regras do `.gitignore`
foram conferidas com o próprio Git em um repositório temporário isolado.
Nenhum repositório ou histórico do projeto privado foi utilizado.

Também foi realizada comparação local, somente em memória, entre valores
dos arquivos privados e o texto público. As coincidências encontradas foram
palavras genéricas em documentação, comentários e na licença, sem identidades
reais identificadas. Os valores privados e os relatórios dessa comparação
não fazem parte do pacote. A integridade dos arquivos originais foi confirmada
por comparação de hashes antes e depois do trabalho.

## Antes de publicar

Revisar estes 18 arquivos e o manifesto. Publicar somente esta pasta como raiz
de um repositório novo, sem importar histórico ou arquivos do projeto privado.
O `.gitignore` usa lista permitida e bloqueia dados, ambientes e credenciais;
ele não remove segredos já presentes em histórico ou incluídos à força.

A publicação depende da confirmação expressa do proprietário após a revisão.
Alterações posteriores exigem novos testes, auditoria e atualização do manifesto.

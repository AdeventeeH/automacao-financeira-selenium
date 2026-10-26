"""Configuração fixa da distribuição pública, sem dados de ambiente."""
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent
CAMINHO_CSV = PASTA_PROJETO / "dados" / "demonstracao.csv"
TEMPO_ESPERA = 20
MODO_TESTE = True
LIMITE_REGISTROS = 3

# Identificadores de campos HTML, sem IDs de pessoas, contas ou clínicas.
ID_BOTAO_NOVA_RECEITA = 'btn-income'
ID_BOTAO_NOVA_DESPESA = 'btn-expenses'
CAMPO_PACIENTE = 'patient_name'
CAMPO_PROFISSIONAL = 'physician'
CAMPO_CONVENIO = 'insurance'
CAMPO_PROCEDIMENTO = 'procedure_name'
CAMPO_VALOR = 'value'
CAMPO_DESCRICAO = 'name'
CAMPO_CATEGORIA = 'category_name'
CAMPO_CONTA = 'account_name'
CAMPO_FORMA_PAGAMENTO = 'payment_form'
CAMPO_CENTRO_CUSTO = 'cost_center_name'
CAMPO_VENCIMENTO = 'expires_date'
CHECKBOX_PAGO = 'paid'
CAMPO_DATA_PAGAMENTO = 'pay_date'
CAMPO_RECORRENCIA = 'recurrence'
CAMPO_NUMERO_RECORRENCIAS = 'recurrence_number'
CAMPO_ENTRADA = 'down_payment'
CAMPO_NUMERO_PARCELAS = 'installment_number'
CHECKBOX_PAGADOR_DIFERENTE = 'has_payer'
CAMPO_NOME_PAGADOR = 'payer_name'
CAMPO_DOCUMENTO_PAGADOR = 'payer_cpf_cnpj'

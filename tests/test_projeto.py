"""Regressões com dados sintéticos e diretórios temporários isolados."""
import contextlib
import csv
import io
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import acesso_sistema
import automacao
from dados_ficticios import criar_csv, criar_linhas
from demo import executar_demo, InterfaceSimulada
from leitor_csv import converter_data, converter_linha, converter_pago, converter_valor
import processamento_lote as lote
from reprocessar_pendencias import selecionar_pendencias


class LeituraTests(unittest.TestCase):
    def test_valores_brasileiros(self):
        self.assertEqual(str(converter_valor("R$ 1.234,56")), "1234.56")
        self.assertEqual(str(converter_valor(" ")), "0.00")
        with self.assertRaises(ValueError):
            converter_valor("inválido")

    def test_datas_e_pago(self):
        for texto in ("15/01/2030", "15-01-2030", "2030-01-15"):
            self.assertEqual(converter_data(texto).isoformat(), "2030-01-15")
        self.assertFalse(converter_pago("Não"))
        self.assertFalse(converter_pago(" "))
        with self.assertRaises(ValueError):
            converter_data("31/02/2030")

    def test_pagamento_exige_data(self):
        with self.assertRaises(ValueError):
            converter_linha(criar_linhas(True)[-1])

    def test_delimitadores(self):
        for separador in (",", ";", "\t", "|"):
            with self.subTest(separador=separador):
                leitor, deslocamento = lote.preparar_leitor_csv(criar_csv(separador=separador), "demo")
                self.assertEqual(deslocamento, 0)
                self.assertEqual(len(list(leitor)), 3)

    def test_linhas_fisicas_com_sep_e_multilinha(self):
        texto = "\nsep=;\n" + criar_csv().replace(
            "Movimentação fictícia 001", '"Movimentação fictícia\nem duas linhas"',
        )
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "entrada.csv"
            caminho.write_text(texto, encoding="utf-8-sig", newline="")
            _, registros = lote.carregar_registros(caminho)
        self.assertEqual(registros[0]["linha_csv_inicio"], 4)
        self.assertEqual(registros[0]["linha_csv_fim"], 5)
        self.assertEqual(registros[1]["linha_csv_inicio"], 6)

    def test_cabecalhos_invalidos(self):
        for texto in ("", "coluna_desconhecida\nx", "sep=?\nx", "id;id\nx;y"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                lote.preparar_leitor_csv(texto, "demo")


class LoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.registros = [
            {"registro": i, "linha_csv_inicio": i + 1, "linha_csv_fim": i + 1, "dados": linha}
            for i, linha in enumerate(criar_linhas(), 1)
        ]
        self.diario = lote.Diario(self.raiz, self.registros)
        self.addCleanup(lambda: self.diario.fechar())

    def test_retomada_marca_tentativas_incertas(self):
        self.diario.registrar(1, "SALVANDO")
        self.diario.registrar(2, "EM_PROCESSAMENTO")
        self.diario.fechar()
        self.diario = lote.Diario(self.raiz, self.registros)
        self.assertEqual(self.diario.obter(1)["status"], "VERIFICAR_NO_EXTRATO")
        self.assertEqual(self.diario.obter(2)["status"], "INTERROMPIDO_ANTES_DE_SALVAR")

    def test_repeticao_recusa_sucesso_e_incerteza(self):
        for status in ("SALVO_NOTIFICACAO", "VERIFICAR_NO_EXTRATO", "SALVANDO"):
            self.diario.registrar(1, status)
            with self.subTest(status=status), self.assertRaises(ValueError):
                lote.liberar_registro(self.diario, 1)

    def test_repeticao_libera_somente_erro(self):
        self.diario.registrar(1, "ERRO_LEITURA")
        lote.liberar_registro(self.diario, 1)
        self.assertEqual(self.diario.obter(1)["status"], "NAO_PROCESSADO")

    def test_valor_nao_finito_e_campos_incompletos_nao_abrem_formulario(self):
        for valor in ("NaN", "Infinity", "-Infinity"):
            self.registros[0]["dados"]["Valor"] = valor
            self.diario.registrar(1, "NAO_PROCESSADO")
            interface = InterfaceSimulada()
            lote.processar(self.registros[:1], self.diario, None, True, interface)
            self.assertEqual(self.diario.obter(1)["status"], "ERRO_LEITURA")
            self.assertEqual(interface.abertos, [])
        self.registros[0]["dados"]["Valor"] = None
        self.diario.registrar(1, "NAO_PROCESSADO")
        interface = InterfaceSimulada()
        lote.processar(self.registros[:1], self.diario, None, True, interface)
        self.assertEqual(interface.abertos, [])
        self.assertEqual(self.diario.obter(1)["status"], "ERRO_LEITURA")

    def test_simulacao_nunca_clica_salvar(self):
        interface = InterfaceSimulada()
        lote.processar(self.registros, self.diario, None, True, interface)
        self.assertEqual(len(interface.preenchidos), 3)
        self.assertEqual({r["status"] for r in self.diario.todos()}, {"TESTE_SEM_SALVAR"})

    def test_falha_apos_clique_nao_reenvia(self):
        interface = Mock(wraps=InterfaceSimulada())
        botao = Mock()
        interface.preparar_salvamento = Mock(return_value=(None, botao))
        interface.observar_notificacoes = Mock()
        interface.confirmar_salvamento = Mock(side_effect=RuntimeError("Falha fictícia"))
        interface.encerrar_observador = Mock()
        lote.processar(self.registros[:1], self.diario, None, False, interface)
        self.assertEqual(self.diario.obter(1)["status"], "VERIFICAR_NO_EXTRATO")
        lote.processar(self.registros[:1], self.diario, None, False, interface)
        botao.click.assert_called_once()

    def test_falha_no_diario_impede_clique(self):
        interface = Mock(wraps=InterfaceSimulada())
        botao = Mock()
        interface.preparar_salvamento = Mock(return_value=(None, botao))
        interface.observar_notificacoes = Mock()
        registrar = self.diario.registrar

        def falhar_antes_de_salvar(numero, status, *args, **kwargs):
            if status == "SALVANDO":
                raise OSError("Falha fictícia de armazenamento")
            return registrar(numero, status, *args, **kwargs)

        with patch.object(self.diario, "registrar", side_effect=falhar_antes_de_salvar):
            with self.assertRaises(OSError):
                lote.processar(self.registros[:1], self.diario, None, False, interface)
        botao.click.assert_not_called()

    def test_exportacao_protege_formulas(self):
        self.diario.registrar(1, "ERRO", mensagem="=1+1")
        self.diario.exportar()
        for nome in ("resultados.csv", "pendencias.csv", "eventos.csv"):
            with (self.raiz / nome).open(encoding="utf-8-sig", newline="") as arquivo:
                linha = next(csv.DictReader(arquivo, delimiter=";"))
            self.assertEqual(linha["mensagem"], "'=1+1")

    def test_pendencias_bloqueiam_id_duplicado_e_historico_salvo(self):
        self.diario.registrar(1, "ERRO")
        relatorio = [self.diario.obter(1)]
        historico = {r["registro"]: r for r in self.diario.todos()}
        selecionados, _ = selecionar_pendencias(relatorio, self.registros, historico)
        self.assertEqual([r["registro"] for r in selecionados], [1])
        selecionados, _ = selecionar_pendencias(relatorio, self.registros * 2, historico)
        self.assertEqual(selecionados, [])
        historico[1]["status"] = "SALVO_NOTIFICACAO"
        selecionados, _ = selecionar_pendencias(relatorio, self.registros, historico)
        self.assertEqual(selecionados, [])

    def test_pendencias_recusam_dados_alterados(self):
        self.diario.registrar(1, "ERRO")
        relatorio = [self.diario.obter(1)]
        relatorio[0]["valor"] = "999,99"
        historico = {r["registro"]: r for r in self.diario.todos()}
        selecionados, _ = selecionar_pendencias(relatorio, self.registros, historico)
        self.assertEqual(selecionados, [])


class SegurancaTests(unittest.TestCase):
    def test_acessos_reais_desativados(self):
        with patch("selenium.webdriver.Chrome") as chrome:
            with self.assertRaises(RuntimeError):
                automacao.criar_navegador()
            chrome.assert_not_called()
        with self.assertRaises(RuntimeError):
            acesso_sistema.entrar_no_extrato(None)

    def test_demo_com_rede_bloqueada(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("Rede proibida")):
            with patch("selenium.webdriver.Chrome", side_effect=AssertionError("Chrome proibido")):
                resultados = executar_demo(True)
        self.assertEqual([r["status"] for r in resultados], ["TESTE_SEM_SALVAR"] * 3 + ["ERRO_LEITURA"])
        self.assertTrue(all(r["id_original"].startswith("DEMO-") for r in resultados))

    def test_notificacoes_exigem_sucesso_explicito(self):
        self.assertFalse(lote.mensagem_de_sucesso({"eventos": []}))
        self.assertTrue(lote.mensagem_de_sucesso({"eventos": [
            {"titulo": "Finanças", "mensagem": "Transação salva com sucesso."},
        ]}))
        for estado in (None, {"excesso": True}, {"eventos": [
            {"titulo": "Finanças", "mensagem": "Mensagem fictícia desconhecida"},
        ]}):
            with self.subTest(estado=estado), self.assertRaises(RuntimeError):
                lote.mensagem_de_sucesso(estado)


if __name__ == "__main__":
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main()

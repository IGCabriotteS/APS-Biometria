"""Testes de política de acesso, banco, prova de vida, sessão e bloqueio."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

import _ambiente  # noqa: F401
from cofre import autenticacao as aut
from cofre import config, politica
from cofre.autenticacao import ControleBloqueio, SessaoAutenticacao
from cofre.banco import Banco
from cofre.classificacao import Previsao
from cofre.erros import RegraDeNegocio, SistemaBloqueado, UsuarioInvalido
from cofre.pipeline import Resultado
from cofre.prova_vida import DesafioPiscada


def _banco():
    tmp = tempfile.mkdtemp(dir=_ambiente.PASTA_DADOS)
    return Banco(Path(tmp) / "t.db")


class TestPolitica(unittest.TestCase):
    def setUp(self):
        self.banco = _banco()
        self.comp = {c["nome"]: c for c in self.banco.listar_compartimentos()}
        self.geral = self.comp["Arquivo Geral de Relatórios Ambientais"]
        self.agro = self.comp["Laboratório de Toxinas Agrícolas"]
        self.residuos = self.comp["Laboratório de Resíduos Perigosos"]
        self.central = self.comp["Câmara Central de Toxinas de Alto Risco"]

    def _usuario(self, nome, nivel, divisao=None):
        uid = self.banco.criar_usuario(nome, "cargo", nivel, divisao)
        return self.banco.obter_usuario(uid)

    def test_matriz_de_permissoes(self):
        geral = self._usuario("Maria Geral", 1)
        diretor = self._usuario("Dora Diretora", 2, "Agrotóxicos e Biocidas")
        ministro = self._usuario("Marina Ministra", 3)
        esperado = {
            # (usuário, compartimento): permitido
            ("geral", "geral"): True, ("geral", "agro"): False,
            ("geral", "residuos"): False, ("geral", "central"): False,
            ("diretor", "geral"): True, ("diretor", "agro"): True,
            ("diretor", "residuos"): False, ("diretor", "central"): False,
            ("ministro", "geral"): True, ("ministro", "agro"): True,
            ("ministro", "residuos"): True, ("ministro", "central"): True,
        }
        usuarios = {"geral": geral, "diretor": diretor, "ministro": ministro}
        comps = {"geral": self.geral, "agro": self.agro,
                 "residuos": self.residuos, "central": self.central}
        for (u, c), quer in esperado.items():
            decisao = politica.decidir(usuarios[u], comps[c])
            self.assertEqual(decisao.permitido, quer, f"{u} -> {c}: {decisao.motivo}")

    def test_usuario_desativado_e_negado(self):
        u = self._usuario("Pedro Antigo", 1)
        self.banco.desativar_usuario(u["id"])
        self.assertFalse(politica.decidir(self.banco.obter_usuario(u["id"]), self.geral).permitido)


class TestBanco(unittest.TestCase):
    def setUp(self):
        self.banco = _banco()

    def test_validacoes_de_cadastro(self):
        with self.assertRaises(UsuarioInvalido):
            self.banco.criar_usuario("Al", "x", 1)
        with self.assertRaises(UsuarioInvalido):
            self.banco.criar_usuario("Fulano de Tal", "x", 9)
        with self.assertRaises(UsuarioInvalido):
            self.banco.criar_usuario("Diretor Sem Divisao", "x", 2)
        self.banco.criar_usuario("Ana Souza", "x", 1)
        with self.assertRaises(UsuarioInvalido):          # nome duplicado (sem caixa)
            self.banco.criar_usuario("ana souza", "x", 1)

    def test_nivel_3_e_exclusivo_do_ministro(self):
        uid = self.banco.criar_usuario("Marina Ministra", "Ministra", 3)
        with self.assertRaises(RegraDeNegocio):
            self.banco.criar_usuario("Outro Ministro", "x", 3)
        self.banco.desativar_usuario(uid)
        self.banco.criar_usuario("Outro Ministro", "x", 3)   # agora é permitido

    def test_historico_encadeado_detecta_adulteracao(self):
        for i in range(4):
            self.banco.registrar_acesso(1, "Ana", "Arquivo", "PERMITIDO", "ok", 0.1 + i / 100)
        self.assertEqual(self.banco.verificar_integridade(), (True, None))
        self.banco._con.execute("UPDATE acessos SET resultado='NEGADO' WHERE id=2")   # era PERMITIDO
        self.banco._con.execute("UPDATE acessos SET motivo='editado' WHERE id=3")
        self.banco._con.commit()
        ok, linha = self.banco.verificar_integridade()
        self.assertFalse(ok)
        self.assertEqual(linha, 2)      # a PRIMEIRA linha adulterada é a 2 (a 3 também foi)

    def test_apagar_as_ultimas_linhas_e_detectado_pela_ancora(self):
        for i in range(4):
            self.banco.registrar_acesso(None, "x", "c", "NEGADO", "m")
        self.assertTrue(self.banco.verificar_integridade()[0])
        self.banco._con.execute("DELETE FROM acessos WHERE id IN (3, 4)")   # corta o fim
        self.banco._con.commit()
        ok, linha = self.banco.verificar_integridade()
        self.assertFalse(ok)
        self.assertEqual(linha, 3)      # restam as linhas 1 e 2: a ausente é a 3

    def test_ancora_ausente_com_historico_falha_fechado(self):
        # apagar o fim do histórico E as chaves da âncora não pode parecer "íntegro"
        for i in range(4):
            self.banco.registrar_acesso(None, "x", "c", "NEGADO", "m")
        self.banco._con.execute("DELETE FROM acessos WHERE id IN (3, 4)")
        self.banco._con.execute("DELETE FROM parametros WHERE chave IN ('log_total', 'log_ultimo_hash')")
        self.banco._con.commit()
        self.assertFalse(self.banco.verificar_integridade()[0])

    def test_historico_vazio_e_integro(self):
        self.assertEqual(self.banco.verificar_integridade(), (True, None))

    def test_eventos_administrativos_entram_no_historico(self):
        self.banco.registrar_evento("Marina", "usuário 'X' cadastrado")
        linha = self.banco.listar_acessos()[0]
        self.assertEqual(linha["resultado"], "ADMIN")
        self.assertTrue(self.banco.verificar_integridade()[0])

    def test_apagar_linha_quebra_a_cadeia(self):
        for i in range(3):
            self.banco.registrar_acesso(None, "x", "c", "NEGADO", "m")
        self.banco._con.execute("DELETE FROM acessos WHERE id=2")
        self.banco._con.commit()
        self.assertFalse(self.banco.verificar_integridade()[0])


class TestProvaDeVida(unittest.TestCase):
    def test_piscada_completa_conclui(self):
        d = DesafioPiscada()
        for olhos in (2, 2, 2, 0, 0, 2, 2):
            d.registrar(olhos)
        self.assertTrue(d.concluido)

    def test_um_unico_quadro_sem_olhos_nao_e_piscada(self):
        # falha isolada do detector de Haar não pode valer como piscada
        d = DesafioPiscada()
        for olhos in (2, 2, 2, 0, 2, 2, 2, 2, 0, 2, 2, 2):
            d.registrar(olhos)
        self.assertFalse(d.concluido)

    def test_olhos_sempre_abertos_nao_conclui(self):
        d = DesafioPiscada()
        for _ in range(50):
            d.registrar(2)
        self.assertFalse(d.concluido)           # foto parada: nunca pisca

    def test_perder_o_rosto_reinicia_o_desafio(self):
        d = DesafioPiscada()
        for olhos in (2, 2, 2, 0):
            d.registrar(olhos)
        d.registrar(None)
        self.assertEqual(d.estado, DesafioPiscada.AGUARDA_ABERTOS)


class _ReconhecedorFalso:
    """Devolve previsões pré-programadas: (usuario_id, distancia, segunda)."""
    def __init__(self, roteiro):
        self.roteiro = list(roteiro)

    def prever(self, vetor):
        uid, dist, seg = self.roteiro.pop(0) if len(self.roteiro) > 1 else self.roteiro[0]
        return Previsao(uid, dist, seg, dist <= config.LIMIAR_DISTANCIA)


def _resultado(olhos=2, rosto=True, intruso=False, ok=True):
    r = Resultado()
    if rosto:
        r.caixa, r.caixas = (0, 0, 100, 100), [(0, 0, 100, 100)]
    r.intruso, r.qualidade_ok, r.olhos = intruso, ok, olhos
    r.motivos = [] if ok else ["imagem desfocada"]
    r.vetor = np.zeros(59)
    return r


class _Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TestSessao(unittest.TestCase):
    def _sessao(self, roteiro, vida=False, relogio=None):
        return SessaoAutenticacao(_ReconhecedorFalso(roteiro), exigir_vida=vida,
                                  relogio=relogio or _Relogio())

    def test_identifica_apos_quadros_consistentes(self):
        s = self._sessao([(7, 0.20, 0.50)])
        estados = [s.processar(_resultado()) for _ in range(config.QUADROS_CONFIRMACAO)]
        self.assertEqual(estados[-1].fase, aut.IDENTIFICADO)
        self.assertEqual(estados[-1].usuario_id, 7)
        self.assertNotEqual(estados[0].fase, aut.IDENTIFICADO)   # um quadro só não basta

    def test_distancia_alta_nunca_identifica_e_estoura_tempo(self):
        rel = _Relogio()
        s = self._sessao([(7, 0.90, 1.0)], relogio=rel)
        for _ in range(5):
            self.assertNotEqual(s.processar(_resultado()).fase, aut.IDENTIFICADO)
        rel.t = config.TEMPO_MAX_AUTENTICACAO + 1
        e = s.processar(_resultado())
        self.assertEqual(e.fase, aut.FALHA)
        self.assertIn("não reconhecido", e.motivo_falha)

    def test_dois_usuarios_parecidos_geram_ambiguidade(self):
        s = self._sessao([(7, 0.30, 0.305)])       # margem ~1,6% < mínima
        for _ in range(config.QUADROS_JANELA):
            self.assertNotEqual(s.processar(_resultado()).fase, aut.IDENTIFICADO)

    def test_segundo_rosto_impede_a_autenticacao(self):
        rel = _Relogio()
        s = self._sessao([(7, 0.20, 0.50)], relogio=rel)
        for _ in range(20):
            self.assertNotEqual(s.processar(_resultado(intruso=True)).fase, aut.IDENTIFICADO)
        rel.t = 100
        self.assertIn("mais de um rosto", s.processar(_resultado(intruso=True)).motivo_falha)

    def test_prova_de_vida_exige_piscada(self):
        rel = _Relogio()
        s = self._sessao([(7, 0.20, 0.50)], vida=True, relogio=rel)
        fase = None
        for _ in range(config.QUADROS_CONFIRMACAO):
            fase = s.processar(_resultado(olhos=2)).fase
        self.assertEqual(fase, aut.PROVA_DE_VIDA)
        for olhos in (2, 2, 0, 0, 2, 2):
            estado = s.processar(_resultado(olhos=olhos))
        self.assertEqual(estado.fase, aut.IDENTIFICADO)

    def test_rosto_desconhecido_que_pisca_apos_a_identificacao_nao_conclui(self):
        # troca de foto: identidade confirmada, depois entra um rosto NÃO reconhecido
        # que pisca. A prova de vida concluída não pode valer para a identidade antiga.
        rel = _Relogio()
        roteiro = [(7, 0.20, 0.50)] * config.QUADROS_CONFIRMACAO + [(7, 0.90, 1.0)]
        s = self._sessao(roteiro, vida=True, relogio=rel)
        for _ in range(config.QUADROS_CONFIRMACAO):
            s.processar(_resultado(olhos=2))
        for olhos in (2, 2, 2, 0, 0, 2, 2, 2, 2, 2):
            estado = s.processar(_resultado(olhos=olhos))
            self.assertNotEqual(estado.fase, aut.IDENTIFICADO)
        rel.t = config.TEMPO_MAX_PISCADA + 1
        self.assertEqual(s.processar(_resultado(olhos=2)).fase, aut.FALHA)

    def test_foto_rosto_proprio_piscando_foto_de_novo_nao_conclui(self):
        # foto da vítima identifica; um rosto DESCONHECIDO aparece de olhos abertos e pisca;
        # a foto volta. Os quadros de olhos abertos precisam ser do mesmo usuário, então a
        # presença do desconhecido reinicia o desafio e a sequência não conclui.
        n = config.QUADROS_CONFIRMACAO
        roteiro = ([(7, 0.20, 0.50)] * n            # foto: identifica
                   + [(7, 0.90, 1.0)] * 7           # desconhecido: 3 abertos, 2 fechados, 2 abertos
                   + [(7, 0.20, 0.50)] * 3)         # foto de volta
        rel = _Relogio()
        s = self._sessao(roteiro, vida=True, relogio=rel)
        for _ in range(n):
            s.processar(_resultado(olhos=2))
        for olhos in (2, 2, 2, 0, 0, 2, 2, 2, 2, 2):
            estado = s.processar(_resultado(olhos=olhos))
            self.assertNotEqual(estado.fase, aut.IDENTIFICADO)

    def test_foto_parada_falha_na_prova_de_vida(self):
        rel = _Relogio()
        s = self._sessao([(7, 0.20, 0.50)], vida=True, relogio=rel)
        for _ in range(config.QUADROS_CONFIRMACAO + 5):
            s.processar(_resultado(olhos=2))
        rel.t = config.TEMPO_MAX_PISCADA + 1
        estado = s.processar(_resultado(olhos=2))
        self.assertEqual(estado.fase, aut.FALHA)
        self.assertIn("prova de vida", estado.motivo_falha)

    def test_troca_de_pessoa_durante_a_prova_de_vida(self):
        roteiro = [(7, 0.20, 0.50)] * config.QUADROS_CONFIRMACAO + [(8, 0.20, 0.50)]
        s = self._sessao(roteiro, vida=True)
        for _ in range(config.QUADROS_CONFIRMACAO):
            s.processar(_resultado(olhos=2))
        estados = [s.processar(_resultado(olhos=2)) for _ in range(4)]
        self.assertEqual(estados[-1].fase, aut.FALHA)
        self.assertIn("troca de pessoa", estados[-1].motivo_falha)


class TestBloqueio(unittest.TestCase):
    def test_bloqueia_apos_tres_falhas_e_libera_depois(self):
        banco = _banco()
        relogio = _Relogio()
        relogio.t = 1000.0
        ctl = ControleBloqueio(banco, relogio=relogio)
        self.assertFalse(ctl.registrar_falha())
        self.assertFalse(ctl.registrar_falha())
        self.assertTrue(ctl.registrar_falha())
        with self.assertRaises(SistemaBloqueado):
            ctl.exigir_liberado()
        relogio.t += config.SEGUNDOS_BLOQUEIO + 1
        ctl.exigir_liberado()                       # liberado

    def test_sucesso_zera_o_contador(self):
        ctl = ControleBloqueio(_banco(), relogio=_Relogio())
        ctl.registrar_falha()
        ctl.registrar_falha()
        ctl.registrar_sucesso()
        self.assertFalse(ctl.registrar_falha())


if __name__ == "__main__":
    unittest.main()

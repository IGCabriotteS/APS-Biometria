"""Teste de ponta a ponta sem câmera, com fotos da base ORL (se estiver na pasta).

Cadastra três pessoas (uma por nível), autentica por arquivo e confere
permissões, recusa de intruso, registro de histórico e bloqueio do terminal.
"""

import unittest

import _ambiente  # noqa: F401
from cofre import config
from cofre.aquisicao import carregar_imagem
from cofre.banco import Banco
from cofre.erros import SistemaBloqueado
from cofre.servico import Cofre

PESSOAS = {"ministro": "s01", "diretor": "s03", "geral": "s05", "intruso": "s02"}
CADASTRO = range(1, 8)       # imagens 1..7 para cadastro
SONDA = "08.png"             # imagem não usada no cadastro


def _caminho(pessoa, arquivo):
    return _ambiente.BASE_ORL / pessoa / arquivo


@unittest.skipUnless(_ambiente.BASE_ORL.is_dir(), "base ORL não encontrada")
class TestIntegracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cofre = Cofre(Banco(_ambiente.PASTA_DADOS / "integracao.db"))
        pip = cls.cofre.pipeline

        def faces(pessoa):
            return [pip.processar_recorte(carregar_imagem(_caminho(pessoa, f"{i:02d}.png"))).normalizada
                    for i in CADASTRO]

        cls.cofre.cadastrar("Marina Ministra", "Ministra do Meio Ambiente", 3, None,
                            faces(PESSOAS["ministro"]))
        cls.cofre.cadastrar("Dora Diretora", "Diretora", 2, "Agrotóxicos e Biocidas",
                            faces(PESSOAS["diretor"]))
        cls.cofre.cadastrar("Gabriel Geral", "Analista", 1, None, faces(PESSOAS["geral"]))
        comps = {c["nome"]: c["id"] for c in cls.cofre.banco.listar_compartimentos()}
        cls.geral = comps["Arquivo Geral de Relatórios Ambientais"]
        cls.agro = comps["Laboratório de Toxinas Agrícolas"]
        cls.residuos = comps["Laboratório de Resíduos Perigosos"]
        cls.central = comps["Câmara Central de Toxinas de Alto Risco"]

    def _entrar(self, quem, comp):
        return self.cofre.autenticar_arquivo(_caminho(PESSOAS[quem], SONDA), comp, so_recorte=True)

    def setUp(self):
        # A base ORL tem muito mais variação de pose do que uma webcam na mesma
        # sessão: as distâncias legítimas ficam em 0,30-0,51 e as de intrusos em
        # 0,56-0,59. O teste verifica o FLUXO (política, histórico, bloqueio),
        # não a taxa de acerto, que é medida em avaliacao.py; por isso usa um
        # limiar que separa as duas faixas em vez do limiar de produção.
        if self.cofre.reconhecedor is not None:
            self.cofre.reconhecedor.limiar = 0.53
        self.cofre.banco.definir_parametro("bloqueio_ate", 0)
        self.cofre.banco.definir_parametro("falhas_consecutivas", 0)

    def test_modelo_foi_treinado_e_tem_tres_usuarios(self):
        self.assertTrue(self.cofre.modelo_pronto())
        self.assertEqual(len(self.cofre.reconhecedor.usuarios), 3)

    def test_ministro_entra_em_todos_os_compartimentos(self):
        for comp in (self.geral, self.agro, self.residuos, self.central):
            r = self._entrar("ministro", comp)
            self.assertTrue(r["permitido"], r)
            self.assertEqual(r["usuario"], "Marina Ministra")

    def test_diretor_so_na_propria_divisao(self):
        self.assertTrue(self._entrar("diretor", self.agro)["permitido"])
        self.assertFalse(self._entrar("diretor", self.residuos)["permitido"])
        self.assertFalse(self._entrar("diretor", self.central)["permitido"])

    def test_geral_so_no_arquivo_geral(self):
        self.assertTrue(self._entrar("geral", self.geral)["permitido"])
        self.assertFalse(self._entrar("geral", self.agro)["permitido"])
        self.assertFalse(self._entrar("geral", self.central)["permitido"])

    def test_intruso_e_negado_e_sem_identidade(self):
        r = self._entrar("intruso", self.central)
        self.assertFalse(r["permitido"])
        self.assertIsNone(r["usuario"])

    def test_bloqueio_apos_falhas_consecutivas(self):
        for _ in range(config.TENTATIVAS_ATE_BLOQUEIO):
            self.assertFalse(self._entrar("intruso", self.central)["permitido"])
        with self.assertRaises(SistemaBloqueado):
            self._entrar("ministro", self.central)

    def test_historico_registra_tudo_e_continua_integro(self):
        self._entrar("ministro", self.central)
        self._entrar("intruso", self.central)
        acessos = self.cofre.banco.listar_acessos()
        self.assertGreater(len(acessos), 0)
        self.assertEqual(self.cofre.banco.verificar_integridade(), (True, None))

    def test_negacao_de_politica_nao_bloqueia_o_terminal(self):
        # quem é reconhecido mas pede um compartimento proibido é negado e registrado,
        # sem acionar o bloqueio (que protege o reconhecimento contra tentativas em série)
        for comp in (self.residuos, self.central, self.residuos, self.central):
            self.assertFalse(self._entrar("diretor", comp)["permitido"])
        self.cofre.bloqueio.exigir_liberado()                     # não levanta
        self.assertTrue(self._entrar("diretor", self.agro)["permitido"])

    def test_motivo_por_arquivo_fica_marcado_no_historico(self):
        self._entrar("ministro", self.central)
        ultimo = self.cofre.banco.listar_acessos()[-1]
        self.assertIn("sem prova de vida", ultimo["motivo"])

    def test_ministro_nao_pode_ser_removido_pelo_menu(self):
        from cofre.erros import RegraDeNegocio
        ministro = next(u for u in self.cofre.banco.listar_usuarios() if u["nivel"] == 3)
        with self.assertRaises(RegraDeNegocio):
            self.cofre.remover_usuario(ministro["id"])
        self.assertTrue(self.cofre.banco.obter_usuario(ministro["id"])["ativo"])

    def test_cadastro_e_remocao_aparecem_no_historico(self):
        eventos = [a for a in self.cofre.banco.listar_acessos() if a["resultado"] == "ADMIN"]
        self.assertTrue(any("cadastrado" in e["motivo"] for e in eventos))

    def test_modelo_adulterado_e_recuperavel_por_comando_local(self):
        from cofre import config as cfg
        from cofre.erros import ModeloIndisponivel
        try:
            with open(cfg.ARQUIVO_MODELO, "ab") as f:
                f.write(b"x")                                      # adultera o arquivo
            with self.assertRaises(ModeloIndisponivel) as ctx:
                self.cofre.carregar_modelo()
            self.assertIn("retreinar", str(ctx.exception))         # a mensagem diz o que fazer
        finally:
            self.cofre.retreinar_modelo()
        self.assertTrue(self.cofre.modelo_pronto())
        self.assertTrue(any("retreinado" in a["motivo"] for a in self.cofre.banco.listar_acessos()))

    def test_modelo_sem_impressao_digital_falha_fechado(self):
        from cofre.erros import ModeloIndisponivel
        hash_ok = self.cofre.banco.obter_parametro("hash_modelo")
        try:
            self.cofre.banco.definir_parametro("hash_modelo", "")
            with self.assertRaises(ModeloIndisponivel):
                self.cofre.carregar_modelo()
        finally:
            self.cofre.banco.definir_parametro("hash_modelo", hash_ok)
        self.assertTrue(self.cofre.modelo_pronto())

    def test_troca_de_ministro_e_atomica(self):
        # se o cadastro do novo ministro falhar, o antigo volta (ativo, com biometria e modelo)
        ministro = next(u for u in self.cofre.banco.listar_usuarios() if u["nivel"] == 3)
        antes = len(self.cofre.reconhecedor.usuarios) if self.cofre.reconhecedor else 3
        with self.assertRaises(Exception):
            self.cofre.trocar_ministro(ministro["id"], "Novo Ministro", "x", [])   # sem amostras
        depois = self.cofre.banco.obter_usuario(ministro["id"])
        self.assertTrue(depois["ativo"])
        self.assertTrue(self.cofre.modelo_pronto())
        self.assertEqual(len(self.cofre.reconhecedor.usuarios), antes)

    def test_remover_usuario_retira_o_acesso(self):
        uid = self.cofre.banco.criar_usuario("Temporario Teste", "x", 1)
        self.cofre.remover_usuario(uid)
        self.assertFalse(self.cofre.banco.obter_usuario(uid)["ativo"])


if __name__ == "__main__":
    unittest.main()

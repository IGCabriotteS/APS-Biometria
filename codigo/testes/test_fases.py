"""Testes das fases de pré-processamento, segmentação, características e classificação."""

import unittest

import numpy as np

import _ambiente  # noqa: F401  (deve vir antes dos imports de cofre)
from cofre import caracteristicas, classificacao, config, preprocessamento, segmentacao
from cofre.erros import ModeloIndisponivel


class TestCaracteristicas(unittest.TestCase):
    def test_codigo_lbp_de_bloco_conhecido(self):
        # Centro 50; vizinhos no sentido horário a partir do canto superior
        # esquerdo: 60 10 60 / 10 . 60 / 10 60 10 -> bits 1,0,1,1,0,1,0,0
        bloco = np.array([[60, 10, 60],
                          [10, 50, 60],
                          [10, 60, 10]], dtype=np.uint8)
        # ordem dos vizinhos: (0,0)=60 (0,1)=10 (0,2)=60 (1,2)=60 (2,2)=10 (2,1)=60 (2,0)=10 (1,0)=10
        # bits: 1 0 1 1 0 1 0 0 -> 10110100 = 180
        self.assertEqual(int(caracteristicas.imagem_lbp(bloco)[0, 0]), 0b10110100)

    def test_tabela_tem_58_uniformes_e_uma_classe_outros(self):
        tabela = caracteristicas.TABELA_UNIFORMES
        self.assertEqual(len(set(tabela.tolist())), 59)
        self.assertEqual(int((tabela == 58).sum()), 256 - 58)
        self.assertEqual(int(tabela[0b00000000]), int(tabela[0b00000000]))  # determinismo
        self.assertNotEqual(int(tabela[0b00000000]), 58)   # só zeros é uniforme
        self.assertEqual(int(tabela[0b01010101]), 58)      # muitas transições

    def test_vetor_tem_dimensao_e_soma_esperadas(self):
        rng = np.random.default_rng(0)
        face = rng.integers(0, 256, config.TAMANHO_FACE[::-1], dtype=np.uint8)
        v = caracteristicas.extrair(face)
        blocos = config.GRADE_BLOCOS[0] * config.GRADE_BLOCOS[1]
        self.assertEqual(v.shape, (blocos * 59,))
        self.assertAlmostEqual(float(v.sum()), blocos, places=6)  # cada bloco soma 1

    def test_lbp_e_invariante_a_brilho_aditivo(self):
        rng = np.random.default_rng(1)
        face = rng.integers(0, 150, (60, 60), dtype=np.uint8)
        np.testing.assert_array_equal(caracteristicas.imagem_lbp(face),
                                      caracteristicas.imagem_lbp(face + 50))


class TestPreProcessamento(unittest.TestCase):
    def test_normalizar_devolve_tamanho_padrao(self):
        face = np.full((150, 130), 120, np.uint8)
        saida = preprocessamento.normalizar_face(face)
        self.assertEqual(saida.shape, config.TAMANHO_FACE[::-1])

    def test_qualidade_reprova_escuro_claro_e_desfocado(self):
        rng = np.random.default_rng(2)
        bom = rng.integers(40, 200, (120, 120), dtype=np.uint8)
        self.assertTrue(preprocessamento.avaliar_qualidade(bom)[0])
        escuro = (bom // 8).astype(np.uint8)
        self.assertIn("imagem muito escura", preprocessamento.avaliar_qualidade(escuro)[1])
        claro = np.full((120, 120), 250, np.uint8)
        self.assertIn("imagem muito clara", preprocessamento.avaliar_qualidade(claro)[1])
        liso = np.full((120, 120), 120, np.uint8)
        self.assertIn("imagem desfocada", preprocessamento.avaliar_qualidade(liso)[1])


class TestSegmentacao(unittest.TestCase):
    def test_intruso_so_quando_segundo_rosto_e_comparavel(self):
        self.assertFalse(segmentacao.ha_intruso([(0, 0, 200, 200)]))
        self.assertFalse(segmentacao.ha_intruso([(0, 0, 200, 200), (0, 0, 90, 90)]))
        self.assertTrue(segmentacao.ha_intruso([(0, 0, 200, 200), (0, 0, 180, 180)]))

    def test_angulo_entre_olhos(self):
        olhos = [(10, 40, 20, 20), (70, 40, 20, 20)]          # mesma altura
        self.assertAlmostEqual(segmentacao.angulo_entre_olhos(olhos, 100), 0.0, places=5)
        inclinado = [(10, 40, 20, 20), (70, 50, 20, 20)]      # direito mais baixo
        self.assertGreater(segmentacao.angulo_entre_olhos(inclinado, 100), 5)
        colados = [(40, 40, 20, 20), (45, 40, 20, 20)]
        self.assertIsNone(segmentacao.angulo_entre_olhos(colados, 100))
        self.assertIsNone(segmentacao.angulo_entre_olhos(olhos[:1], 100))

    def test_mascara_zera_cantos_e_preserva_centro(self):
        face = np.full((100, 100), 200, np.uint8)
        m = segmentacao.mascara_eliptica(face)
        self.assertEqual(int(m[0, 0]), 0)
        self.assertEqual(int(m[50, 50]), 200)

    def test_recortar_respeita_bordas(self):
        img = np.zeros((100, 100), np.uint8)
        r = segmentacao.recortar(img, (80, 80, 40, 40))
        self.assertLessEqual(r.shape[0], 100)
        self.assertLessEqual(r.shape[1], 100)


class TestClassificacao(unittest.TestCase):
    def _modelo(self):
        rng = np.random.default_rng(3)
        centros = [rng.dirichlet(np.ones(59 * 64) * 0.3) for _ in range(3)]
        vetores, rotulos = [], []
        for uid, c in enumerate(centros, start=1):
            for _ in range(5):
                ruido = np.abs(c + rng.normal(0, 0.00003, c.shape))
                vetores.append(ruido / ruido.sum() * 64)
                rotulos.append(uid)
        vetores = np.array(vetores)
        return classificacao.Reconhecedor(limiar=0.2).treinar(vetores, rotulos), centros

    def test_distancia_zero_para_iguais_e_simetrica(self):
        a = np.random.default_rng(4).dirichlet(np.ones(59))
        b = np.random.default_rng(5).dirichlet(np.ones(59))
        self.assertAlmostEqual(float(classificacao.distancia_qui_quadrado(a, a)), 0.0)
        self.assertAlmostEqual(float(classificacao.distancia_qui_quadrado(a, b)),
                               float(classificacao.distancia_qui_quadrado(b, a)))

    def test_reconhece_usuario_cadastrado_e_rejeita_desconhecido(self):
        modelo, centros = self._modelo()
        consulta = centros[1] / centros[1].sum() * 64
        previsao = modelo.prever(consulta)
        self.assertEqual(previsao.usuario_id, 2)
        self.assertTrue(previsao.aceito)
        estranho = np.random.default_rng(99).dirichlet(np.ones(59 * 64) * 0.3) * 64
        self.assertFalse(modelo.prever(estranho).aceito)

    def test_modelo_nao_treinado_levanta_erro(self):
        with self.assertRaises(ModeloIndisponivel):
            classificacao.Reconhecedor().prever(np.zeros(59))

    def test_salvar_carregar_e_deteccao_de_adulteracao(self):
        import tempfile
        from pathlib import Path
        modelo, _ = self._modelo()
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.npz"
            h = modelo.salvar(caminho)
            carregado = classificacao.Reconhecedor.carregar(caminho, hash_esperado=h)
            self.assertEqual(carregado.usuarios, [1, 2, 3])
            with open(caminho, "ab") as f:
                f.write(b"x")                     # adultera o arquivo
            with self.assertRaises(ModeloIndisponivel):
                classificacao.Reconhecedor.carregar(caminho, hash_esperado=h)

    def test_confirmador_exige_consistencia(self):
        c = classificacao.Confirmador(janela=5, necessarios=3)
        for voto in (1, None, 1, 2):
            self.assertIsNone(c.registrar(voto))
        self.assertEqual(c.registrar(1), 1)
        c.reiniciar()
        self.assertIsNone(c.confirmado())


if __name__ == "__main__":
    unittest.main()

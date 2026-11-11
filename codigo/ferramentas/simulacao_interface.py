"""Roda os fluxos de CÂMERA da interface (cadastro, autenticação, prova de vida)
com uma câmera simulada, sem janelas e sem pessoas.

A câmera simulada entrega quadros 640x480 montados com rostos da base ORL
ampliados. Serve para pegar erros de programação nos caminhos que só rodam com
câmera (que os testes automatizados não cobrem). Não mede desempenho de
reconhecimento: a ORL não tem a aparência de uma foto de webcam.

Uso (dentro da pasta `codigo`):  python ferramentas/simulacao_interface.py ..\\base_teste\\orl
"""

import os
import sys
import tempfile
from pathlib import Path

DADOS = tempfile.mkdtemp(prefix="cofre_sim_")
os.environ["COFRE_DADOS"] = DADOS
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from cofre import config, interface  # noqa: E402
from cofre.aquisicao import carregar_imagem  # noqa: E402
from cofre.servico import ADMINISTRACAO, Cofre  # noqa: E402

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "../base_teste/orl")


def quadro_de_rosto(imagem64, olhos_fechados=False, lado=260):
    """Monta um quadro 640x480 com o rosto ampliado no centro."""
    rosto = cv2.resize(imagem64, (lado, lado), interpolation=cv2.INTER_CUBIC)
    if olhos_fechados:
        faixa = rosto[int(lado * 0.28):int(lado * 0.46), :]
        faixa[:] = int(np.median(rosto[int(lado * 0.2):int(lado * 0.6), :]))
        cv2.line(rosto, (int(lado * 0.2), int(lado * 0.37)), (int(lado * 0.8), int(lado * 0.37)), 40, 2)
    fundo = np.full((480, 640), 120, np.uint8)
    y0, x0 = (480 - lado) // 2, (640 - lado) // 2
    fundo[y0:y0 + lado, x0:x0 + lado] = rosto
    return cv2.cvtColor(fundo, cv2.COLOR_GRAY2BGR)


class CameraFalsa:
    """Entrega quadros de uma lista (repete a última ao acabar)."""
    quadros = []

    def __init__(self, *a, **k):
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def ler(self):
        q = self.quadros[min(self._i, len(self.quadros) - 1)]
        self._i += 1
        return q


def carregar_pessoa(n):
    pasta = BASE / f"s{n:02d}"
    return [carregar_imagem(f, cinza=True) for f in sorted(pasta.glob("*.png"))]


def silenciar_janelas():
    interface.cv2.imshow = lambda *a, **k: None
    interface.cv2.waitKey = lambda *a, **k: -1
    interface.cv2.destroyAllWindows = lambda *a, **k: None
    interface.cv2.getWindowProperty = lambda *a, **k: 1.0
    interface.Camera = CameraFalsa


def main():
    silenciar_janelas()
    cofre = Cofre()
    pip = cofre.pipeline

    pessoas = {"ministro": carregar_pessoa(1), "diretor": carregar_pessoa(3), "geral": carregar_pessoa(5),
               "intruso": carregar_pessoa(2)}
    # 1) detecção de rosto nos quadros simulados
    detectados = sum(pip.processar(quadro_de_rosto(im)).tem_rosto for im in pessoas["ministro"])
    print(f"1) quadros simulados com rosto detectado: {detectados}/10")
    if detectados < 7:
        print("   A detecção falhou nos quadros simulados; a simulação não é aplicável.")
        return 1

    # 2) cadastro pelo fluxo de câmera (25 amostras)
    cadastros = {"ministro": ("Marina Ministra", "Ministra", 3, None),
                 "diretor": ("Dora Diretora", "Diretora", 2, "Agrotóxicos e Biocidas"),
                 "geral": ("Gabriel Geral", "Analista", 1, None)}
    for chave, dados in cadastros.items():
        CameraFalsa.quadros = [quadro_de_rosto(im) for im in pessoas[chave][:8]] * 4
        faces = interface.capturar_amostras(cofre)
        assert faces is not None and len(faces) == config.AMOSTRAS_POR_CADASTRO, f"captura {chave}: {faces and len(faces)}"
        uid = cofre.cadastrar(*dados, faces)
        print(f"2) {chave}: cadastrado (id {uid}) com {len(faces)} amostras pelo fluxo de câmera")

    comp = {c["nome"]: c["id"] for c in cofre.banco.listar_compartimentos()}
    central = comp["Câmara Central de Toxinas de Alto Risco"]
    agro = comp["Laboratório de Toxinas Agrícolas"]
    cofre.reconhecedor.limiar = 0.53   # ORL tem mais variação que a webcam (ver testes de integração)

    def tentar(chave, compartimento, vida, fechar_olhos=False):
        config.EXIGIR_PROVA_DE_VIDA = vida
        aberto = [quadro_de_rosto(im) for im in pessoas[chave][7:10]]
        seq = aberto * 6
        if fechar_olhos:   # piscada simulada no meio da sequência
            fechado = [quadro_de_rosto(im, olhos_fechados=True) for im in pessoas[chave][7:10]]
            seq = aberto * 5 + fechado[:2] + aberto * 8
        CameraFalsa.quadros = seq
        cofre.banco.definir_parametro("bloqueio_ate", 0)
        cofre.banco.definir_parametro("falhas_consecutivas", 0)
        return interface.autenticar_ao_vivo(cofre, compartimento)

    # 3) autenticação sem prova de vida
    ok, usuario, motivo = tentar("ministro", central, vida=False)
    print(f"3) ministro -> câmara central (sem prova de vida): permitido={ok} ({motivo})")
    assert ok and usuario["nome"] == "Marina Ministra"
    ok, usuario, motivo = tentar("diretor", central, vida=False)
    print(f"   diretor -> câmara central: permitido={ok} ({motivo})")
    assert not ok
    ok, usuario, motivo = tentar("diretor", agro, vida=False)
    print(f"   diretor -> laboratório da divisão: permitido={ok} ({motivo})")
    assert ok
    ok, usuario, motivo = tentar("intruso", central, vida=False)
    print(f"   intruso -> câmara central: permitido={ok} ({motivo})")
    assert not ok and usuario is None

    # 4) prova de vida
    ok, usuario, motivo = tentar("ministro", central, vida=True, fechar_olhos=False)
    print(f"4) com prova de vida e SEM piscada (foto parada): permitido={ok} ({motivo})")
    ok_piscou, usuario, motivo2 = tentar("ministro", central, vida=True, fechar_olhos=True)
    print(f"   com prova de vida e piscada simulada: permitido={ok_piscou} ({motivo2})")

    # 5) cadastro/remoção
    cofre.remover_usuario(cofre.banco.listar_usuarios()[-1]["id"])
    print("5) remoção de usuário: ok; ativos agora:", cofre.banco.contar_ativos())
    print("6) integridade do histórico:", cofre.banco.verificar_integridade())
    from cofre import avaliacao
    print("7) calibração com as amostras de cadastro:")
    print(avaliacao.resumo_calibracao(avaliacao.calibrar_com_cadastros(cofre.banco)))
    config.EXIGIR_PROVA_DE_VIDA = True
    return 0


if __name__ == "__main__":
    sys.exit(main())

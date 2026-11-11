"""Fase 1 - Aquisição da imagem (sensor).

O enunciado pede reconhecimento em tempo real por câmera, mas admite imagens
obtidas por scanner ou arquivo. Por isso o módulo oferece as duas fontes com a
mesma interface de saída: uma matriz NumPy BGR (formato nativo do OpenCV).
"""

import os
import time
from pathlib import Path

import cv2
import numpy as np

from . import config
from .erros import CameraIndisponivel, ErroCaptura, ImagemInvalida


class Camera:
    """Envolve cv2.VideoCapture com abertura segura e liberação garantida."""

    def __init__(self, indice=None, largura=None, altura=None):
        self.indice = config.INDICE_CAMERA if indice is None else indice
        self.largura = largura or config.LARGURA_CAPTURA
        self.altura = altura or config.ALTURA_CAPTURA
        self._captura = None

    def abrir(self):
        # No Windows, o backend DirectShow abre mais rápido e de forma mais
        # estável do que o backend padrão (MSMF) para webcams comuns.
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        captura = cv2.VideoCapture(self.indice, backend)
        if not captura.isOpened():
            captura.release()
            raise CameraIndisponivel(
                f"Não foi possível abrir a câmera de índice {self.indice}. "
                "Verifique se ela está conectada, se outro programa a está "
                "usando e se o Windows permite o acesso (Configurações > "
                "Privacidade > Câmera).")
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
        self._captura = captura
        self._aquecer()
        return self

    def _aquecer(self, quadros=5):
        """Descarta os primeiros quadros, que costumam sair escuros."""
        for _ in range(quadros):
            self._captura.read()
            time.sleep(0.03)

    def ler(self):
        if self._captura is None:
            raise ErroCaptura("A câmera não foi aberta.")
        ok, quadro = self._captura.read()
        if not ok or quadro is None:
            raise ErroCaptura("A câmera parou de enviar imagens.")
        return quadro

    def fechar(self):
        if self._captura is not None:
            self._captura.release()
            self._captura = None

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *_):
        self.fechar()


def carregar_imagem(caminho, cinza=False):
    """Lê uma imagem de arquivo (scanner, foto, base pública).

    Usa np.fromfile + imdecode porque cv2.imread falha em silêncio com
    caminhos que têm acentos no Windows (ex.: 'Documentos', 'João').
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ImagemInvalida(f"Arquivo não encontrado: {caminho}")
    try:
        dados = np.fromfile(str(caminho), dtype=np.uint8)
        modo = cv2.IMREAD_GRAYSCALE if cinza else cv2.IMREAD_COLOR
        imagem = cv2.imdecode(dados, modo)
    except Exception as exc:  # leitura de disco ou decodificação
        raise ImagemInvalida(f"Falha ao ler {caminho}: {exc}") from exc
    if imagem is None:
        raise ImagemInvalida(f"O arquivo não é uma imagem válida: {caminho}")
    return imagem


def salvar_imagem(caminho, imagem):
    """Grava uma imagem PNG/JPG suportando caminhos com acentos."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    extensao = caminho.suffix or ".png"
    ok, buffer = cv2.imencode(extensao, imagem)
    if not ok:
        raise ImagemInvalida(f"Não foi possível codificar a imagem {caminho}")
    buffer.tofile(str(caminho))
    return caminho

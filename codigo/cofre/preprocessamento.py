"""Fase 2 - Pré-processamento.

Prepara o quadro e o recorte do rosto para as fases seguintes:
conversão para tons de cinza, redução de ruído, correção de iluminação
(equalização de histograma) e avaliação de qualidade da amostra.
"""

import cv2
import numpy as np

from . import config


def para_cinza(imagem):
    """Converte BGR para tons de cinza; aceita imagem que já é cinza."""
    if imagem.ndim == 2:
        return imagem
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)


def reduzir_ruido(cinza):
    """Filtro gaussiano 3x3: atenua o ruído do sensor sem borrar demais."""
    return cv2.GaussianBlur(cinza, (3, 3), 0)


def equalizar_global(cinza):
    """Equalização de histograma global (usada antes do detector Haar)."""
    return cv2.equalizeHist(cinza)


def equalizar_adaptativa(cinza):
    """CLAHE: equalização adaptativa com limite de contraste.

    Trabalha por blocos, o que corrige sombras laterais no rosto melhor do
    que a equalização global (Zuiderveld, 1994).
    """
    clahe = cv2.createCLAHE(clipLimit=config.CLAHE_LIMITE,
                            tileGridSize=config.CLAHE_BLOCO)
    return clahe.apply(cinza)


def normalizar_face(recorte_cinza):
    """Leva qualquer recorte ao tamanho padrão e (se config.USAR_CLAHE) corrige a iluminação."""
    reduzido = cv2.resize(recorte_cinza, config.TAMANHO_FACE,
                          interpolation=cv2.INTER_AREA)
    return equalizar_adaptativa(reduzido) if config.USAR_CLAHE else reduzido


def nitidez(cinza):
    """Variância do laplaciano: quanto menor, mais desfocada a imagem."""
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def avaliar_qualidade(recorte_cinza):
    """Verifica brilho e nitidez do recorte (antes da equalização).

    Devolve (aprovado, lista_de_motivos). Amostras ruins pioram o modelo e,
    na autenticação, produzem falsas rejeições; por isso são descartadas.
    """
    reduzido = cv2.resize(recorte_cinza, config.TAMANHO_FACE,
                          interpolation=cv2.INTER_AREA)
    motivos = []
    brilho = float(np.mean(reduzido))
    if brilho < config.BRILHO_MIN:
        motivos.append("imagem muito escura")
    elif brilho > config.BRILHO_MAX:
        motivos.append("imagem muito clara")
    if nitidez(reduzido) < config.NITIDEZ_MIN:
        motivos.append("imagem desfocada")
    return (len(motivos) == 0), motivos

"""Fase 4 - Extração de características.

Implementa o LBP (Local Binary Patterns) uniforme e o histograma por blocos,
descritor de textura proposto para reconhecimento facial por Ahonen, Hadid e
Pietikäinen (2006). Tudo é feito com NumPy vetorizado, sem laços por pixel.

Fluxo: imagem em cinza -> imagem LBP (um código de 0 a 255 por pixel) ->
mapeamento para 59 classes (padrões uniformes) -> histograma de cada bloco da
grade -> vetor único concatenado e normalizado.
"""

import numpy as np

from . import config

# Deslocamentos dos 8 vizinhos, no sentido horário a partir do canto
# superior esquerdo, em coordenadas da imagem sem borda.
_VIZINHOS = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]


def _tabela_uniformes():
    """Mapeia cada código LBP de 8 bits para uma de 59 classes.

    Um padrão é "uniforme" se, percorrendo os 8 bits em círculo, há no máximo
    duas transições 0->1 ou 1->0. Existem 58 padrões assim (manchas, bordas,
    cantos); os 198 restantes viram uma única classe "outros" (índice 58).
    """
    tabela = np.zeros(256, dtype=np.uint8)
    proximo = 0
    for codigo in range(256):
        bits = [(codigo >> i) & 1 for i in range(8)]
        transicoes = sum(bits[i] != bits[(i + 1) % 8] for i in range(8))
        if transicoes <= 2:
            tabela[codigo] = proximo
            proximo += 1
        else:
            tabela[codigo] = 58
    return tabela


TABELA_UNIFORMES = _tabela_uniformes()
NUM_CLASSES = 59


def imagem_lbp(cinza):
    """Calcula o código LBP (3x3, 8 vizinhos) de cada pixel interno."""
    cinza = np.asarray(cinza, dtype=np.uint8)
    h, w = cinza.shape
    centro = cinza[1:h - 1, 1:w - 1]
    codigo = np.zeros(centro.shape, dtype=np.uint8)
    for posicao, (dy, dx) in enumerate(_VIZINHOS):
        vizinho = cinza[dy:dy + h - 2, dx:dx + w - 2]
        codigo |= ((vizinho >= centro).astype(np.uint8) << (7 - posicao))
    return codigo


def histograma_por_blocos(lbp, grade=None):
    """Divide a imagem LBP em blocos e concatena os histogramas de 59 classes.

    Cada histograma é normalizado pela soma, de modo que o vetor não depende
    do tamanho do bloco. O resultado tem grade[0] * grade[1] * 59 dimensões.
    """
    linhas, colunas = grade or config.GRADE_BLOCOS
    classes = TABELA_UNIFORMES[lbp]
    h, w = classes.shape
    partes = []
    for i in range(linhas):
        for j in range(colunas):
            bloco = classes[i * h // linhas:(i + 1) * h // linhas,
                            j * w // colunas:(j + 1) * w // colunas]
            hist = np.bincount(bloco.ravel(), minlength=NUM_CLASSES).astype(np.float64)
            hist /= max(hist.sum(), 1.0)
            partes.append(hist)
    return np.concatenate(partes)


def extrair(face_normalizada, grade=None):
    """Atalho: rosto normalizado -> vetor de características."""
    return histograma_por_blocos(imagem_lbp(face_normalizada), grade)

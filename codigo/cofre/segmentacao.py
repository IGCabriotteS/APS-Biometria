"""Fase 3 - Segmentação.

Separa o rosto do resto da cena em quatro passos:
  1. detecção do rosto com cascata de Haar (Viola e Jones, 2001);
  2. recorte com pequena margem;
  3. alinhamento: gira o recorte para deixar a linha dos olhos horizontal;
  4. máscara elíptica, que remove cabelo, fundo e roupa dos cantos.
"""

import math

import cv2
import numpy as np

from . import config
from .preprocessamento import equalizar_global


class Detector:
    """Detector de rostos e olhos baseado em cascatas de Haar do OpenCV."""

    def __init__(self):
        pasta = cv2.data.haarcascades
        self._rosto = cv2.CascadeClassifier(pasta + "haarcascade_frontalface_default.xml")
        self._olho = cv2.CascadeClassifier(pasta + "haarcascade_eye.xml")
        if self._rosto.empty() or self._olho.empty():
            raise RuntimeError("Arquivos de cascata do OpenCV não encontrados.")

    def detectar_rostos(self, cinza):
        """Lista de caixas (x, y, w, h) ordenada da maior para a menor."""
        equalizada = equalizar_global(cinza)
        caixas = self._rosto.detectMultiScale(
            equalizada,
            scaleFactor=config.ESCALA_DETECCAO,
            minNeighbors=config.VIZINHOS_DETECCAO,
            minSize=(config.TAMANHO_MIN_FACE, config.TAMANHO_MIN_FACE))
        caixas = [tuple(int(v) for v in c) for c in caixas]
        return sorted(caixas, key=lambda c: c[2] * c[3], reverse=True)

    def detectar_olhos(self, recorte_cinza):
        """Caixas de olhos ABERTOS: no máximo um por metade do rosto.

        Procurar em cada metade da faixa superior (55% da altura) elimina
        detecções em sobrancelha, nariz ou boca e garante um par esquerdo e
        direito para o alinhamento. Parâmetros (passo 1,05 e 4 vizinhos)
        escolhidos medindo, em quadros reais de webcam, a fração de quadros
        com os dois olhos encontrados: 99-100%, contra 38% com passo 1,1 e
        6 vizinhos.
        """
        altura, largura = recorte_cinza.shape[:2]
        faixa = equalizar_global(recorte_cinza[: int(altura * 0.55), :])
        lado = max(8, largura // 8)
        olhos = []
        for x0, x1 in ((0, largura // 2), (largura // 2, largura)):
            achados = self._olho.detectMultiScale(
                faixa[:, x0:x1], scaleFactor=1.05, minNeighbors=4, minSize=(lado, lado))
            if len(achados):
                x, y, w, h = max(achados, key=lambda o: o[2] * o[3])
                olhos.append((int(x) + x0, int(y), int(w), int(h)))
        return olhos


def ha_intruso(caixas):
    """Verdadeiro se houver um segundo rosto de tamanho comparável ao maior.

    Impede que um acompanhante entre junto (piggybacking) ou que alguém
    observe a tela por cima do ombro durante a autenticação.
    """
    if len(caixas) < 2:
        return False
    maior = caixas[0][2] * caixas[0][3]
    segundo = caixas[1][2] * caixas[1][3]
    return segundo >= config.FRACAO_MIN_SEGUNDA_FACE * maior


def recortar(cinza, caixa, margem=None):
    """Recorta a caixa do rosto com margem, respeitando os limites da imagem."""
    margem = config.MARGEM_RECORTE if margem is None else margem
    x, y, w, h = caixa
    dx, dy = int(w * margem), int(h * margem)
    x0, y0 = max(0, x - dx), max(0, y - dy)
    x1, y1 = min(cinza.shape[1], x + w + dx), min(cinza.shape[0], y + h + dy)
    return cinza[y0:y1, x0:x1]


def angulo_entre_olhos(olhos, largura_recorte):
    """Ângulo (graus) da reta que liga os dois olhos, ou None se não houver par."""
    if len(olhos) < 2:
        return None
    # fica com os dois maiores e os ordena da esquerda para a direita
    dois = sorted(sorted(olhos, key=lambda o: o[2] * o[3], reverse=True)[:2],
                  key=lambda o: o[0])
    (x1, y1, w1, h1), (x2, y2, w2, h2) = dois
    c1 = (x1 + w1 / 2.0, y1 + h1 / 2.0)
    c2 = (x2 + w2 / 2.0, y2 + h2 / 2.0)
    if abs(c2[0] - c1[0]) < 0.25 * largura_recorte:
        return None  # olhos "colados": quase certamente uma detecção falsa
    angulo = math.degrees(math.atan2(c2[1] - c1[1], c2[0] - c1[0]))
    if abs(angulo) > config.ANGULO_MAX_ALINHAMENTO:
        return None
    return angulo


def alinhar(recorte_cinza, angulo):
    """Gira o recorte em torno do centro para nivelar os olhos."""
    if angulo is None or abs(angulo) < 1.0:
        return recorte_cinza
    h, w = recorte_cinza.shape[:2]
    matriz = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angulo, 1.0)
    return cv2.warpAffine(recorte_cinza, matriz, (w, h),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def mascara_eliptica(face_normalizada):
    """Zera os pixels fora de uma elipse centrada no rosto.

    O fundo e o cabelo variam de um dia para o outro e não identificam a
    pessoa; mantê-los só aumentaria a distância entre fotos do mesmo usuário.
    """
    h, w = face_normalizada.shape[:2]
    mascara = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(mascara, (w // 2, int(h * 0.52)),
                (int(w * 0.42), int(h * 0.52)), 0, 0, 360, 255, -1)
    return cv2.bitwise_and(face_normalizada, face_normalizada, mask=mascara)

"""Baixa a base ORL (Olivetti faces, AT&T) e grava uma subpasta por pessoa.

Uso (dentro da pasta `codigo`):
    python ferramentas/baixar_orl.py ..\\base_teste\\orl

A base tem 40 pessoas e 10 imagens de cada, em tons de cinza, 64x64 pixels
(versão distribuída pela biblioteca scikit-learn). Requer a internet na
primeira execução; depois fica em cache.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from sklearn.datasets import fetch_olivetti_faces


def main():
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "../base_teste/orl")
    dados = fetch_olivetti_faces(data_home=str(destino.parent / "_cache"), shuffle=False)
    imagens = (dados.images * 255).astype(np.uint8)
    contagem = {}
    for imagem, pessoa in zip(imagens, dados.target):
        contagem[pessoa] = contagem.get(pessoa, 0) + 1
        pasta = destino / f"s{pessoa + 1:02d}"
        pasta.mkdir(parents=True, exist_ok=True)
        cv2.imencode(".png", imagem)[1].tofile(str(pasta / f"{contagem[pessoa]:02d}.png"))
    print(f"{len(imagens)} imagens de {len(contagem)} pessoas gravadas em {destino}")


if __name__ == "__main__":
    main()

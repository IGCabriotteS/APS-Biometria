"""Fase 5 - Classificação e interpretação.

O classificador compara o vetor de características do rosto apresentado com os
vetores guardados de cada usuário usando a distância qui-quadrado, adequada a
histogramas. A decisão é em conjunto aberto: se nenhum usuário chega perto o
bastante, o rosto é tratado como desconhecido, nunca como "o mais parecido".
"""

import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config
from .erros import ModeloIndisponivel

_EPS = 1e-10


def distancia_qui_quadrado(a, b):
    """Distância qui-quadrado simétrica entre histogramas normalizados.

    Para vetores de blocos, a soma é dividida pelo número de blocos, o que
    mantém o resultado na faixa de 0 a 2 independentemente da grade usada.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    blocos = max(1, a.shape[-1] // 59)
    return np.sum((a - b) ** 2 / (a + b + _EPS), axis=-1) / blocos


@dataclass
class Previsao:
    """Resultado da comparação de um rosto com o modelo."""
    usuario_id: int          # id do usuário mais próximo (-1 se modelo vazio)
    distancia: float         # distância ao usuário mais próximo
    segunda_distancia: float  # distância ao segundo mais próximo (inf se só há um)
    aceito: bool             # distancia <= limiar

    @property
    def margem(self):
        """Folga relativa entre o melhor e o segundo colocado."""
        if not np.isfinite(self.segunda_distancia) or self.segunda_distancia <= 0:
            return 1.0
        return (self.segunda_distancia - self.distancia) / self.segunda_distancia


class Reconhecedor:
    """Banco de histogramas por usuário + busca do vizinho mais próximo."""

    def __init__(self, limiar=None):
        self.limiar = config.LIMIAR_DISTANCIA if limiar is None else limiar
        self._vetores = np.empty((0, 0))
        self._rotulos = np.empty(0, dtype=np.int64)

    # -- treino ---------------------------------------------------------------
    def treinar(self, vetores, rotulos):
        vetores = np.asarray(vetores, dtype=np.float64)
        rotulos = np.asarray(rotulos, dtype=np.int64)
        if len(vetores) == 0 or len(vetores) != len(rotulos):
            raise ModeloIndisponivel("Não há amostras suficientes para treinar o modelo.")
        self._vetores, self._rotulos = vetores, rotulos
        return self

    @property
    def treinado(self):
        return len(self._rotulos) > 0

    @property
    def usuarios(self):
        return sorted(set(int(r) for r in self._rotulos))

    # -- inferência ------------------------------------------------------------
    def prever(self, vetor):
        if not self.treinado:
            raise ModeloIndisponivel("O modelo ainda não foi treinado.")
        distancias = distancia_qui_quadrado(self._vetores, np.asarray(vetor)[None, :])
        por_usuario = []
        for uid in self.usuarios:
            d = np.sort(distancias[self._rotulos == uid])
            k = min(config.MELHORES_AMOSTRAS, len(d))
            por_usuario.append((float(np.mean(d[:k])), uid))
        por_usuario.sort()
        melhor_d, melhor_id = por_usuario[0]
        segunda_d = por_usuario[1][0] if len(por_usuario) > 1 else float("inf")
        return Previsao(melhor_id, melhor_d, segunda_d, melhor_d <= self.limiar)

    # -- persistência com verificação de integridade ---------------------------
    def salvar(self, caminho=None):
        caminho = Path(caminho or config.ARQUIVO_MODELO)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(caminho, vetores=self._vetores, rotulos=self._rotulos)
        return hash_arquivo(caminho)

    @classmethod
    def carregar(cls, caminho=None, hash_esperado=None, limiar=None):
        caminho = Path(caminho or config.ARQUIVO_MODELO)
        if not caminho.is_file():
            raise ModeloIndisponivel("Nenhum modelo treinado foi encontrado.")
        if hash_esperado is not None and hash_arquivo(caminho) != hash_esperado:
            raise ModeloIndisponivel(
                "O arquivo do modelo foi alterado ou está corrompido "
                "(a impressão digital SHA-256 não confere). Um administrador local deve "
                "verificar a máquina e executar: python -m cofre retreinar")
        try:
            with np.load(caminho) as dados:
                modelo = cls(limiar)
                modelo.treinar(dados["vetores"], dados["rotulos"])
        except ModeloIndisponivel:
            raise
        except Exception as exc:
            raise ModeloIndisponivel(f"Modelo ilegível: {exc}") from exc
        return modelo


def hash_arquivo(caminho):
    """SHA-256 do conteúdo de um arquivo."""
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


class Confirmador:
    """Votação temporal: só confirma quando o mesmo usuário vence em N dos
    últimos M quadros.

    Um único quadro pode ser enganado por ruído, reflexo ou uma semelhança
    ocasional; exigir consistência no tempo filtra esses erros de um quadro só
    sem exigir que o usuário fique parado. ATENÇÃO: quadros consecutivos de uma
    mesma pose são muito parecidos, então 8 votos NÃO são 8 evidências
    independentes. A votação não protege contra uma pessoa muito parecida com um
    usuário cadastrado, e o seu efeito sobre a falsa aceitação não foi medido.
    """

    def __init__(self, janela=None, necessarios=None):
        self.janela = janela or config.QUADROS_JANELA
        self.necessarios = necessarios or config.QUADROS_CONFIRMACAO
        self._votos = deque(maxlen=self.janela)

    def registrar(self, usuario_id):
        """usuario_id é None quando o quadro foi rejeitado."""
        self._votos.append(usuario_id)
        return self.confirmado()

    def confirmado(self):
        validos = [v for v in self._votos if v is not None]
        if not validos:
            return None
        candidato = max(set(validos), key=validos.count)
        return candidato if validos.count(candidato) >= self.necessarios else None

    def reiniciar(self):
        self._votos.clear()

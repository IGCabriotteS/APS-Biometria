"""Lógica de autenticação em tempo real, sem entrada/saída.

A classe SessaoAutenticacao recebe o resultado do pipeline de cada quadro e
devolve o estado da tentativa. Como não depende de câmera nem de janelas, ela
é testada automaticamente com sequências simuladas de quadros.
"""

import time
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from . import config
from .classificacao import Confirmador
from .erros import SistemaBloqueado
from .prova_vida import DesafioPiscada

PROCURANDO = "procurando"
VALIDANDO = "validando"
PROVA_DE_VIDA = "prova_de_vida"
IDENTIFICADO = "identificado"
FALHA = "falha"

_MOTIVOS = {
    "nao_reconhecido": "rosto não reconhecido (usuário desconhecido)",
    "varios_rostos": "mais de um rosto no campo de visão",
    "sem_rosto": "nenhum rosto detectado",
    "qualidade": "qualidade da imagem insuficiente",
}


@dataclass
class Estado:
    fase: str
    mensagem: str
    usuario_id: Optional[int] = None
    distancia: Optional[float] = None
    motivo_falha: Optional[str] = None

    @property
    def finalizado(self):
        return self.fase in (IDENTIFICADO, FALHA)


class SessaoAutenticacao:
    """Uma tentativa de autenticação, do primeiro quadro ao veredito."""

    def __init__(self, reconhecedor, exigir_vida=None, relogio=time.monotonic,
                 tempo_max=None):
        self.reconhecedor = reconhecedor
        self.exigir_vida = config.EXIGIR_PROVA_DE_VIDA if exigir_vida is None else exigir_vida
        self._relogio = relogio
        self._tempo_max = tempo_max or config.TEMPO_MAX_AUTENTICACAO
        self._inicio = relogio()
        self._inicio_vida = None
        self._confirmador = Confirmador()
        self._desafio = DesafioPiscada()
        self._ocorrencias = Counter()
        self._usuario = None
        self._distancia = None
        self._outro_seguido = 0
        self._reconfirmados = 0

    # ------------------------------------------------------------------------
    def _falha(self, motivo):
        return Estado(FALHA, "Acesso negado: " + motivo, self._usuario,
                      self._distancia, motivo)

    def _motivo_predominante(self):
        if not self._ocorrencias:
            return "tempo esgotado"
        chave = self._ocorrencias.most_common(1)[0][0]
        return _MOTIVOS[chave]

    def _reiniciar_identidade(self):
        self._confirmador.reiniciar()
        self._desafio.reiniciar()
        self._usuario = None
        self._inicio_vida = None
        self._outro_seguido = 0
        self._reconfirmados = 0

    # ------------------------------------------------------------------------
    def processar(self, r):
        agora = self._relogio()

        if self._usuario is None and agora - self._inicio > self._tempo_max:
            return self._falha(self._motivo_predominante())
        if (self._usuario is not None and self._inicio_vida is not None
                and agora - self._inicio_vida > config.TEMPO_MAX_PISCADA):
            return self._falha("prova de vida não realizada no tempo previsto")

        if not r.tem_rosto:
            self._ocorrencias["sem_rosto"] += 1
            self._reiniciar_identidade()
            return Estado(PROCURANDO, "Aproxime o rosto da câmera")

        if r.intruso:
            self._ocorrencias["varios_rostos"] += 1
            self._reiniciar_identidade()
            return Estado(PROCURANDO, "Mais de um rosto no campo de visão")

        if not r.qualidade_ok:
            self._ocorrencias["qualidade"] += 1
            if self._usuario is None:
                self._confirmador.registrar(None)
            return Estado(PROCURANDO, "Qualidade ruim: " + ", ".join(r.motivos))

        previsao = self.reconhecedor.prever(r.vetor)
        valido = previsao.aceito and previsao.margem >= config.MARGEM_MINIMA

        if self._usuario is None:
            confirmado = self._confirmador.registrar(
                previsao.usuario_id if valido else None)
            if not valido:
                self._ocorrencias["nao_reconhecido"] += 1
            if confirmado is None:
                texto = "Verificando identidade..." if valido else "Rosto não reconhecido"
                return Estado(VALIDANDO, texto, distancia=previsao.distancia)
            self._usuario, self._distancia = confirmado, previsao.distancia
            if not self.exigir_vida:
                return Estado(IDENTIFICADO, "Identidade confirmada",
                              self._usuario, self._distancia)
            self._inicio_vida = agora
            self._desafio.reiniciar()
            self._desafio.registrar(r.olhos)
            return Estado(PROVA_DE_VIDA, self._desafio.instrucao,
                          self._usuario, self._distancia)

        # --- fase de prova de vida: a identidade precisa continuar a mesma ----
        if valido and previsao.usuario_id != self._usuario:
            self._outro_seguido += 1
            self._reconfirmados = 0
            if self._outro_seguido >= 3:
                return self._falha("troca de pessoa durante a prova de vida")
        else:
            self._outro_seguido = 0
        reconhecido = valido and previsao.usuario_id == self._usuario
        # Reconfirmação: só o MESMO usuário reconhecido conta. Sem isso, trocar a foto de
        # quem foi identificado por um rosto desconhecido que pisca faria a prova de vida
        # "valer" para a vítima.
        self._reconfirmados = self._reconfirmados + 1 if reconhecido else 0
        # Os quadros de olhos ABERTOS (antes e depois da piscada) precisam ser do mesmo
        # usuário; só durante a piscada, quando o reconhecimento cai de qualidade, o
        # desafio tolera quadros não reconhecidos. Um rosto desconhecido que apareça
        # com os olhos abertos reinicia o desafio.
        if not reconhecido and self._desafio.estado != DesafioPiscada.AGUARDA_PISCADA \
                and not self._desafio.concluido:
            self._desafio.reiniciar()
        else:
            self._desafio.registrar(r.olhos)
        if self._desafio.concluido and self._reconfirmados >= config.QUADROS_RECONFIRMACAO:
            return Estado(IDENTIFICADO, "Identidade e prova de vida confirmadas",
                          self._usuario, self._distancia)
        return Estado(PROVA_DE_VIDA, self._desafio.instrucao,
                      self._usuario, self._distancia)


class ControleBloqueio:
    """Bloqueio temporário do terminal após falhas consecutivas.

    O contador e o horário de liberação ficam no banco, para que fechar e
    reabrir o programa não zere a punição (ataque de força bruta).
    """

    def __init__(self, banco, relogio=time.time):
        self._banco = banco
        self._relogio = relogio

    def segundos_restantes(self):
        ate = float(self._banco.obter_parametro("bloqueio_ate", "0"))
        return max(0, int(round(ate - self._relogio())))

    def exigir_liberado(self):
        restante = self.segundos_restantes()
        if restante > 0:
            raise SistemaBloqueado(restante)

    def registrar_falha(self):
        """Soma uma falha; devolve True se esta falha ativou o bloqueio."""
        falhas = int(self._banco.obter_parametro("falhas_consecutivas", "0")) + 1
        if falhas >= config.TENTATIVAS_ATE_BLOQUEIO:
            self._banco.definir_parametro(
                "bloqueio_ate", self._relogio() + config.SEGUNDOS_BLOQUEIO)
            self._banco.definir_parametro("falhas_consecutivas", 0)
            return True
        self._banco.definir_parametro("falhas_consecutivas", falhas)
        return False

    def registrar_sucesso(self):
        self._banco.definir_parametro("falhas_consecutivas", 0)

"""Encadeia as cinco fases e guarda as imagens intermediárias.

Guardar cada etapa permite mostrar, na apresentação, o que o sistema "enxerga"
em cada fase, e permite que os testes verifiquem as fases separadamente.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from . import caracteristicas, config, preprocessamento, segmentacao


def _face_final(alinhada):
    """Normaliza o rosto e, se config.USAR_MASCARA, remove os cantos (cabelo, fundo)."""
    face = preprocessamento.normalizar_face(alinhada)
    return segmentacao.mascara_eliptica(face) if config.USAR_MASCARA else face


@dataclass
class Resultado:
    """Tudo o que o pipeline produziu para um quadro."""
    quadro: Optional[np.ndarray] = None          # fase 1: imagem original (BGR)
    cinza: Optional[np.ndarray] = None           # fase 2: tons de cinza
    caixas: List[Tuple[int, int, int, int]] = field(default_factory=list)
    caixa: Optional[Tuple[int, int, int, int]] = None   # fase 3: maior rosto
    intruso: bool = False                        # há outro rosto relevante?
    recorte: Optional[np.ndarray] = None         # fase 3: recorte com margem
    angulo: Optional[float] = None               # inclinação corrigida (graus)
    olhos: int = 0                               # olhos abertos detectados
    normalizada: Optional[np.ndarray] = None     # fase 3/4: rosto 100x100 mascarado
    lbp: Optional[np.ndarray] = None             # fase 4: imagem LBP
    vetor: Optional[np.ndarray] = None           # fase 4: histograma por blocos
    qualidade_ok: bool = False
    motivos: List[str] = field(default_factory=list)

    @property
    def tem_rosto(self):
        return self.caixa is not None


class Pipeline:
    def __init__(self):
        self.detector = segmentacao.Detector()

    # -- a partir de um quadro completo (câmera ou foto de corpo/busto) --------
    def processar(self, quadro_bgr, com_olhos=True):
        r = Resultado(quadro=quadro_bgr)
        r.cinza = preprocessamento.para_cinza(quadro_bgr)
        suave = preprocessamento.reduzir_ruido(r.cinza)

        r.caixas = self.detector.detectar_rostos(suave)
        if not r.caixas:
            return r
        r.caixa = r.caixas[0]
        r.intruso = segmentacao.ha_intruso(r.caixas)

        r.recorte = segmentacao.recortar(suave, r.caixa)
        qual_ok, motivos = preprocessamento.avaliar_qualidade(r.recorte)
        r.qualidade_ok, r.motivos = qual_ok, motivos

        if com_olhos:
            olhos = self.detector.detectar_olhos(r.recorte)
            r.olhos = len(olhos)
            r.angulo = segmentacao.angulo_entre_olhos(olhos, r.recorte.shape[1])
        alinhado = segmentacao.alinhar(r.recorte, r.angulo)

        r.normalizada = _face_final(alinhado)
        r.lbp = caracteristicas.imagem_lbp(r.normalizada)
        r.vetor = caracteristicas.histograma_por_blocos(r.lbp)
        return r

    # -- a partir de um recorte já feito (bases públicas, fotos 3x4) -----------
    def processar_recorte(self, recorte_bgr_ou_cinza):
        """Pula a detecção: o arquivo já contém só o rosto."""
        r = Resultado(quadro=recorte_bgr_ou_cinza)
        r.cinza = preprocessamento.para_cinza(recorte_bgr_ou_cinza)
        r.recorte = preprocessamento.reduzir_ruido(r.cinza)
        r.caixa = (0, 0, r.cinza.shape[1], r.cinza.shape[0])
        r.caixas = [r.caixa]
        r.qualidade_ok, r.motivos = preprocessamento.avaliar_qualidade(r.recorte)
        r.normalizada = _face_final(r.recorte)
        r.lbp = caracteristicas.imagem_lbp(r.normalizada)
        r.vetor = caracteristicas.histograma_por_blocos(r.lbp)
        return r

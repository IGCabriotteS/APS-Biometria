"""Avaliação de desempenho do reconhecedor em uma base de imagens.

Espera uma pasta com uma subpasta por pessoa (ex.: base/s1/1.pgm, 2.pgm...).
Protocolo em conjunto aberto, que imita o cofre real:

  * metade das pessoas é "cadastrada" (as primeiras k imagens de cada uma);
  * a outra metade é de "intrusos": nunca aparece no treino;
  * as demais imagens são o teste: as de cadastrados medem a taxa de falsa
    rejeição (FRR) e as dos intrusos medem a taxa de falsa aceitação (FAR).

Varrendo o limiar de distância obtém-se a curva FAR x FRR e o ponto de erro
igual (EER), que orienta a escolha de config.LIMIAR_DISTANCIA.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import caracteristicas, config
from .aquisicao import carregar_imagem
from .classificacao import Reconhecedor
from .erros import ErroCofre
from .pipeline import Pipeline

EXTENSOES = {".pgm", ".png", ".jpg", ".jpeg", ".bmp"}


@dataclass
class Relatorio:
    limiares: np.ndarray
    far: np.ndarray
    frr: np.ndarray
    eer: float
    limiar_eer: float
    acuracia_identificacao: float   # entre cadastrados, no limiar do EER
    n_genuinos: int
    n_impostores: int
    n_cadastrados: int
    n_intrusos: int


def carregar_base(pasta):
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroCofre(f"Pasta da base não encontrada: {pasta}")
    base = {}
    for sub in sorted(p for p in pasta.iterdir() if p.is_dir()):
        arquivos = sorted(f for f in sub.iterdir() if f.suffix.lower() in EXTENSOES)
        if arquivos:
            base[sub.name] = arquivos
    if len(base) < 4:
        raise ErroCofre("A base precisa de pelo menos 4 pessoas (2 cadastradas e 2 intrusos).")
    return base


def _vetor(pipeline, caminho, detectar):
    imagem = carregar_imagem(caminho, cinza=True)
    r = (pipeline.processar(imagem, com_olhos=True) if detectar
         else pipeline.processar_recorte(imagem))
    return r.vetor if r.tem_rosto and r.vetor is not None else None


def avaliar(pasta, amostras_cadastro=5, detectar=False, passo_limiar=0.01,
            progresso=None):
    base = carregar_base(pasta)
    pessoas = list(base)
    cadastrados = pessoas[::2]            # alternância determinística
    intrusos = [p for p in pessoas if p not in cadastrados]
    pipeline = Pipeline()

    vetores, rotulos, teste = [], [], []   # teste: (vetor, rotulo_real ou -1)
    for indice, pessoa in enumerate(pessoas):
        for pos, arquivo in enumerate(base[pessoa]):
            v = _vetor(pipeline, arquivo, detectar)
            if v is None:
                continue
            if pessoa in cadastrados and pos < amostras_cadastro:
                vetores.append(v)
                rotulos.append(cadastrados.index(pessoa))
            elif pessoa in cadastrados:
                teste.append((v, cadastrados.index(pessoa)))
            else:
                teste.append((v, -1))
        if progresso:
            progresso(indice + 1, len(pessoas))

    modelo = Reconhecedor(limiar=float("inf")).treinar(vetores, rotulos)
    previsoes = [(modelo.prever(v), real) for v, real in teste]

    genuinos = [(p.distancia, p.usuario_id == real) for p, real in previsoes if real >= 0]
    impostores = [p.distancia for p, real in previsoes if real < 0]
    if not genuinos or not impostores:
        raise ErroCofre("A base não gerou amostras de teste suficientes.")

    dist_gen = np.array([d for d, _ in genuinos])
    acertou = np.array([ok for _, ok in genuinos])
    dist_imp = np.array(impostores)

    limiares = np.arange(0.0, max(dist_gen.max(), dist_imp.max()) + passo_limiar, passo_limiar)
    # FRR: genuíno rejeitado por distância alta OU identificado como outra pessoa
    frr = np.array([np.mean((dist_gen > t) | (~acertou)) for t in limiares])
    far = np.array([np.mean(dist_imp <= t) for t in limiares])
    # EER pelos limiares EXATOS (as próprias distâncias medidas), e não pela grade acima,
    # para coincidir com ferramentas/experimentos.py; a grade serve só para a curva e o CSV.
    cand = np.unique(np.concatenate([dist_gen, dist_imp]))
    far_c = np.array([np.mean(dist_imp <= t) for t in cand])
    frr_c = np.array([np.mean((dist_gen > t) | (~acertou)) for t in cand])
    i = int(np.argmin(np.abs(far_c - frr_c)))
    eer = float((far_c[i] + frr_c[i]) / 2.0)
    acuracia = float(np.mean(acertou & (dist_gen <= cand[i])))

    return Relatorio(limiares, far, frr, eer, float(cand[i]), acuracia,
                     len(dist_gen), len(dist_imp), len(cadastrados), len(intrusos))


def calibrar_com_cadastros(banco):
    """Mede distâncias entre as amostras de cadastro REAIS (câmera) dos usuários.

    Serve para conferir o limiar com os rostos do próprio grupo, sem pedir novas
    capturas. Dois vieses otimistas, que o relatório deve declarar:
      * legítimos: as amostras são da mesma sessão (ignoram-se a própria e as
        vizinhas na sequência, que são quase idênticas), então a FRR real, em
        outro dia e outra luz, tende a ser PIOR do que a medida aqui;
      * impostores: só existem os outros usuários cadastrados, poucas pessoas.
    Devolve um dicionário com as estatísticas.
    """
    from .classificacao import distancia_qui_quadrado

    por_usuario = {}
    for usuario in banco.listar_usuarios():
        pasta = config.PASTA_AMOSTRAS / str(usuario["id"])
        vetores = [caracteristicas.extrair(carregar_imagem(f, cinza=True))
                   for f in sorted(pasta.glob("*.png"))]
        if len(vetores) >= 5:
            por_usuario[usuario["nome"]] = np.array(vetores)
    if len(por_usuario) < 2:
        raise ErroCofre("A calibração precisa de pelo menos 2 usuários cadastrados com amostras.")

    genuinos, impostores = [], []
    for nome, V in por_usuario.items():
        for i, v in enumerate(V):
            d = distancia_qui_quadrado(V, v[None, :])
            longe = np.abs(np.arange(len(V)) - i) > 2       # fora da vizinhança temporal
            if longe.any():
                genuinos.append(float(d[longe].min()))
        for outro, W in por_usuario.items():
            if outro != nome:
                for v in W:
                    impostores.append(float(distancia_qui_quadrado(V, v[None, :]).min()))
    gen, imp = np.array(genuinos), np.array(impostores)
    limiar = config.LIMIAR_DISTANCIA
    return {
        "usuarios": len(por_usuario), "n_genuinos": len(gen), "n_impostores": len(imp),
        "gen_mediana": float(np.median(gen)), "gen_p90": float(np.percentile(gen, 90)),
        "gen_max": float(gen.max()), "imp_min": float(imp.min()),
        "imp_p5": float(np.percentile(imp, 5)), "imp_mediana": float(np.median(imp)),
        "frr_no_limiar": float(np.mean(gen > limiar)), "far_no_limiar": float(np.mean(imp <= limiar)),
        "limiar": limiar,
    }


def resumo_calibracao(r):
    return "\n".join([
        "CALIBRAÇÃO COM AS AMOSTRAS DE CADASTRO (câmera)",
        f"  Usuários: {r['usuarios']}   Pares legítimos: {r['n_genuinos']}   Pares de impostor: {r['n_impostores']}",
        f"  Legítimos (distância): mediana {r['gen_mediana']:.3f}, percentil 90 {r['gen_p90']:.3f}, máxima {r['gen_max']:.3f}",
        f"  Impostores (distância): mínima {r['imp_min']:.3f}, percentil 5 {r['imp_p5']:.3f}, mediana {r['imp_mediana']:.3f}",
        f"  No limiar atual ({r['limiar']}): FRR {100 * r['frr_no_limiar']:.1f}%  FAR {100 * r['far_no_limiar']:.1f}%",
        "  Leitura: um limiar seguro fica ABAIXO da menor distância de impostor. Se a máxima dos",
        "  legítimos estiver acima dela, as faixas se sobrepõem e é preciso melhorar a captura",
        "  (luz, posição) antes de mexer no limiar. Estes números são OTIMISTAS: mesma sessão,",
        "  poucos impostores. Confirme com tentativas reais em outro momento.",
    ])


def salvar_csv(relatorio, caminho):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["limiar", "FAR", "FRR"])
        for t, a, f in zip(relatorio.limiares, relatorio.far, relatorio.frr):
            escritor.writerow([f"{t:.3f}".replace(".", ","),
                               f"{a:.4f}".replace(".", ","), f"{f:.4f}".replace(".", ",")])
    return caminho


def resumo(relatorio):
    return "\n".join([
        "AVALIAÇÃO DE DESEMPENHO (conjunto aberto)",
        f"  Pessoas cadastradas: {relatorio.n_cadastrados}   Intrusos: {relatorio.n_intrusos}",
        f"  Testes genuínos: {relatorio.n_genuinos}   Testes de impostor: {relatorio.n_impostores}",
        f"  Limiar no ponto de erro igual (EER): {relatorio.limiar_eer:.3f}",
        f"  EER: {100 * relatorio.eer:.2f}%",
        f"  Identificação correta de cadastrados nesse limiar: "
        f"{100 * relatorio.acuracia_identificacao:.2f}%",
        f"  Limiar configurado hoje: {config.LIMIAR_DISTANCIA}",
    ])

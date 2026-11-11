"""Experimentos reproduzíveis com a base ORL (usados no capítulo de resultados).

Uso (dentro da pasta `codigo`):
    python ferramentas/experimentos.py ..\\base_teste\\orl  ..\\figuras  ..\\documentos\\resultados.json

Protocolo de identificação em CONJUNTO ABERTO: metade das pessoas é cadastrada (as
primeiras n imagens), a outra metade são intrusos que nunca aparecem no cadastro.

Duas formas de relatar cada configuração:
  * divisão de referência: pessoas de índice par cadastradas, ímpar intrusos, imagens
    em ordem (a mesma usada em todo o relatório);
  * 30 divisões aleatórias (pessoas e imagens sorteadas): média e desvio-padrão.
    Como todas vêm das mesmas 40 pessoas, o desvio-padrão mede a sensibilidade à
    divisão, NÃO a incerteza de generalizar para outras pessoas (que é maior).

Métricas (nomes da ISO/IEC 19795-1 para identificação em conjunto aberto):
  FAR  = FPIR: fração de impostores aceitos como alguém;
  FRR  = FNIR: fração de legítimos recusados OU identificados como outra pessoa;
  EER  = ponto em que FAR = FRR (pode passar de 50% porque a FRR inclui a troca de identidade);
  FRR@FAR1% = FRR no limiar mais permissivo que mantém FAR <= 1%.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cofre import caracteristicas, config, preprocessamento, segmentacao  # noqa: E402
from cofre.aquisicao import carregar_imagem  # noqa: E402
from cofre.classificacao import distancia_qui_quadrado  # noqa: E402

SEMENTES = range(30)


def carregar(pasta):
    pessoas = sorted(p for p in Path(pasta).iterdir() if p.is_dir())
    return [[carregar_imagem(f, cinza=True) for f in sorted(p.glob("*.png"))] for p in pessoas]


def preparar(img, mascara=True, equalizacao="clahe", tamanho=(100, 100)):
    """Mesma cadeia do pipeline (suavização, normalização, máscara) com opções."""
    suave = preprocessamento.reduzir_ruido(img)
    r = cv2.resize(suave, tamanho, interpolation=cv2.INTER_AREA)
    if equalizacao == "clahe":
        r = preprocessamento.equalizar_adaptativa(r)
    elif equalizacao == "global":
        r = cv2.equalizeHist(r)
    return segmentacao.mascara_eliptica(r) if mascara else r


# ---------------------------------------------------------------------------
# métricas
# ---------------------------------------------------------------------------
def calcular_eer(dist_gen, acertou, dist_imp):
    """(EER, limiar no EER, FRR@FAR1%) varrendo o limiar."""
    melhor, frr_far1 = None, 1.0
    for t in np.unique(np.concatenate([dist_gen, dist_imp])):
        far = float(np.mean(dist_imp <= t))
        frr = float(np.mean((dist_gen > t) | (~acertou)))
        if melhor is None or abs(far - frr) < melhor[0]:
            melhor = (abs(far - frr), (far + frr) / 2.0, float(t))
        if far <= 0.01:
            frr_far1 = frr          # o último t com FAR <= 1% é o mais permissivo
    return melhor[1], melhor[2], frr_far1


def prever(ref, rot, v, distancia, k, n_usuarios):
    d = distancia(ref, v[None, :])
    por = [np.sort(d[rot == u])[:k].mean() for u in range(n_usuarios)]
    return int(np.argmin(por)), float(np.min(por))


def avaliar_divisao(F_ref, rot, F_gen, rot_gen, F_imp, distancia, k, n_usuarios):
    gen, ok = [], []
    for v, real in zip(F_gen, rot_gen):
        ident, d = prever(F_ref, rot, v, distancia, k, n_usuarios)
        gen.append(d)
        ok.append(ident == real)
    imp = [prever(F_ref, rot, v, distancia, k, n_usuarios)[1] for v in F_imp]
    return np.array(gen), np.array(ok), np.array(imp)


def dividir(rng, n_pessoas, n_imgs, n_cad):
    """Sorteia pessoas cadastradas/intrusos e imagens de cadastro/teste."""
    pessoas = rng.permutation(n_pessoas)
    cad, intr = pessoas[: n_pessoas // 2], pessoas[n_pessoas // 2:]
    plano = [(int(p), *np.split(rng.permutation(n_imgs), [n_cad])) for p in cad]
    return plano, [int(p) for p in intr]


def dividir_referencia(n_pessoas, n_imgs, n_cad):
    cad = list(range(0, n_pessoas, 2))
    intr = list(range(1, n_pessoas, 2))
    ordem = np.arange(n_imgs)
    return [(p, ordem[:n_cad], ordem[n_cad:]) for p in cad], intr


# ---------------------------------------------------------------------------
# execução de uma configuração
# ---------------------------------------------------------------------------
def rodar(F_de, distancia, n_cad=5, k=1, n_pessoas=40, n_imgs=10, aleatorio=True):
    """F_de(plano) -> (F_ref, F_gen, F_imp) para uma divisão. Devolve métricas."""
    resultados = []
    divisoes = ([dividir(np.random.default_rng(s), n_pessoas, n_imgs, n_cad) for s in SEMENTES]
                if aleatorio else [dividir_referencia(n_pessoas, n_imgs, n_cad)])
    for plano, intr in divisoes:
        F_ref, rot, F_gen, rot_gen, F_imp = F_de(plano, intr)
        gen, ok, imp = avaliar_divisao(F_ref, rot, F_gen, rot_gen, F_imp, distancia, k, len(plano))
        eer, lim, frr1 = calcular_eer(gen, ok, imp)
        resultados.append({"eer": eer, "limiar": lim, "frr_far1": frr1,
                           "far_cfg": float(np.mean(imp <= config.LIMIAR_DISTANCIA)),
                           "frr_cfg": float(np.mean((gen > config.LIMIAR_DISTANCIA) | (~ok))),
                           "gen": gen, "imp": imp, "ok": ok})
    return resultados


def extrator_arrays(F):
    """F: array (pessoas, imagens, D) já calculado -> função de divisão."""
    def f(plano, intr):
        ref, rot, gen, rot_gen = [], [], [], []
        for u, (p, j_cad, j_teste) in enumerate(plano):
            for j in j_cad:
                ref.append(F[p, j]); rot.append(u)
            for j in j_teste:
                gen.append(F[p, j]); rot_gen.append(u)
        imp = [F[p, j] for p in intr for j in range(F.shape[1])]
        return np.array(ref), np.array(rot), np.array(gen), np.array(rot_gen), np.array(imp)
    return f


def extrator_pca(X, componentes):
    """PCA (Turk e Pentland, 1991) treinada SÓ com as imagens de cadastro da divisão."""
    def f(plano, intr):
        treino = np.array([X[p, j] for p, j_cad, _ in plano for j in j_cad])
        media = treino.mean(axis=0)
        _, _, vt = np.linalg.svd(treino - media, full_matrices=False)
        base = vt[:componentes]
        proj = lambda x: base @ (x - media)
        ref, rot, gen, rot_gen = [], [], [], []
        for u, (p, j_cad, j_teste) in enumerate(plano):
            for j in j_cad:
                ref.append(proj(X[p, j])); rot.append(u)
            for j in j_teste:
                gen.append(proj(X[p, j])); rot_gen.append(u)
        imp = [proj(X[p, j]) for p in intr for j in range(X.shape[1])]
        return np.array(ref), np.array(rot), np.array(gen), np.array(rot_gen), np.array(imp)
    return f


def euclidiana(a, b):
    return np.sqrt(np.sum((a - b) ** 2, axis=-1))


def coseno(a, b):
    num = np.sum(a * b, axis=-1)
    den = np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1) + 1e-12
    return 1.0 - num / den


def intersecao(a, b):
    return 1.0 - np.sum(np.minimum(a, b), axis=-1) / (a.shape[-1] // 59)


def resumo(ref, aleat):
    eers = np.array([r["eer"] for r in aleat])
    frr1 = np.array([r["frr_far1"] for r in aleat])
    return {"eer": ref[0]["eer"], "limiar": ref[0]["limiar"], "frr_far1": ref[0]["frr_far1"],
            "eer_media": float(eers.mean()), "eer_dp": float(eers.std(ddof=1)),
            "frr_far1_media": float(frr1.mean()), "frr_far1_dp": float(frr1.std(ddof=1)),
            "acuracia": 1.0 - ref[0]["eer"]}       # mantido só para compatibilidade com as figuras


def pareados(imagens, resultados):
    """Diferenças PAREADAS (mesmas 30 divisões) entre variantes, com IC de 95% da média.

    diferença = EER da variante - EER do LBP padrão (ou da referência indicada);
    positivo = a variante é pior. O IC usa t de Student (29 gl); vale para a
    variação ENTRE DIVISÕES das mesmas 40 pessoas, não para outras pessoas.
    """
    n_p, n_i = len(imagens), len(imagens[0])
    chi = distancia_qui_quadrado

    def eers(F_de, d, k=1):
        return np.array([r["eer"] for r in rodar(F_de, d, 5, k, n_p, n_i, aleatorio=True)])

    F_pad = np.array([[caracteristicas.extrair(preparar(i)) for i in ims] for ims in imagens])
    F_nu = np.array([[caracteristicas.extrair(preparar(i, mascara=False, equalizacao="nenhuma")) for i in ims]
                     for ims in imagens])
    X_cl = np.array([[preparar(i, mascara=False).ravel().astype(np.float64) for i in ims] for ims in imagens])
    X_nc = np.array([[preparar(i, mascara=False, equalizacao="nenhuma").ravel().astype(np.float64) for i in ims]
                     for ims in imagens])
    base = eers(extrator_arrays(F_pad), chi)                       # LBP padrão (CLAHE + máscara)
    sem = eers(extrator_arrays(F_nu), chi)                         # LBP sem CLAHE e sem máscara
    pca_cl = eers(extrator_pca(X_cl, 80), coseno)                  # melhor PCA, com CLAHE
    pca_nc = eers(extrator_pca(X_nc, 80), coseno)                  # o mesmo PCA, sem CLAHE
    euc = eers(extrator_arrays(F_pad), euclidiana)
    k2 = eers(extrator_arrays(F_pad), chi, k=2)
    comparacoes = {
        "LBP padrão (CLAHE e máscara) contra LBP sem CLAHE e sem máscara": base - sem,
        "PCA 80 + cosseno (com CLAHE) contra LBP padrão (com CLAHE e máscara)": pca_cl - base,
        "PCA 80 + cosseno (sem CLAHE) contra LBP sem CLAHE e sem máscara": pca_nc - sem,
        "Distância euclidiana contra qui-quadrado (LBP padrão)": euc - base,
        "Decisão por k = 2 contra k = 1 (LBP padrão)": k2 - base,
    }
    t = 2.045   # t de Student, 29 graus de liberdade, bilateral 95%
    saida = {}
    for nome, d in comparacoes.items():
        m, dp = float(d.mean()), float(d.std(ddof=1))
        h = t * dp / np.sqrt(len(d))
        saida[nome] = {"media": m, "ic_inf": m - h, "ic_sup": m + h, "fracao_positiva": float(np.mean(d > 0))}
        print(f"{nome}: diferença média {100 * m:+.1f} pp  IC95% [{100 * (m - h):+.1f}; {100 * (m + h):+.1f}]  "
              f"(variante pior em {100 * np.mean(d > 0):.0f}% das divisões)")
    resultados["pareados"] = saida
    # linhas extras para a tabela de métodos
    resumo_pca_nc = {"eer_media": float(pca_nc.mean()), "eer_dp": float(pca_nc.std(ddof=1))}
    resultados["metodo"]["Eigenfaces sem CLAHE (PCA 80 + cosseno)"] = {
        **resumo_pca_nc, "eer": float("nan")   # só há as 30 divisões; sem divisão de referência, "frr_far1_media": float("nan"), "frr_far1_dp": float("nan")}
    return resultados


def main():
    if len(sys.argv) > 4 and sys.argv[4] == "--so-pareados":
        # roda apenas o bloco de diferenças pareadas e atualiza o JSON existente
        pasta, saida_json = sys.argv[1], Path(sys.argv[3])
        res = json.loads(saida_json.read_text(encoding="utf-8"))
        pareados(carregar(pasta), res)
        saida_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Pareados gravados em", saida_json)
        return
    pasta, saida_fig, saida_json = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    saida_fig.mkdir(parents=True, exist_ok=True)
    imagens = carregar(pasta)
    n_p, n_i = len(imagens), len(imagens[0])
    chi = distancia_qui_quadrado
    resultados = {"pessoas": n_p, "imagens_por_pessoa": n_i, "divisoes_aleatorias": len(list(SEMENTES))}

    def LBP(grade=(8, 8), **opc):
        return np.array([[caracteristicas.extrair(preparar(i, **opc), grade) for i in ims] for ims in imagens])

    def linha(nome, F_de, distancia, n_cad=5, k=1):
        ref = rodar(F_de, distancia, n_cad, k, n_p, n_i, aleatorio=False)
        alea = rodar(F_de, distancia, n_cad, k, n_p, n_i, aleatorio=True)
        r = resumo(ref, alea)
        print(f"{nome:44s} ref {100 * r['eer']:5.1f}%  30 divisões {100 * r['eer_media']:5.1f} ± {100 * r['eer_dp']:4.1f}"
              f"  FRR@FAR1% {100 * r['frr_far1_media']:5.1f} ± {100 * r['frr_far1_dp']:4.1f}")
        return r, ref, alea

    F_padrao = LBP()
    padrao = extrator_arrays(F_padrao)

    print("--- grade de blocos ---")
    resultados["grade"] = {}
    for g in (1, 3, 4, 5, 6, 7, 8, 10):
        F = F_padrao if g == 8 else LBP((g, g))
        resultados["grade"][f"{g}x{g}"] = linha(f"grade {g}x{g}", extrator_arrays(F), chi)[0]

    print("--- pré-processamento ---")
    resultados["preprocessamento"] = {}
    for nome, opc in {"CLAHE + máscara (padrão)": {}, "sem máscara": {"mascara": False},
                      "equalização global": {"equalizacao": "global"},
                      "sem equalização": {"equalizacao": "nenhuma"},
                      "sem equalização e sem máscara": {"equalizacao": "nenhuma", "mascara": False}}.items():
        F = F_padrao if not opc else LBP(**opc)
        resultados["preprocessamento"][nome] = linha(nome, extrator_arrays(F), chi)[0]

    print("--- medida de distância e k ---")
    resultados["distancia"] = {}
    for nome, d in {"qui-quadrado": chi, "euclidiana": euclidiana, "interseção de histogramas": intersecao}.items():
        resultados["distancia"][nome] = linha(nome, padrao, d)[0]
    resultados["k"] = {}
    for k in (1, 2, 3):
        resultados["k"][str(k)] = linha(f"k = {k}", padrao, chi, k=k)[0]

    print("--- imagens de cadastro por pessoa ---")
    resultados["cadastro"] = {}
    for n in (2, 3, 5, 7):
        resultados["cadastro"][str(n)] = linha(f"{n} imagens de cadastro", padrao, chi, n_cad=n)[0]

    print("--- método: LBP x Eigenfaces (várias configurações de PCA) ---")
    resultados["metodo"] = {"LBP 8x8 + qui-quadrado": resultados["distancia"]["qui-quadrado"]}
    X = np.array([[preparar(i, mascara=False).ravel().astype(np.float64) for i in ims] for ims in imagens])
    pca = {}
    for comp in (10, 20, 40, 60, 80):
        for nome_d, d in (("euclidiana", euclidiana), ("cosseno", coseno)):
            pca[(comp, nome_d)] = linha(f"Eigenfaces PCA {comp} + {nome_d}", extrator_pca(X, comp), d)[0]
    melhor = min(pca, key=lambda c: pca[c]["eer_media"])
    resultados["metodo"]["Eigenfaces (PCA 40) + euclidiana"] = pca[(40, "euclidiana")]
    resultados["metodo"][f"Eigenfaces, melhor configuração testada (PCA {melhor[0]} + {melhor[1]})"] = pca[melhor]
    resultados["pca_todas"] = {f"{c}+{d}": v for (c, d), v in pca.items()}

    # distâncias da divisão de referência (para as figuras) e limiar de produção em 30 divisões
    ref = rodar(padrao, chi, 5, 1, n_p, n_i, aleatorio=False)[0]
    alea = rodar(padrao, chi, 5, 1, n_p, n_i, aleatorio=True)
    np.savez(saida_fig / "distancias_orl.npz", gen=ref["gen"], imp=ref["imp"])
    gen, imp = ref["gen"], ref["imp"]
    far_cfg = np.array([r["far_cfg"] for r in alea])
    frr_cfg = np.array([r["frr_cfg"] for r in alea])
    resultados["padrao"] = {
        "eer": ref["eer"], "limiar_eer": ref["limiar"], "acuracia": 1.0 - ref["eer"],
        "n_genuinos": int(len(gen)), "n_impostores": int(len(imp)),
        "far_no_limiar_config": float(np.mean(imp <= config.LIMIAR_DISTANCIA)),
        "frr_no_limiar_config": float(np.mean((gen > config.LIMIAR_DISTANCIA) | (~ref["ok"]))),
        "gen_media": float(gen.mean()), "imp_media": float(imp.mean()),
        "gen_mediana": float(np.median(gen)), "imp_mediana": float(np.median(imp)),
        "imp_min": float(imp.min()),
        "limiar_cfg_far_media_30": float(far_cfg.mean()), "limiar_cfg_far_dp_30": float(far_cfg.std(ddof=1)),
        "limiar_cfg_far_max_30": float(far_cfg.max()),
        "limiar_cfg_frr_media_30": float(frr_cfg.mean()), "limiar_cfg_frr_dp_30": float(frr_cfg.std(ddof=1)),
    }
    print(f"\nLimiar {config.LIMIAR_DISTANCIA} em 30 divisões: FAR {100 * far_cfg.mean():.2f}% ± {100 * far_cfg.std(ddof=1):.2f} "
          f"(máx {100 * far_cfg.max():.1f}%), FRR {100 * frr_cfg.mean():.1f}% ± {100 * frr_cfg.std(ddof=1):.1f}")
    print("--- diferenças pareadas ---")
    pareados(imagens, resultados)
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    saida_json.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Resultados gravados em", saida_json)


if __name__ == "__main__":
    main()

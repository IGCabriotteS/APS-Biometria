"""Gera as figuras do relatório a partir do código e da base ORL.

Uso (dentro da pasta `codigo`):
    python ferramentas/gerar_figuras.py ..\\base_teste\\orl ..\\figuras ..\\documentos\\resultados.json

As imagens de rosto vêm da base ORL (AT&T Laboratories Cambridge); as figuras de
processamento são produzidas pelas próprias funções do sistema, não desenhadas.
"""

import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cofre import caracteristicas, config, interface, preprocessamento, segmentacao  # noqa: E402
from cofre.aquisicao import carregar_imagem  # noqa: E402
from cofre.classificacao import Reconhecedor  # noqa: E402
from cofre.pipeline import Pipeline  # noqa: E402

plt.rcParams.update({"font.family": ["Arial", "DejaVu Sans"], "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 200, "savefig.bbox": "tight", "figure.dpi": 100})
CINZA, ESCURO, DESTAQUE, CLARO = "#6b6b6b", "#222222", "#1f6f8b", "#e6eef2"


def salvar(fig, pasta, nome):
    fig.savefig(pasta / nome, facecolor="white")
    plt.close(fig)
    print("ok", nome)


def caixa(ax, x, y, w, h, texto, cor=CLARO, borda=ESCURO, tam=8.5, negrito=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=cor, ec=borda, lw=1.1))
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=tam,
            fontweight="bold" if negrito else "normal", color=ESCURO)


def seta(ax, p, q, curva=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11, lw=1.1,
                                 color=ESCURO, connectionstyle=f"arc3,rad={curva}"))


def fig_cinco_fases(pasta):
    fig, ax = plt.subplots(figsize=(6.3, 2.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.0); ax.axis("off")
    nomes = ["1. Aquisição", "2. Pré-\nprocessamento", "3. Segmen-\ntação",
             "4. Extração de\ncaracterísticas", "5. Classificação"]
    detalhe = ["câmera ou\narquivo de\nimagem", "cinza, ruído,\nequalização", "detecção,\nrecorte, alinha-\nmento, máscara",
               "LBP uniforme\ne histograma\npor blocos", "distância\nqui-quadrado,\nlimiar, política"]
    xs = [0.05, 2.05, 4.05, 6.05, 8.05]
    for x, n, d in zip(xs, nomes, detalhe):
        caixa(ax, x, 2.35, 1.65, 1.3, n, tam=7.4, negrito=True)
        ax.text(x + 0.825, 1.55, d, ha="center", va="center", fontsize=6.4, color=CINZA)
    for a, b in zip(xs, xs[1:]):
        seta(ax, (a + 1.7, 3.0), (b - 0.04, 3.0))
    ax.text(5, 0.35, "Fluxo do sistema: da imagem bruta até a decisão de acesso", ha="center",
            fontsize=7.5, style="italic", color=CINZA)
    salvar(fig, pasta, "fig01_cinco_fases.png")


def fig_arquitetura(pasta):
    """Arquitetura em camadas: interface -> serviço -> três grupos de módulos."""
    fig, ax = plt.subplots(figsize=(6.3, 4.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 7.2); ax.axis("off")
    caixa(ax, 1.6, 6.3, 6.8, 0.75, "Interface: interface.py e __main__.py\n(menus, janelas em tempo real, linha de comando)", tam=7.8)
    caixa(ax, 2.2, 4.95, 5.6, 0.85, "Serviço: servico.py (classe Cofre)\ncadastro, treino, decisão e registro", cor="#d5e6ec", tam=7.8, negrito=True)
    seta(ax, (5, 6.3), (5, 5.83))
    colunas = [
        (0.1, "Fases 1 a 4 (imagem)", ["aquisicao.py", "preprocessamento.py", "segmentacao.py", "caracteristicas.py", "pipeline.py"]),
        (3.5, "Fase 5 e autenticação", ["classificacao.py", "autenticacao.py", "prova_vida.py", "avaliacao.py"]),
        (6.9, "Segurança e auditoria", ["politica.py", "banco.py", "relatorios.py"]),
    ]
    for x, titulo, modulos in colunas:
        ax.text(x + 1.5, 4.45, titulo, ha="center", fontsize=8, fontweight="bold")
        seta(ax, (min(max(x + 1.5, 3.0), 7.0), 4.93), (x + 1.5, 4.68))
        for i, nome in enumerate(modulos):
            caixa(ax, x, 3.5 - 0.78 * i, 3.0, 0.58, nome, tam=8)
    salvar(fig, pasta, "fig02_arquitetura.png")


def fig_lbp_exemplo(pasta):
    bloco = np.array([[60, 10, 60], [10, 50, 60], [10, 60, 10]])
    centro = 50
    bits = (bloco >= centro).astype(int)
    ordem = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]
    cod = "".join(str(bits[p]) for p in ordem)
    fig, axs = plt.subplots(1, 3, figsize=(6.3, 2.4))
    for ax, dados, titulo in zip(axs[:2], (bloco, bits), ("Vizinhança 3x3 (tons de cinza)", "Limiarização: vizinho >= centro")):
        ax.imshow(np.zeros((3, 3)), cmap="Greys", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(dados[i, j]), ha="center", va="center", fontsize=12,
                        fontweight="bold" if (i, j) == (1, 1) else "normal")
        ax.add_patch(Rectangle((0.5, 0.5), 1, 1, fill=False, ec=DESTAQUE, lw=2))
        ax.set_xticks(range(3)); ax.set_yticks(range(3)); ax.tick_params(length=0, labelbottom=False, labelleft=False)
        ax.set_title(titulo, fontsize=8)
        for s in ax.spines.values():
            s.set_visible(True)
    axs[2].axis("off")
    axs[2].text(0, 0.82, "Leitura no sentido horário\na partir do canto superior\nesquerdo:", fontsize=8.5, va="top")
    axs[2].text(0, 0.42, " ".join(cod), fontsize=11, family="monospace", fontweight="bold")
    axs[2].text(0, 0.2, f"= {cod} (binário)\n= {int(cod, 2)} (decimal)", fontsize=9, va="top")
    axs[2].text(0, -0.05, "O pixel central recebe\no código " + str(int(cod, 2)), fontsize=8.5, va="top", color=CINZA)
    salvar(fig, pasta, "fig03_lbp_exemplo.png")


def fig_etapas(pasta, imagens):
    pipe = Pipeline()
    img = imagens[0][2]
    r = pipe.processar_recorte(img)
    suave = preprocessamento.reduzir_ruido(img)
    clahe = preprocessamento.normalizar_face(suave)
    classes = caracteristicas.TABELA_UNIFORMES[r.lbp]
    fig, axs = plt.subplots(1, 6, figsize=(6.4, 1.9))
    pares = [(img, "Original\n(64x64)"), (suave, "Pré-processada\n(gaussiano 3x3)"),
             (clahe, "Normalizada\n(100x100 + CLAHE)"), (r.normalizada, "Máscara\nelíptica"),
             (r.lbp, "Imagem LBP\n(códigos 0-255)"), (classes, "Classes uniformes\n(0-58)")]
    for ax, (im, tit) in zip(axs, pares):
        ax.imshow(im, cmap="gray"); ax.set_title(tit, fontsize=6.2); ax.axis("off")
    salvar(fig, pasta, "fig04_etapas.png")

    fig, axs = plt.subplots(1, 2, figsize=(6.3, 2.7), gridspec_kw={"width_ratios": [1, 1.7]})
    axs[0].imshow(r.normalizada, cmap="gray"); axs[0].axis("off")
    h, w = r.normalizada.shape
    for k in range(1, 8):
        axs[0].axhline(k * h / 8, color="#ffcc00", lw=0.5); axs[0].axvline(k * w / 8, color="#ffcc00", lw=0.5)
    axs[0].set_title("Grade de 8x8 blocos", fontsize=8)
    vetor = r.vetor
    bloco = vetor[27 * 59:28 * 59]
    axs[1].bar(range(59), bloco, color=DESTAQUE, width=0.85)
    axs[1].set_title("Histograma LBP de um bloco (59 classes)", fontsize=8)
    axs[1].set_xlabel("classe LBP (0-57 uniformes, 58 = outros)"); axs[1].set_ylabel("frequência relativa")
    salvar(fig, pasta, "fig05_grade_histograma.png")


def fig_variacao_pose(pasta, imagens):
    fig, axs = plt.subplots(2, 5, figsize=(6.0, 2.7))
    for ax, im in zip(axs.ravel(), imagens[5]):
        ax.imshow(im, cmap="gray"); ax.axis("off")
    fig.suptitle("Dez imagens de uma mesma pessoa na base ORL (variação de pose e expressão)", fontsize=8)
    salvar(fig, pasta, "fig06_variacao_orl.png")


def fig_distribuicoes(pasta):
    dados = np.load(pasta / "distancias_orl.npz")
    gen, imp = dados["gen"], dados["imp"]
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.8))
    bins = np.linspace(0.15, 0.8, 30)
    axs[0].hist(gen, bins=bins, alpha=0.8, color=DESTAQUE, label="legítimos")
    axs[0].hist(imp, bins=bins, alpha=0.6, color="#b5651d", label="intrusos")
    axs[0].axvline(config.LIMIAR_DISTANCIA, color="black", ls="--", lw=1)
    axs[0].text(config.LIMIAR_DISTANCIA + 0.01, axs[0].get_ylim()[1] * 0.9, "limiar\n0,38", fontsize=7)
    axs[0].set_xlabel("distância qui-quadrado"); axs[0].set_ylabel("nº de testes"); axs[0].legend(fontsize=7)
    axs[0].set_title("Distribuição das distâncias", fontsize=8)
    ts = np.linspace(0, 0.8, 300)
    far = [np.mean(imp <= t) for t in ts]
    frr = [np.mean(gen > t) for t in ts]
    axs[1].plot(ts, np.array(far) * 100, color="#b5651d", label="FAR (falsa aceitação)")
    axs[1].plot(ts, np.array(frr) * 100, color=DESTAQUE, label="FRR (falsa rejeição)")
    axs[1].axvline(config.LIMIAR_DISTANCIA, color="black", ls="--", lw=1)
    axs[1].set_ylim(0, 125)
    axs[1].set_xlabel("limiar de distância"); axs[1].set_ylabel("taxa (%)")
    axs[1].legend(fontsize=7, loc="upper center", ncol=2, frameon=False)
    axs[1].set_title("FAR e FRR em função do limiar", fontsize=8)
    fig.tight_layout()
    salvar(fig, pasta, "fig07_far_frr.png")


def fig_barras(pasta, res):
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.7))
    g = res["grade"]
    chaves = list(g)
    axs[0].bar(chaves, [100 * g[k]["eer_media"] for k in chaves], yerr=[100 * g[k]["eer_dp"] for k in chaves],
               color=DESTAQUE, capsize=2, error_kw={"lw": 0.8})
    axs[0].set_ylabel("EER médio (%)"); axs[0].set_xlabel("grade de blocos")
    axs[0].tick_params(axis="x", labelsize=6.5)
    axs[0].set_title("Efeito da grade de blocos", fontsize=8)
    pca_melhor = [v for n, v in res["metodo"].items() if n.startswith("Eigenfaces, melhor")][0]
    metodos = {"LBP\nqui-quad.": res["metodo"]["LBP 8x8 + qui-quadrado"],
               "LBP\neuclid.": res["distancia"]["euclidiana"],
               "LBP\ninters.": res["distancia"]["interseção de histogramas"],
               "PCA 40\neuclid.": res["metodo"]["Eigenfaces (PCA 40) + euclidiana"],
               "PCA\nmelhor": pca_melhor}
    axs[1].bar(list(metodos), [100 * v["eer_media"] for v in metodos.values()],
               yerr=[100 * v["eer_dp"] for v in metodos.values()], capsize=2, error_kw={"lw": 0.8},
               color=[DESTAQUE, "#6aa0b4", "#6aa0b4", "#b5651d", "#b5651d"])
    axs[1].set_ylabel("EER médio (%)"); axs[1].tick_params(axis="x", labelsize=6.5)
    axs[1].set_title("Métodos e medidas de distância", fontsize=8)
    fig.tight_layout()
    salvar(fig, pasta, "fig08_ablacao.png")


def fig_cadastro(pasta, res):
    c = res["cadastro"]
    fig, ax = plt.subplots(figsize=(4.2, 2.5))
    ns = list(c)
    ax.errorbar(ns, [100 * c[n]["eer_media"] for n in ns], yerr=[100 * c[n]["eer_dp"] for n in ns],
                fmt="o-", color=DESTAQUE, capsize=3, label="EER (média ± desvio-padrão)")
    ax.errorbar(ns, [100 * c[n]["frr_far1_media"] for n in ns], yerr=[100 * c[n]["frr_far1_dp"] for n in ns],
                fmt="s--", color="#b5651d", capsize=3, label="FRR com FAR de cerca de 1%")
    ax.set_xlabel("imagens de cadastro por pessoa"); ax.set_ylabel("%"); ax.legend(fontsize=7)
    ax.set_title("Mais amostras no cadastro, menos erro (30 divisões)", fontsize=8)
    salvar(fig, pasta, "fig09_cadastro.png")


def fig_estados(pasta):
    fig, ax = plt.subplots(figsize=(6.3, 3.7))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.2); ax.axis("off")
    caixa(ax, 0.1, 4.3, 2.3, 1.0, "PROCURANDO\nsem rosto, intruso\nou qualidade ruim", tam=7)
    caixa(ax, 3.7, 4.3, 2.3, 1.0, "VALIDANDO\nvotação: 8 votos\nem 12 quadros", tam=7)
    caixa(ax, 7.3, 4.3, 2.5, 1.0, "PROVA DE VIDA\npiscada em\naté 8 segundos", tam=7)
    caixa(ax, 7.3, 1.6, 2.5, 1.0, "IDENTIFICADO\naplica a política", cor="#d5e6ec", tam=7.2, negrito=True)
    caixa(ax, 3.2, 0.2, 3.3, 1.0, "FALHA\nacesso negado e registro", cor="#f0d9c8", tam=7.2, negrito=True)
    seta(ax, (2.45, 4.8), (3.65, 4.8)); seta(ax, (6.05, 4.8), (7.25, 4.8))
    seta(ax, (8.55, 4.28), (8.55, 2.65))
    ax.text(8.7, 3.45, "piscada\nconcluída", fontsize=6.5, color=CINZA, va="center")
    ax.text(0.1, 5.85, "início da tentativa", fontsize=6.8, color=CINZA)
    seta(ax, (1.0, 5.8), (1.0, 5.35))
    seta(ax, (3.7, 4.55), (2.45, 4.55), 0.0)
    ax.text(3.05, 3.85, "rosto some ou há vários\nrostos: recomeça", fontsize=6.5, color=CINZA, ha="center")
    seta(ax, (4.85, 4.28), (4.85, 1.25))
    ax.text(4.98, 2.75, "15 s sem\nconfirmar", fontsize=6.5, color=CINZA, va="center")
    seta(ax, (7.7, 4.28), (6.55, 1.0), -0.12)
    ax.text(7.35, 2.0, "sem piscada ou\ntroca de pessoa", fontsize=6.5, color=CINZA, ha="right", va="center")
    salvar(fig, pasta, "fig10_estados_autenticacao.png")


def fig_banco(pasta):
    fig, ax = plt.subplots(figsize=(6.3, 3.9))
    ax.set_xlim(0, 10); ax.set_ylim(-1.1, 5.6); ax.axis("off")
    def tabela(x, y, w, titulo, campos):
        h = 0.42 * (len(campos) + 1)
        ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=ESCURO, lw=1.1))
        ax.add_patch(Rectangle((x, y + h - 0.42), w, 0.42, fc=CLARO, ec=ESCURO, lw=1.1))
        ax.text(x + w / 2, y + h - 0.21, titulo, ha="center", va="center", fontsize=8, fontweight="bold")
        for i, c in enumerate(campos):
            ax.text(x + 0.1, y + h - 0.42 - 0.21 - 0.42 * i, c, va="center", fontsize=7)
    tabela(0.1, 1.5, 2.9, "usuarios", ["id (PK)", "nome", "cargo", "nivel (1 a 3)", "divisao", "ativo", "criado_em"])
    tabela(3.55, 3.0, 2.9, "compartimentos", ["id (PK)", "nome (único)", "nivel_minimo", "divisao"])
    tabela(3.55, 1.2, 2.9, "parametros", ["chave (PK)", "valor"])
    tabela(7.0, 0.5, 2.9, "acessos", ["id (PK)", "data_hora", "usuario_id", "nome", "compartimento", "resultado", "motivo", "distancia", "hash_anterior", "hash"])
    ax.text(0.1, -0.25,
            "A tabela acessos guarda o nome do usuário e do compartimento (texto), e não só chaves, para que o\n"
            "histórico sobreviva à remoção de cadastros. A tabela parametros guarda o hash do modelo, o contador\n"
            "de falhas e o horário de liberação do bloqueio.",
            fontsize=6.6, color=CINZA, ha="left", va="top")
    salvar(fig, pasta, "fig11_banco.png")


def fig_haar(pasta):
    fig, axs = plt.subplots(1, 4, figsize=(6.0, 1.7))
    def desenhar(ax, regioes, titulo):
        ax.set_xlim(0, 4); ax.set_ylim(0, 3); ax.set_aspect("equal"); ax.axis("off")
        ax.add_patch(Rectangle((0.3, 0.3), 3.4, 2.4, fc="white", ec=ESCURO))
        for (x, y, w, h, cor) in regioes:
            ax.add_patch(Rectangle((x, y), w, h, fc=cor, ec=ESCURO))
        ax.set_title(titulo, fontsize=7)
    desenhar(axs[0], [(0.3, 0.3, 1.7, 2.4, "white"), (2.0, 0.3, 1.7, 2.4, "#444444")], "borda vertical")
    desenhar(axs[1], [(0.3, 1.5, 3.4, 1.2, "white"), (0.3, 0.3, 3.4, 1.2, "#444444")], "borda horizontal")
    desenhar(axs[2], [(0.3, 0.3, 1.13, 2.4, "white"), (1.43, 0.3, 1.14, 2.4, "#444444"), (2.57, 0.3, 1.13, 2.4, "white")], "linha")
    desenhar(axs[3], [(0.3, 0.3, 1.7, 1.2, "white"), (2.0, 1.5, 1.7, 1.2, "white"), (2.0, 0.3, 1.7, 1.2, "#444444"), (0.3, 1.5, 1.7, 1.2, "#444444")], "diagonal")
    salvar(fig, pasta, "fig12_haar.png")


def fig_telas(pasta, imagens):
    """Reproduz as telas do sistema com rostos da ORL (mesmas funções de desenho)."""
    pipe = Pipeline()
    treino = [pipe.processar_recorte(im).vetor for i in (0, 2, 4) for im in imagens[i][:7]]
    rotulos = [i for i in (1, 2, 3) for _ in range(7)]
    modelo = Reconhecedor(limiar=0.53).treinar(treino, rotulos)
    probe = imagens[2][8]
    r = pipe.processar_recorte(probe)
    previsao = modelo.prever(r.vetor)
    painel = interface.montar_painel(r, previsao)
    cv2.imencode(".png", painel)[1].tofile(str(pasta / "fig13_painel_fases.png"))
    print("ok fig13_painel_fases.png")

    def tela(permitido, linhas):
        base = cv2.resize(cv2.cvtColor(probe, cv2.COLOR_GRAY2BGR), (480, 480), interpolation=cv2.INTER_CUBIC)
        canvas = np.zeros((480, 640, 3), np.uint8)
        canvas[:, 80:560] = base
        cor = interface.VERDE if permitido else interface.VERMELHO
        cv2.rectangle(canvas, (0, 0), (639, 479), cor, 14)
        interface._texto(canvas, "ACESSO PERMITIDO" if permitido else "ACESSO NEGADO", (30, 70), cor, 1.2, 3)
        for i, linha in enumerate(linhas):
            interface._texto(canvas, linha, (30, 120 + 34 * i), interface.BRANCO, 0.65)
        return canvas
    a = tela(True, ["Dora Diretora", "Nivel 2 - Diretor de divisao", "Laboratorio de Toxinas Agricolas", "diretor da divisao responsavel"])
    b = tela(False, ["Dora Diretora", "Nivel 2 - Diretor de divisao", "Camara Central de Toxinas de Alto Risco", "compartimento exclusivo do ministro"])
    cv2.imencode(".png", np.hstack([a, b]))[1].tofile(str(pasta / "fig14_telas_resultado.png"))
    print("ok fig14_telas_resultado.png")


def main():
    pasta_base, pasta_fig, arq_json = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    pasta_fig.mkdir(parents=True, exist_ok=True)
    pessoas = sorted(p for p in pasta_base.iterdir() if p.is_dir())
    imagens = [[carregar_imagem(f, cinza=True) for f in sorted(p.glob("*.png"))] for p in pessoas]
    res = json.loads(arq_json.read_text(encoding="utf-8"))
    fig_cinco_fases(pasta_fig); fig_arquitetura(pasta_fig); fig_lbp_exemplo(pasta_fig)
    fig_etapas(pasta_fig, imagens); fig_variacao_pose(pasta_fig, imagens)
    fig_distribuicoes(pasta_fig); fig_barras(pasta_fig, res); fig_cadastro(pasta_fig, res)
    fig_estados(pasta_fig); fig_banco(pasta_fig); fig_haar(pasta_fig); fig_telas(pasta_fig, imagens)


if __name__ == "__main__":
    main()

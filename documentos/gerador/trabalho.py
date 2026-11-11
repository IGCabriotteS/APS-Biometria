"""Monta o trabalho de APS completo (Word + PDF) a partir de conteudo/*.txt.

Uso (na pasta documentos\\gerador):
    python trabalho.py [--visivel]
Saída: ..\\APS_Biometria_Facial_Trabalho.docx e .pdf
"""

import json
import sys
from pathlib import Path

from docgen import (CM, Montador, analisar, wdAlignCenter, wdAlignLeft)

RAIZ = Path(__file__).resolve().parent
DOCS = RAIZ.parent
FIGS = DOCS.parent / "figuras"
CONTEUDO = DOCS / "conteudo"
IMAGEM_LOGO = DOCS / "gerador" / "logo_unip.png"
G = json.loads((RAIZ / "grupo.json").read_text(encoding="utf-8"))

RESUMO = (
    "Este trabalho apresenta o projeto, a implementação e a avaliação de um sistema de identificação e "
    "autenticação biométrica por reconhecimento facial para proteger o acesso a um cofre de segurança "
    "máxima, com três níveis de permissão: acesso geral, diretores de divisão e ministro. O sistema "
    "foi desenvolvido em Python, com OpenCV e NumPy, e organizado segundo as cinco fases do processamento "
    "de imagens digitais: aquisição, pré-processamento, segmentação, extração de características e "
    "classificação. A face é detectada por classificador em cascata, alinhada e normalizada, descrita por "
    "padrões binários locais (LBP) uniformes em histogramas por blocos e classificada por distância "
    "qui-quadrado em conjunto aberto, com limiar de rejeição escolhido por experimento. O programa inclui "
    "votação em vários quadros, prova de vida por piscada, recusa de mais de um rosto, bloqueio após "
    "falhas, histórico de acessos encadeado por hash, relatórios e tratamento de erros. Em experimentos "
    "com a base ORL, em 30 divisões aleatórias, o método obteve taxa de erro igual média de 15,1% (desvio-padrão "
    "de 3,1 pontos), à frente da distância euclidiana e do melhor ajuste de eigenfaces testado por margens "
    "pequenas, porém consistentes entre as divisões, e a falsa aceitação média foi de 0,18% no limiar adotado, ao custo de falsa rejeição média de "
    "36,2% nessa base de baixa resolução. O número de imagens de cadastro teve efeito grande e consistente, e as "
    "etapas de equalização adaptativa e de máscara pioraram o resultado nessa base. Os resultados são "
    "discutidos com suas limitações estatísticas, sem validação com câmera e usuários reais, bem como os "
    "aspectos legais, éticos e interdisciplinares envolvidos no uso de dados biométricos."
)
PALAVRAS = "Reconhecimento facial. Biometria. Processamento de imagens. Controle de acesso. Padrões binários locais."
ABSTRACT = (
    "This work presents the design, implementation and evaluation of a facial recognition based biometric "
    "identification and authentication system that protects access to a maximum security vault, with three "
    "permission levels: general access, division directors and the minister. The system was developed in "
    "Python with OpenCV and NumPy and is organized according to the five phases of digital image processing: "
    "acquisition, preprocessing, segmentation, feature extraction and classification. Faces are detected by a "
    "cascade classifier, aligned and normalized, described by uniform local binary patterns (LBP) in block "
    "histograms and classified by chi-square distance in an open-set setting, with a rejection threshold chosen "
    "experimentally. The program includes multi-frame voting, blink-based liveness checking, rejection of "
    "multiple faces, lockout after failures, a hash-chained access log, reports and error handling. In "
    "experiments on the ORL database, over 30 random splits, the method reached a mean equal error rate of "
    "15.1% (standard deviation 3.1 points), ahead of Euclidean distance and of the best eigenfaces setting "
    "tested by small but consistent margins, and a mean false acceptance rate of 0.18% at the adopted threshold, at the cost "
    "of a mean false rejection rate of 36.2% on this low-resolution database. The number of enrollment images "
    "had a large and consistent effect, and adaptive equalization and masking worsened the results on this "
    "database. The results are discussed with their limitations, without validation on a camera with real users, "
    "together with the legal, ethical and interdisciplinary aspects of using biometric data."
)
KEYWORDS = "Facial recognition. Biometrics. Image processing. Access control. Local binary patterns."

SIGLAS = [
    ("ABNT", "Associação Brasileira de Normas Técnicas"), ("APS", "Atividades Práticas Supervisionadas"),
    ("BGR", "Blue, Green, Red (ordem dos canais de cor no OpenCV)"), ("CCD", "Charge-Coupled Device"),
    ("CLAHE", "Contrast Limited Adaptive Histogram Equalization"), ("CMOS", "Complementary Metal-Oxide Semiconductor"),
    ("CSV", "Comma-Separated Values"), ("EER", "Equal Error Rate (taxa de erro igual)"),
    ("FAR", "False Acceptance Rate (taxa de falsa aceitação)"), ("FRR", "False Rejection Rate (taxa de falsa rejeição)"),
    ("IEC", "International Electrotechnical Commission"), ("ISO", "International Organization for Standardization"),
    ("LBP", "Local Binary Patterns (padrões binários locais)"), ("LDA", "Linear Discriminant Analysis"),
    ("LGPD", "Lei Geral de Proteção de Dados Pessoais"), ("ORL", "Base de rostos da Olivetti Research Laboratory (AT&T)"),
    ("PCA", "Principal Component Analysis (análise de componentes principais)"),
    ("PIVC", "Processamento de Imagem e Visão Computacional"), ("RBAC", "Role-Based Access Control"),
    ("RF", "Requisito funcional"), ("SHA", "Secure Hash Algorithm"), ("UNIP", "Universidade Paulista"),
]

ATIVIDADES_FICHA = [
    "Estudo do enunciado, levantamento bibliográfico e definição dos requisitos",
    "Desenvolvimento das fases de aquisição, pré-processamento e segmentação",
    "Desenvolvimento das fases de extração de características e classificação",
    "Experimentos com base pública e escolha dos parâmetros",
    "Banco de dados, política de três níveis e registro de acessos",
    "Autenticação em tempo real, prova de vida e bloqueio",
    "Interface, relatórios e tratamento de erros",
    "Testes finais e redação do relatório",
    "Preparo da apresentação",
]


def fmt(x, casas=1):
    """Percentual com vírgula decimal e arredondamento convencional (meio para cima)."""
    import math
    from decimal import ROUND_HALF_UP, Decimal
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    v = Decimal(str(round(100 * x, 6))).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return f"{v}".replace(".", ",")


def sinal(x, casas=1):
    """Diferença em pontos percentuais, com sinal e vírgula decimal."""
    return ("+" if x >= 0 else "−") + fmt(abs(x), casas)


def mais_menos(media, dp, casas=1):
    if media != media:      # NaN: medida não calculada para esta variante
        return "–"
    return f"{fmt(media, casas)} ± {fmt(dp, casas)}"


def linhas_tabela(variantes):
    """variantes: [(rotulo, dict de resultados)] -> linhas '| a | b |' da tabela."""
    saida = ["| Variante | EER, divisão de referência (%) | EER, média ± desvio-padrão em 30 divisões (%) | "
             "FRR com FAR de cerca de 1%, média ± desvio-padrão (%) |"]
    for rotulo, r in variantes:
        saida.append(f"| {rotulo} | {fmt(r['eer'])} | {mais_menos(r['eer_media'], r['eer_dp'])} | "
                     f"{mais_menos(r['frr_far1_media'], r['frr_far1_dp'])} |")
    return "\n".join(saida)


def preencher(texto, res):
    """Troca marcadores @@T:xxx@@ por tabelas e @@N:xxx@@ por números calculados do JSON."""
    legenda = "Elaborado pelos autores (2026), a partir de experimento com a base ORL (SAMARIA; HARTER, 1994)."
    larg = "34,16,25,25"

    def tab(chave, titulo, variantes):
        return f"[TAB {chave} | {titulo} | {legenda} | {larg}]\n" + linhas_tabela(variantes)

    g = res["grade"]
    grade = tab("grade", "Efeito da grade de blocos do histograma LBP", [
        ("1 × 1 (histograma global)", g["1x1"]), ("3 × 3", g["3x3"]), ("4 × 4", g["4x4"]), ("5 × 5", g["5x5"]),
        ("6 × 6", g["6x6"]), ("7 × 7", g["7x7"]), ("8 × 8 (padrão)", g["8x8"]), ("10 × 10", g["10x10"])])
    p = res["preprocessamento"]
    pre = tab("pre", "Efeito do pré-processamento", [
        ("CLAHE e máscara elíptica (padrão)", p["CLAHE + máscara (padrão)"]), ("Sem máscara", p["sem máscara"]),
        ("Equalização global", p["equalização global"]), ("Sem equalização", p["sem equalização"]),
        ("Sem equalização e sem máscara", p["sem equalização e sem máscara"])])
    d, k, mt = res["distancia"], res["k"], res["metodo"]
    nome_pca = [n for n in mt if n.startswith("Eigenfaces, melhor")][0]
    dist = tab("dist", "Efeito da medida de distância, do número de amostras na decisão e do método", [
        ("Distância qui-quadrado (padrão)", d["qui-quadrado"]), ("Distância euclidiana", d["euclidiana"]),
        ("Interseção de histogramas", d["interseção de histogramas"]),
        ("Decisão pela menor distância (k = 1, padrão)", k["1"]),
        ("Média das duas menores distâncias (k = 2)", k["2"]), ("Média das três menores distâncias (k = 3)", k["3"]),
        ("*Eigenfaces* (PCA com 40 componentes) e distância euclidiana", mt["Eigenfaces (PCA 40) + euclidiana"]),
        ("*Eigenfaces*, melhor configuração testada (" + nome_pca.split("(", 1)[1], mt[nome_pca]),
        ("LBP sem CLAHE e sem máscara (qui-quadrado), para comparação justa", p["sem equalização e sem máscara"]),
        ("*Eigenfaces* sem CLAHE (PCA com 80 componentes e cosseno)", mt["Eigenfaces sem CLAHE (PCA 80 + cosseno)"])])
    c = res["cadastro"]
    cad = tab("cadastro", "Efeito do número de imagens de cadastro por pessoa", [
        (f"{n} imagens de cadastro" + (" (padrão)" if n == "5" else ""), c[n]) for n in ("2", "3", "5", "7")])
    par = res["pareados"]
    linhas_p = ["| Comparação (variante contra referência) | Diferença média (pontos percentuais) | Intervalo de confiança de 95% | Divisões em que a variante é pior (%) |"]
    for nome, v in par.items():
        linhas_p.append(f"| {nome} | {sinal(v['media'])} | {sinal(v['ic_inf'])} a {sinal(v['ic_sup'])} | {fmt(v['fracao_positiva'], 0)} |")
    pareados = (f"[TAB pareados | Diferenças pareadas de EER entre variantes, nas mesmas 30 divisões | {legenda} | 46,16,22,16]\n"
                + "\n".join(linhas_p))
    return (texto.replace("@@T:pareados@@", pareados).replace("@@T:grade@@", grade).replace("@@T:pre@@", pre)
            .replace("@@T:dist@@", dist).replace("@@T:cadastro@@", cad))


def capa(m):
    def par(txt, antes=0, negrito=False, tam=12):
        p = m._escrever(txt, "Capa", espaco_antes=antes)
        if negrito:
            p.Font.Bold = True
        p.Font.Size = tam
        return p

    if IMAGEM_LOGO.exists():
        r = m._fim()
        pic = m.doc.InlineShapes.AddPicture(str(IMAGEM_LOGO), False, True, r)
        pic.LockAspectRatio = True
        pic.Width = 3.0 * CM
        pic.Range.Paragraphs(1).Style = m.doc.Styles("Capa")
        m._fim().InsertParagraphAfter()
    par(G["instituicao"].replace(" - ", " – ").upper(), 6, True)
    par("CURSO DE " + G["curso"].upper(), 6, True)
    par("Turma " + G["turma"], 6)
    for i, a in enumerate(G["integrantes"]):
        par(f"{a['nome']} – RA: {a['ra']}", 36 if i == 0 else 4)
    par(G["titulo"].upper(), 90, True)
    par("Atividades Práticas Supervisionadas (APS) – " + G["disciplina"], 24)
    par(G["cidade"], 110)
    par(G["ano"], 0)


def folha_de_rosto(m):
    def par(txt, antes=0, negrito=False, alinh=wdAlignCenter, esq=0.0):
        p = m._escrever(txt, "Capa", alinh=alinh, espaco_antes=antes)
        p.Font.Bold = negrito
        p.ParagraphFormat.LeftIndent = esq * CM
        return p

    for i, a in enumerate(G["integrantes"]):
        par(f"{a['nome']} – RA: {a['ra']}", 0 if i == 0 else 4)
    par(G["titulo"].upper(), 110, True)
    nota = (f"Trabalho de Atividades Práticas Supervisionadas apresentado ao curso de {G['curso']} da "
            f"{G['instituicao'].split(' - ')[0]}, turma {G['turma']}, na disciplina {G['disciplina']}, "
            f"sob orientação do(a) Prof.(a) {G['orientador']}.")
    par(nota, 90, False, wdAlignLeft, 8.0)
    par(G["cidade"], 130)
    par(G["ano"], 0)


def tabela_ficha(m, aluno):
    def linha(txt, antes=0):
        return m._escrever(txt, "Texto simples", espaco_antes=antes)

    p = linha(f"**NOME:** {aluno['nome']}     **TURMA:** {G['turma']}     **RA:** {aluno['ra']}")
    p.ParagraphFormat.SpaceAfter = 0
    p.ParagraphFormat.LineSpacingRule = 0
    for txt in (f"**CURSO:** {G['curso']}     **CAMPUS:** {G['campus']}     **SEMESTRE:** {G['semestre']}",
                f"**TURNO:** ________     **CÓDIGO DA ATIVIDADE:** ______________     **ANO GRADE:** ________"):
        q = linha(txt, 4)
        q.ParagraphFormat.LineSpacingRule = 0
        q.Font.Size = 10.5
    cab = ["DATA DA ATIVIDADE", "DESCRIÇÃO DA ATIVIDADE", "TOTAL DE HORAS", "ASSINATURA DO ALUNO",
           "HORAS ATRIBUÍDAS (1)", "ASSINATURA DO PROFESSOR"]
    n = len(ATIVIDADES_FICHA) + 5
    t = m.doc.Tables.Add(m._fim(), n + 1, 6)
    t.Range.Style = m.doc.Styles("Tabela texto")
    t.Range.ParagraphFormat.Reset(); t.Range.Font.Reset()
    t.Range.Font.Size = 9
    t.AllowAutoFit = False
    pesos = [2.0, 5.6, 1.6, 2.6, 1.8, 2.4]
    for j, w in enumerate(pesos):
        t.Columns(j + 1).Width = 16.0 * CM * w / sum(pesos)
    for j, c in enumerate(cab):
        t.Cell(1, j + 1).Range.Text = c
    t.Rows(1).Range.Font.Bold = True
    t.Rows(1).Shading.BackgroundPatternColor = 0xD9D9D9
    t.Rows(1).Range.ParagraphFormat.Alignment = wdAlignCenter
    for i, d in enumerate(ATIVIDADES_FICHA):
        t.Cell(i + 2, 2).Range.Text = d
    Montador.bordas_completas(t)
    t.Rows.AllowBreakAcrossPages = False
    t.Rows.Alignment = wdAlignCenter
    for i in range(2, t.Rows.Count + 1):       # linhas de preenchimento à mão
        t.Rows(i).HeightRule = 1                # no mínimo
        t.Rows(i).Height = 0.95 * CM
    m._escrever("(1) Horas atribuídas de acordo com o regulamento das Atividades Práticas Supervisionadas do curso.",
                "Texto simples", espaco_antes=4).Font.Size = 9
    for txt in ("**TOTAL DE HORAS ATRIBUÍDAS:** ______________     **AVALIAÇÃO:** ______________ (Aprovado ou Reprovado)",
                "**NOTA:** ______________     **DATA:** _____ / _____ / _________",
                "______________________________________________\nCARIMBO E ASSINATURA DO COORDENADOR DO CURSO"):
        q = linha(txt, 6)
        q.Font.Size = 10
        q.ParagraphFormat.LineSpacingRule = 0


def main():
    visivel = "--visivel" in sys.argv
    resultados = json.loads((DOCS / "resultados.json").read_text(encoding="utf-8"))
    textos = [preencher(p.read_text(encoding="utf-8"), resultados) for p in sorted(CONTEUDO.glob("0*.txt"))]
    blocos, rotulos = analisar(textos)
    m = Montador(visivel)
    m.rotulos = rotulos
    try:
        # ---- elementos pré-textuais -------------------------------------------
        capa(m)
        m.secao()
        folha_de_rosto(m)
        m._escrever("RESUMO", "Titulo sem numero")
        m._escrever(RESUMO, "Resumo texto")
        p = m._escrever("**Palavras-chave:** " + PALAVRAS, "Resumo texto")
        m._escrever("ABSTRACT", "Titulo sem numero")
        m._escrever(ABSTRACT, "Resumo texto")
        m._escrever("**Keywords:** " + KEYWORDS, "Resumo texto")
        for titulo, rotulo in (("LISTA DE FIGURAS", "Figura"), ("LISTA DE QUADROS", "Quadro"),
                               ("LISTA DE TABELAS", "Tabela"), ("LISTA DE CÓDIGOS", "Código")):
            if any(b["t"] == {"Figura": "fig", "Quadro": "quad", "Tabela": "tab", "Código": "cod"}[rotulo] for b in blocos):
                m._escrever(titulo, "Titulo sem numero")
                m.inserir_lista(rotulo)
        m._escrever("LISTA DE ABREVIATURAS E SIGLAS", "Titulo sem numero")
        for s, d in SIGLAS:
            m.sigla(s, d)
        m._escrever("SUMÁRIO", "Titulo sem numero")
        m.inserir_sumario()
        m.secao()
        # ---- elementos textuais, referências e apêndice ---------------------------
        m.renderizar(blocos, FIGS)
        # Página reservada: as fichas de APS de cada integrante serão coladas já digitalizadas
        m._escrever("Ficha APS", "Titulo primario sem numero")
        # ---- numeração, índices e verificação ---------------------------------
        m.numerar_paginas(secao_textual=3, secao_pre=2)
        m.atualizar()
        capitulos, total = m.paginas_por_capitulo()
        print("\nPÁGINAS POR CAPÍTULO (absolutas; a capa é a página 1 do arquivo)")
        for nome, pg, n in capitulos:
            print(f"  {n:3d} pág.  (início na pág. {pg:3d})  {nome[:70]}")
        print("Total de páginas do arquivo:", total)
        destino = DOCS / "APS_Biometria_Facial_Trabalho"
        m.salvar(str(destino) + ".docx", str(destino) + ".pdf")
        print("Gravado:", destino.with_suffix(".docx"))
    finally:
        if not visivel:
            m.fechar()


if __name__ == "__main__":
    main()

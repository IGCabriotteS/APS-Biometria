"""Montador de documentos Word (ABNT) a partir de um texto marcado simples.

Usa a automação COM do Microsoft Word (pywin32), de modo que o resultado é um
.docx nativo: estilos reais, sumário e listas de ilustrações atualizáveis,
legendas com campos SEQ e numeração de páginas por seção.

Marcação aceita nos arquivos de conteúdo (.txt, UTF-8):
    # Título                  seção primária (numerada, nova página)
    ## Título {#chave}        seção secundária;  ### Título  terciária
    #* TÍTULO                 seção primária sem número (REFERÊNCIAS, APÊNDICES)
    texto livre               parágrafo (linhas seguidas formam um parágrafo)
    - item                    alíneas a), b), c)... (linhas consecutivas)
    [FIG chave | arquivo.png | Título | Fonte | largura%]
    [QUADRO chave | Título | Fonte | larguras]   + linhas "| a | b |"
    [TAB chave | Título | Fonte | larguras]      + linhas "| a | b |"
    [COD chave | Título]                          + bloco ``` ... ```
    [EQ chave | expressão]
    [REF] item de referência (uma linha cada)
Dentro do texto: **negrito**, *itálico*, `código`, _{subscrito}, ^{sobrescrito},
{fig:chave} {quad:chave} {tab:chave} {cod:chave} {eq:chave} {sec:chave}.
"""

import re
import sys
from pathlib import Path

import win32com.client as win32

CM = 28.3465  # pontos por centímetro

# constantes do Word
wdAlignLeft, wdAlignCenter, wdAlignRight, wdAlignJustify = 0, 1, 2, 3
wdSectionBreakNextPage, wdPageBreak = 2, 7
wdLineSpaceSingle, wdLineSpaceMultiple = 0, 5
wdStyleNormal, wdStyleH1, wdStyleH2, wdStyleH3 = -1, -2, -3, -4
wdStyleTOC1, wdStyleTOC2, wdStyleTOC3 = -20, -21, -22
wdStyleCaption, wdStyleTOF = -35, -36
wdFieldPage = 33

PADRAO_INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`.+?`|_\{.+?\}|\^\{.+?\})")


def segmentos(texto):
    """Quebra um texto marcado em [(texto, formato)] com formato em
    {None, 'b', 'i', 'c', 'sub', 'sup'}."""
    saida = []
    for parte in PADRAO_INLINE.split(texto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**") and len(parte) > 4:
            saida.append((parte[2:-2], "b"))
        elif parte.startswith("`") and parte.endswith("`") and len(parte) > 2:
            saida.append((parte[1:-1], "c"))
        elif parte.startswith("_{") and parte.endswith("}"):
            saida.append((parte[2:-1], "sub"))
        elif parte.startswith("^{") and parte.endswith("}"):
            saida.append((parte[2:-1], "sup"))
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            saida.append((parte[1:-1], "i"))
        else:
            saida.append((parte, None))
    return saida


# ---------------------------------------------------------------------------
# análise do arquivo de conteúdo
# ---------------------------------------------------------------------------
def analisar(textos):
    """Converte o conteúdo em uma lista de blocos e numera tudo."""
    blocos = []
    for texto in textos:
        linhas = texto.replace("\r\n", "\n").split("\n")
        i = 0
        par = []

        def fechar():
            nonlocal par
            if par:
                blocos.append({"t": "p", "texto": " ".join(par)})
                par = []

        while i < len(linhas):
            ln = linhas[i].rstrip()
            if not ln.strip():
                fechar(); i += 1; continue
            if ln.startswith("#* "):
                fechar(); blocos.append({"t": "h1s", "texto": ln[3:].strip()})
            elif ln.startswith("### "):
                fechar(); blocos.append({"t": "h3", "texto": ln[4:].strip()})
            elif ln.startswith("## "):
                fechar(); blocos.append({"t": "h2", "texto": ln[3:].strip()})
            elif ln.startswith("# "):
                fechar(); blocos.append({"t": "h1", "texto": ln[2:].strip()})
            elif ln.startswith("- "):
                fechar()
                itens = []
                while i < len(linhas) and linhas[i].startswith("- "):
                    itens.append(linhas[i][2:].strip()); i += 1
                blocos.append({"t": "lista", "itens": itens}); continue
            elif ln.startswith("[FIG "):
                fechar()
                p = [x.strip() for x in ln[5:-1].split("|")]
                blocos.append({"t": "fig", "chave": p[0], "arq": p[1], "titulo": p[2],
                               "fonte": p[3], "larg": float(p[4]) if len(p) > 4 else 100})
            elif ln.startswith("[QUADRO ") or ln.startswith("[TAB "):
                fechar()
                tipo = "quad" if ln.startswith("[QUADRO ") else "tab"
                p = [x.strip() for x in ln[ln.index(" ") + 1:-1].split("|")]
                linhas_tab = []
                i += 1
                while i < len(linhas) and linhas[i].strip().startswith("|"):
                    celulas = [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                    linhas_tab.append(celulas); i += 1
                larg = [float(x) for x in p[3].split(",")] if len(p) > 3 and p[3] else None
                blocos.append({"t": tipo, "chave": p[0], "titulo": p[1], "fonte": p[2],
                               "linhas": linhas_tab, "larg": larg}); continue
            elif ln.startswith("[COD "):
                fechar()
                p = [x.strip() for x in ln[5:-1].split("|")]
                i += 1
                codigo = []
                if i < len(linhas) and linhas[i].startswith("```"):
                    i += 1
                    while i < len(linhas) and not linhas[i].startswith("```"):
                        codigo.append(linhas[i].rstrip("\n")); i += 1
                    i += 1
                blocos.append({"t": "cod", "chave": p[0], "titulo": p[1], "linhas": codigo,
                               "fonte": p[2] if len(p) > 2 else ""}); continue
            elif ln.startswith("[EQ "):
                fechar()
                p = [x.strip() for x in ln[4:-1].split("|", 1)]
                blocos.append({"t": "eq", "chave": p[0], "expr": p[1]})
            elif ln.startswith("[REF] "):
                fechar(); blocos.append({"t": "ref", "texto": ln[6:].strip()})
            else:
                par.append(ln.strip())
            i += 1
        fechar()

    # numeração e rótulos
    contagem = {"fig": 0, "quad": 0, "tab": 0, "cod": 0, "eq": 0}
    h = [0, 0, 0]
    rotulos = {}
    for b in blocos:
        t = b["t"]
        if t in ("h1", "h2", "h3"):
            m = re.search(r"\s*\{#([\w-]+)\}\s*$", b["texto"])
            chave = m.group(1) if m else None
            if m:
                b["texto"] = b["texto"][:m.start()]
            nivel = int(t[1])
            h[nivel - 1] += 1
            for k in range(nivel, 3):
                h[k] = 0
            numero = ".".join(str(x) for x in h[:nivel])
            b["numero"] = numero
            if chave:
                rotulos["sec:" + chave] = f"seção {numero}" if nivel > 1 else f"capítulo {numero}"
        elif t in contagem:
            contagem[t] += 1
            b["n"] = contagem[t]
            nome = {"fig": "Figura", "quad": "Quadro", "tab": "Tabela", "cod": "Código", "eq": "Equação"}[t]
            rotulos[f"{t}:{b['chave']}"] = f"{nome} {b['n']}" if t != "eq" else f"equação ({b['n']})"
    return blocos, rotulos


def resolver(texto, rotulos):
    def troca(m):
        chave = m.group(1)
        if chave not in rotulos:
            raise KeyError(f"Referência cruzada inexistente: {{{chave}}}")
        return rotulos[chave]
    # o rótulo de seção já traz a palavra "capítulo"/"seção": evita "capítulo capítulo 3"
    return re.sub(r"(?:(?:capítulo|seção) )?\{((?:fig|quad|tab|cod|eq|sec):[\w-]+)\}", troca, texto)


# ---------------------------------------------------------------------------
class Montador:
    def __init__(self, visivel=False):
        self.app = win32.gencache.EnsureDispatch("Word.Application")
        self.app.Visible = visivel
        self.app.DisplayAlerts = 0
        self.doc = self.app.Documents.Add()
        self.rotulos = {}
        self._configurar_pagina()
        self._criar_estilos()

    # -- configuração ----------------------------------------------------------
    def _configurar_pagina(self):
        ps = self.doc.PageSetup
        ps.PaperSize = 7  # wdPaperA4
        ps.TopMargin, ps.BottomMargin = 3 * CM, 2 * CM
        ps.LeftMargin, ps.RightMargin = 2.5 * CM, 2.5 * CM
        ps.HeaderDistance = 1.8 * CM
        ps.FooterDistance = 1.25 * CM

    def _estilo(self, nome, base=None, tipo=1):
        try:
            e = self.doc.Styles(nome)
        except Exception:
            e = self.doc.Styles.Add(nome, tipo)
        if base is not None:
            e.BaseStyle = base
        return e

    def _fonte(self, e, tam=12, negrito=False, italico=False, nome="Arial"):
        e.Font.Name, e.Font.Size = nome, tam
        e.Font.Bold, e.Font.Italic = negrito, italico
        e.Font.Color = 0
        e.Font.AllCaps = False

    def _para(self, e, alinh=wdAlignJustify, recuo1=0.0, esq=0.0, antes=0, depois=0,
              espac=1.5, manter=False, quebra=False):
        pf = e.ParagraphFormat
        pf.Alignment = alinh
        pf.FirstLineIndent = recuo1 * CM
        pf.LeftIndent = esq * CM
        pf.RightIndent = 0
        pf.SpaceBefore, pf.SpaceAfter = antes, depois
        if espac == 1.0:
            pf.LineSpacingRule = wdLineSpaceSingle
        else:
            pf.LineSpacingRule = wdLineSpaceMultiple
            pf.LineSpacing = 12 * espac
        pf.KeepWithNext = manter
        pf.PageBreakBefore = quebra
        pf.WidowControl = True

    def _criar_estilos(self):
        n = self.doc.Styles(wdStyleNormal)
        self._fonte(n); self._para(n, recuo1=1.25)
        # títulos
        for cod, tam_neg, ital, quebra in ((wdStyleH1, True, False, True), (wdStyleH2, True, False, False),
                                           (wdStyleH3, False, True, False)):
            e = self.doc.Styles(cod)
            self._fonte(e, 12, tam_neg, ital)
            self._para(e, alinh=wdAlignLeft, antes=0 if quebra else 12, depois=12 if cod == wdStyleH1 else 6,
                       manter=True, quebra=quebra)
        e = self._estilo("Titulo sem numero")
        e.BaseStyle = self.doc.Styles(wdStyleNormal)
        self._fonte(e, 12, True); self._para(e, alinh=wdAlignCenter, depois=12, manter=True, quebra=True)
        e = self._estilo("Titulo primario sem numero")   # aparece no sumário (referências, apêndices)
        e.BaseStyle = self.doc.Styles(wdStyleH1)
        e.NextParagraphStyle = self.doc.Styles(wdStyleNormal)
        self._fonte(e, 12, True); self._para(e, alinh=wdAlignLeft, depois=12, manter=True, quebra=True)
        e.ParagraphFormat.OutlineLevel = 1
        # legendas e fontes
        e = self.doc.Styles(wdStyleCaption)
        self._fonte(e, 10, False); self._para(e, alinh=wdAlignCenter, espac=1.0, antes=12, depois=4, manter=True)
        e = self._estilo("Fonte ilustracao")
        self._fonte(e, 10); self._para(e, alinh=wdAlignCenter, espac=1.0, antes=2, depois=12)
        e = self._estilo("Ilustracao")
        self._fonte(e, 10); self._para(e, alinh=wdAlignCenter, espac=1.0, manter=True)
        e = self._estilo("Alinea")
        e.BaseStyle = self.doc.Styles(wdStyleNormal)
        self._fonte(e); self._para(e, esq=1.9, recuo1=-0.65)
        e = self._estilo("Codigo")
        self._fonte(e, 8.5, nome="Courier New"); self._para(e, alinh=wdAlignLeft, espac=1.0, esq=0.0)
        e.ParagraphFormat.Shading.BackgroundPatternColor = 0xF2F2F2
        e = self._estilo("Tabela texto")
        self._fonte(e, 10); self._para(e, alinh=wdAlignLeft, espac=1.0, antes=2, depois=2)
        e = self._estilo("Equacao")
        self._fonte(e); self._para(e, alinh=wdAlignLeft, recuo1=0, espac=1.5)
        e = self._estilo("Referencia")
        self._fonte(e); self._para(e, alinh=wdAlignLeft, espac=1.0, depois=12)
        e = self._estilo("Resumo texto")
        self._fonte(e); self._para(e, recuo1=0, espac=1.0, depois=12)
        e = self._estilo("Capa")
        self._fonte(e); self._para(e, alinh=wdAlignCenter, recuo1=0, espac=1.0)
        e = self._estilo("Texto simples")
        self._fonte(e); self._para(e, alinh=wdAlignLeft, recuo1=0, espac=1.5)
        e = self._estilo("Sigla")
        self._fonte(e); self._para(e, alinh=wdAlignLeft, recuo1=-3.0, esq=3.0, espac=1.0, depois=6)
        e.ParagraphFormat.TabStops.ClearAll()
        e.ParagraphFormat.TabStops.Add(3.0 * CM, 0)
        for cod, neg in ((wdStyleTOC1, True), (wdStyleTOC2, False), (wdStyleTOC3, False)):
            e = self.doc.Styles(cod)
            self._fonte(e, 12, neg)
            self._para(e, alinh=wdAlignLeft, espac=1.0, depois=4)
        self._para(self.doc.Styles(wdStyleTOC2), alinh=wdAlignLeft, espac=1.0, depois=3, esq=0.5)
        self._para(self.doc.Styles(wdStyleTOC3), alinh=wdAlignLeft, espac=1.0, depois=3, esq=1.0)
        e = self.doc.Styles(wdStyleTOF)
        self._fonte(e); self._para(e, alinh=wdAlignLeft, espac=1.0, depois=6)
        e = self.doc.Styles(-32)  # cabeçalho
        self._fonte(e, 10); self._para(e, alinh=wdAlignRight, recuo1=0, espac=1.0)

    # -- primitivas ------------------------------------------------------------
    def _fim(self):
        return self.doc.Range(self.doc.Content.End - 1, self.doc.Content.End - 1)

    def _escrever(self, texto, estilo, alinh=None, espaco_antes=None, manter=None):
        """Acrescenta um parágrafo com formatação inline ao fim do documento."""
        r = self._fim()
        partes = segmentos(texto)
        plano = "".join(p for p, _ in partes)
        inicio = r.Start
        r.InsertAfter(plano)
        par = self.doc.Range(inicio, inicio + len(plano))
        par.Style = self.doc.Styles(estilo) if isinstance(estilo, str) else self.doc.Styles(estilo)
        par.ParagraphFormat.Reset()
        par.Font.Reset()
        if alinh is not None:
            par.ParagraphFormat.Alignment = alinh
        if espaco_antes is not None:
            par.ParagraphFormat.SpaceBefore = espaco_antes
        if manter is not None:
            par.ParagraphFormat.KeepWithNext = manter
        pos = inicio
        for p, fmt in partes:
            if fmt:
                sub = self.doc.Range(pos, pos + len(p))
                if fmt == "b":
                    sub.Font.Bold = True
                elif fmt == "i":
                    sub.Font.Italic = True
                elif fmt == "c":
                    sub.Font.Name = "Courier New"; sub.Font.Size = 10.5
                elif fmt == "sub":
                    sub.Font.Subscript = True
                elif fmt == "sup":
                    sub.Font.Superscript = True
            pos += len(p)
        self._fim().InsertParagraphAfter()
        return par

    def paragrafo(self, texto):
        par = self._escrever(resolver(texto, self.rotulos), wdStyleNormal)
        if texto.startswith("em que "):          # continuação de uma equação: sem recuo
            par.ParagraphFormat.FirstLineIndent = 0
        return par

    def titulo(self, nivel, texto, numero=None):
        estilo = {1: wdStyleH1, 2: wdStyleH2, 3: wdStyleH3}[nivel]
        rotulo = f"{numero} {texto}" if numero else texto
        if nivel == 1:
            rotulo = rotulo.upper() if not numero else f"{numero} {texto.upper()}"
        return self._escrever(rotulo, estilo)

    def lista(self, itens):
        letras = "abcdefghijklmnopqrstuvwxyz"
        for k, item in enumerate(itens):
            item = resolver(item.rstrip(".;:"), self.rotulos)
            fim = "." if k == len(itens) - 1 else ";"
            self._escrever(f"{letras[k]}) {item}{fim}", "Alinea")

    @staticmethod
    def _id_seq(rotulo):
        """Identificador de sequência sem acento (campos SEQ exigem letras simples)."""
        return rotulo.replace("ó", "o").replace("Ó", "O")

    def _legenda(self, rotulo, n, titulo):
        r = self._fim()
        inicio = r.Start
        r.InsertAfter(f"{rotulo} ")
        par = self.doc.Range(inicio, inicio + len(rotulo) + 1)
        par.Style = self.doc.Styles(wdStyleCaption)
        par.ParagraphFormat.Reset(); par.Font.Reset()
        self.doc.Fields.Add(self._fim(), -1, f"SEQ {self._id_seq(rotulo)} \\* ARABIC", False)
        self._fim().InsertAfter(f" – {titulo}")
        self._fim().InsertParagraphAfter()

    def _fonte_ilustracao(self, texto):
        if texto:
            self._escrever(resolver(texto, self.rotulos), "Fonte ilustracao")

    def figura(self, b, pasta):
        self._legenda("Figura", b["n"], resolver(b["titulo"], self.rotulos))
        r = self._fim()
        caminho = str((pasta / b["arq"]).resolve())
        pic = self.doc.InlineShapes.AddPicture(caminho, False, True, r)
        largura_max = 16.0 * CM
        pic.LockAspectRatio = True
        pic.Width = largura_max * b["larg"] / 100.0
        altura_max = 17.5 * CM
        if pic.Height > altura_max:
            pic.Height = altura_max
        par = pic.Range.Paragraphs(1)
        par.Style = self.doc.Styles("Ilustracao")
        self._fim().InsertParagraphAfter()
        self._fonte_ilustracao(b["fonte"])

    def tabela(self, b, tipo):
        rotulo = "Quadro" if tipo == "quad" else "Tabela"
        self._legenda(rotulo, b["n"], resolver(b["titulo"], self.rotulos))
        linhas = b["linhas"]
        ncol = max(len(l) for l in linhas)
        t = self.doc.Tables.Add(self._fim(), len(linhas), ncol)
        t.Range.Style = self.doc.Styles("Tabela texto")
        t.Range.ParagraphFormat.Reset(); t.Range.Font.Reset()
        t.AllowAutoFit = False
        t.Rows.AllowBreakAcrossPages = False
        t.Rows(1).HeadingFormat = True
        # mantém a tabela inteira na mesma página (quando cabe): todas as linhas,
        # menos a última, "grudam" na seguinte
        t.Range.ParagraphFormat.KeepWithNext = True
        t.Rows(t.Rows.Count).Range.ParagraphFormat.KeepWithNext = False
        largura_total = 16.0 * CM
        pesos = b["larg"] or [1] * ncol
        if len(pesos) != ncol:
            raise ValueError(f"Tabela '{b['chave']}': {len(pesos)} larguras para {ncol} colunas")
        soma = float(sum(pesos))
        for j in range(ncol):
            t.Columns(j + 1).Width = largura_total * pesos[j] / soma
        for i, linha in enumerate(linhas):
            for j in range(ncol):
                txt = resolver(linha[j], self.rotulos) if j < len(linha) else ""
                celula = t.Cell(i + 1, j + 1)
                partes = segmentos(txt)
                celula.Range.Text = "".join(p for p, _ in partes)
                pos = celula.Range.Start
                for p, fmt in partes:
                    if fmt:
                        sub = self.doc.Range(pos, pos + len(p))
                        if fmt == "b": sub.Font.Bold = True
                        elif fmt == "i": sub.Font.Italic = True
                        elif fmt == "c": sub.Font.Name = "Courier New"; sub.Font.Size = 8.5
                        elif fmt == "sub": sub.Font.Subscript = True
                        elif fmt == "sup": sub.Font.Superscript = True
                    pos += len(p)
                if i == 0:
                    celula.Range.Font.Bold = True
        # bordas
        if tipo == "quad":
            self.bordas_completas(t)
            t.Rows(1).Shading.BackgroundPatternColor = 0xD9D9D9
        else:
            t.Borders.Enable = False
            for b_id in (-1, -3):  # superior, inferior
                t.Borders(b_id).LineStyle = 1
            t.Rows(1).Borders(-3).LineStyle = 1
        t.Rows.Alignment = wdAlignCenter
        self._fonte_ilustracao(b["fonte"])

    @staticmethod
    def bordas_completas(t, espessura=4):
        """Grade completa: contorno e linhas internas, horizontais e verticais."""
        for borda in (-1, -2, -3, -4, -5, -6):
            t.Borders(borda).LineStyle = 1
            t.Borders(borda).LineWidth = espessura   # 4 = 0,5 pt

    def codigo(self, b):
        self._legenda("Código", b["n"], resolver(b["titulo"], self.rotulos))
        ultimo = len(b["linhas"]) - 1
        for k, linha in enumerate(b["linhas"]):
            par = self._escrever(linha if linha else " ", "Codigo", manter=(k != ultimo))
        self._fonte_ilustracao(b["fonte"] or "Elaborado pelos autores (2026).")

    def equacao(self, b):
        r = self._fim()
        partes = segmentos(resolver(b["expr"], self.rotulos))
        plano = "".join(p for p, _ in partes)
        inicio = r.Start
        r.InsertAfter(f"\t{plano}\t({b['n']})")
        par = self.doc.Range(inicio, inicio + len(plano) + len(str(b["n"])) + 4)
        par.Style = self.doc.Styles("Equacao")
        par.ParagraphFormat.Reset(); par.Font.Reset()
        pf = par.ParagraphFormat
        pf.TabStops.ClearAll()
        pf.TabStops.Add(8.0 * CM, 1)      # centralizada
        pf.TabStops.Add(16.0 * CM, 2)     # número à direita
        pos = inicio + 1
        for p, fmt in partes:
            if fmt:
                sub = self.doc.Range(pos, pos + len(p))
                if fmt == "i": sub.Font.Italic = True
                elif fmt == "sub": sub.Font.Subscript = True
                elif fmt == "sup": sub.Font.Superscript = True
                elif fmt == "b": sub.Font.Bold = True
            pos += len(p)
        self._fim().InsertParagraphAfter()

    def referencia(self, texto):
        self._escrever(resolver(texto, self.rotulos), "Referencia")

    def secao(self):
        self._fim().InsertBreak(wdSectionBreakNextPage)

    # -- renderização de blocos --------------------------------------------------
    def renderizar(self, blocos, pasta_figuras):
        for b in blocos:
            t = b["t"]
            if t == "p":
                self.paragrafo(b["texto"])
            elif t in ("h1", "h2", "h3"):
                self.titulo(int(t[1]), b["texto"], b["numero"])
            elif t == "h1s":
                self._escrever(b["texto"].upper(), "Titulo primario sem numero")
            elif t == "lista":
                self.lista(b["itens"])
            elif t == "fig":
                self.figura(b, pasta_figuras)
            elif t == "quad":
                self.tabela(b, "quad")
            elif t == "tab":
                self.tabela(b, "tab")
            elif t == "cod":
                self.codigo(b)
            elif t == "eq":
                self.equacao(b)
            elif t == "ref":
                self.referencia(b["texto"])

    # -- índices e cabeçalhos ------------------------------------------------------
    def inserir_sumario(self):
        self.doc.TablesOfContents.Add(self._fim(), True, 1, 3)
        self._fim().InsertParagraphAfter()

    def inserir_lista(self, rotulo):
        self.doc.TablesOfFigures.Add(self._fim(), self._id_seq(rotulo), True)
        self._fim().InsertParagraphAfter()

    def sigla(self, sigla, significado):
        par = self._escrever(f"{sigla}\t{significado}", "Sigla")
        return par

    def quebra_pagina(self):
        self._fim().InsertBreak(wdPageBreak)

    def numerar_paginas(self, secao_textual, secao_pre=None):
        for i in range(1, self.doc.Sections.Count + 1):
            sec = self.doc.Sections(i)
            sec.PageSetup.DifferentFirstPageHeaderFooter = False
            if i > 1:
                sec.Headers(1).LinkToPrevious = False
                sec.Footers(1).LinkToPrevious = False
            hdr = sec.Headers(1)
            hdr.Range.Text = ""
            if i >= secao_textual:
                hdr.Range.Fields.Add(hdr.Range, wdFieldPage)
                hdr.Range.ParagraphFormat.Alignment = wdAlignRight
                hdr.Range.Font.Name, hdr.Range.Font.Size = "Arial", 10
        if secao_pre:
            pn = self.doc.Sections(secao_pre).Headers(1).PageNumbers
            pn.RestartNumberingAtSection = True
            pn.StartingNumber = 1
        pn = self.doc.Sections(secao_textual).Headers(1).PageNumbers
        pn.RestartNumberingAtSection = False

    def atualizar(self):
        self.doc.Repaginate()
        for _ in range(2):
            for toc in self.doc.TablesOfContents:
                toc.Update()
            for tof in self.doc.TablesOfFigures:
                tof.Update()
            self.doc.Fields.Update()
            self.doc.Repaginate()

    def paginas_por_capitulo(self):
        """[(titulo, pagina_inicial_absoluta, paginas)] dos títulos primários."""
        inicios = []
        for p in self.doc.Paragraphs:
            nome = p.Style.NameLocal
            if nome in (self.doc.Styles(wdStyleH1).NameLocal, "Titulo primario sem numero"):
                txt = p.Range.Text.strip()
                inicios.append((txt, p.Range.Information(3)))
        total = self.doc.ComputeStatistics(2)  # wdStatisticPages
        saida = []
        for k, (txt, pg) in enumerate(inicios):
            fim = inicios[k + 1][1] if k + 1 < len(inicios) else total + 1
            saida.append((txt, pg, fim - pg))
        return saida, total

    def salvar(self, destino_docx, destino_pdf=None):
        destino_docx = str(Path(destino_docx).resolve())
        self.doc.SaveAs2(destino_docx, 16)  # wdFormatDocumentDefault
        if destino_pdf:
            self.doc.ExportAsFixedFormat(str(Path(destino_pdf).resolve()), 17)  # PDF

    def fechar(self):
        try:
            self.doc.Close(False)
        finally:
            self.app.Quit()

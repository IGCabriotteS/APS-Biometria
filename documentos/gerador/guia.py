"""Gera o guia do grupo ou o passo a passo (Word + PDF).

Uso: python guia.py                      -> guia.txt  => APS_Biometria_Guia_do_Grupo
     python guia.py passo_a_passo APS_Biometria_Passo_a_Passo "Passo a passo de teste"
"""

import sys

import json
from pathlib import Path

from docgen import CM, Montador, analisar

RAIZ = Path(__file__).resolve().parent
DOCS = RAIZ.parent
G = json.loads((RAIZ / "grupo.json").read_text(encoding="utf-8"))


def main():
    origem = sys.argv[1] if len(sys.argv) > 1 else "guia"
    saida = sys.argv[2] if len(sys.argv) > 2 else "APS_Biometria_Guia_do_Grupo"
    cabecalho = sys.argv[3] if len(sys.argv) > 3 else "Sistema biométrico facial para cofre de segurança máxima"
    texto = (DOCS / "conteudo_guia" / f"{origem}.txt").read_text(encoding="utf-8")
    blocos, rotulos = analisar([texto])
    m = Montador(False)
    m.rotulos = rotulos
    try:
        d = m.doc
        # estilo mais leve que o do trabalho: é um guia de leitura, não um trabalho ABNT
        n = d.Styles(-1)
        n.Font.Size = 11
        n.ParagraphFormat.FirstLineIndent = 0
        n.ParagraphFormat.Alignment = 0
        n.ParagraphFormat.LineSpacingRule = 5
        n.ParagraphFormat.LineSpacing = 12 * 1.15
        n.ParagraphFormat.SpaceAfter = 6
        al = d.Styles("Alinea")
        al.Font.Size = 11
        al.ParagraphFormat.LineSpacingRule = 5
        al.ParagraphFormat.LineSpacing = 12 * 1.15
        al.ParagraphFormat.SpaceAfter = 3
        for cod in (-2, -3):
            e = d.Styles(cod)
            e.ParagraphFormat.PageBreakBefore = False
            e.ParagraphFormat.SpaceBefore = 14
            e.Font.Color = 0x6F4F1F
        d.Styles(-2).Font.Size = 14
        d.Styles(-3).Font.Size = 12
        d.PageSetup.TopMargin = 2.2 * CM
        d.PageSetup.BottomMargin = 2.0 * CM

        p = m._escrever(cabecalho, "Capa", alinh=0)
        p.Font.Size = 10; p.Font.Color = 0x808080
        m.renderizar(blocos, DOCS.parent / "figuras")
        # remove o parágrafo vazio final e numera as páginas no rodapé direito
        m.numerar_paginas(secao_textual=1)
        m.atualizar()
        print("Páginas:", d.ComputeStatistics(2))
        destino = DOCS / saida
        m.salvar(str(destino) + ".docx", str(destino) + ".pdf")
        print("Gravado:", destino.with_suffix(".docx"))
    finally:
        m.fechar()


if __name__ == "__main__":
    main()

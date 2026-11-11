"""Gera o 'Relatório com as linhas de código' (Word + PDF) a partir dos arquivos .py.

Uso (na pasta documentos\\gerador):  python relatorio_codigo.py
"""

import json
from pathlib import Path

from docgen import CM, Montador

RAIZ = Path(__file__).resolve().parent
DOCS = RAIZ.parent
CODIGO = DOCS.parent / "codigo"
G = json.loads((RAIZ / "grupo.json").read_text(encoding="utf-8"))

DESCRICAO = {
    "cofre/__init__.py": "Apresentação do pacote e da organização por fases.",
    "cofre/__main__.py": "Ponto de entrada: menu e subcomandos de linha de comando.",
    "cofre/config.py": "Parâmetros centrais de desempenho e segurança (limiar, janelas, tempos).",
    "cofre/erros.py": "Exceções específicas do sistema.",
    "cofre/aquisicao.py": "Fase 1: câmera e leitura de arquivos de imagem.",
    "cofre/preprocessamento.py": "Fase 2: tons de cinza, ruído, equalização, normalização e qualidade.",
    "cofre/segmentacao.py": "Fase 3: detecção, recorte, alinhamento e máscara do rosto.",
    "cofre/caracteristicas.py": "Fase 4: LBP uniforme e histograma por blocos.",
    "cofre/classificacao.py": "Fase 5: distância qui-quadrado, decisão em conjunto aberto, votação e integridade do modelo.",
    "cofre/pipeline.py": "Encadeamento das cinco fases e guarda das imagens intermediárias.",
    "cofre/prova_vida.py": "Desafio de piscada (prova de vida).",
    "cofre/autenticacao.py": "Sessão de autenticação em tempo real e bloqueio do terminal.",
    "cofre/politica.py": "Regras dos três níveis de acesso.",
    "cofre/banco.py": "Banco SQLite: usuários, compartimentos e histórico encadeado por hash.",
    "cofre/servico.py": "Operações de negócio que unem os módulos (cadastro, treino, decisão, registro).",
    "cofre/relatorios.py": "Relatórios de acessos e de usuários.",
    "cofre/avaliacao.py": "Medição de FAR, FRR e EER em uma base de imagens.",
    "cofre/interface.py": "Menus, janelas em tempo real, painel das fases e telas de resultado.",
    "testes/_ambiente.py": "Isola os testes em uma pasta temporária.",
    "testes/test_fases.py": "Testes das fases de pré-processamento, segmentação, características e classificação.",
    "testes/test_seguranca.py": "Testes de política, banco, prova de vida, sessão e bloqueio.",
    "testes/test_integracao.py": "Teste de ponta a ponta sem câmera, com a base ORL.",
    "ferramentas/experimentos.py": "Experimentos reproduzíveis do capítulo de resultados.",
    "ferramentas/gerar_figuras.py": "Geração das figuras do relatório.",
}
GRUPOS = [("cofre", "Pacote do sistema (cofre)"), ("testes", "Testes automatizados"),
          ("ferramentas", "Ferramentas de experimentos e figuras")]
ORDEM_COFRE = ["__init__", "__main__", "config", "erros", "aquisicao", "preprocessamento", "segmentacao",
               "caracteristicas", "classificacao", "pipeline", "prova_vida", "autenticacao", "politica",
               "banco", "servico", "relatorios", "avaliacao", "interface"]


def arquivos(pasta):
    todos = {p.stem: p for p in (CODIGO / pasta).glob("*.py")}
    if pasta == "cofre":
        return [todos[n] for n in ORDEM_COFRE if n in todos]
    return [todos[k] for k in sorted(todos)]


def main():
    m = Montador(False)
    try:
        doc = m.doc
        # capa simples
        def par(txt, antes=0, negrito=False, tam=12):
            p = m._escrever(txt, "Capa", espaco_antes=antes)
            p.Font.Bold = negrito
            p.Font.Size = tam

        par("RELATÓRIO COM AS LINHAS DE CÓDIGO", 120, True, 14)
        par(G["titulo"], 18, False)
        par(f"Atividades Práticas Supervisionadas – {G['disciplina']}", 30)
        par(f"{G['curso']} – Turma {G['turma']}", 6)
        for i, a in enumerate(G["integrantes"]):
            par(f"{a['nome']} – RA: {a['ra']}", 30 if i == 0 else 4)
        par("Linguagem: Python 3.12 · Bibliotecas: OpenCV 4.11 e NumPy · Banco: SQLite", 60, False, 10)

        total_linhas = 0
        corpo = []
        for pasta, titulo in GRUPOS:
            fs = arquivos(pasta)
            corpo.append((pasta, titulo, fs))
            total_linhas += sum(len(f.read_text(encoding="utf-8").splitlines()) for f in fs)
        par(f"Total: {sum(len(fs) for _, _, fs in corpo)} arquivos, {total_linhas} linhas", 6, False, 10)

        m._escrever("SUMÁRIO", "Titulo sem numero")
        m.inserir_sumario()

        for k, (pasta, titulo, fs) in enumerate(corpo, start=1):
            m._escrever(f"{k} {titulo.upper()}", -2)           # Título 1
            for j, arq in enumerate(fs, start=1):
                rel = f"{pasta}/{arq.name}"
                m._escrever(f"{k}.{j} {rel}", -3)               # Título 2
                m._escrever(DESCRICAO.get(rel, ""), "Texto simples")
                linhas = arq.read_text(encoding="utf-8").splitlines()
                largura = len(str(len(linhas)))
                bloco = "\r".join(f"{n:>{largura}}  {ln.replace(chr(9), '    ')}"
                                  for n, ln in enumerate(linhas, start=1))
                r = m._fim()
                inicio = r.Start
                r.InsertAfter(bloco)
                faixa = doc.Range(inicio, inicio + len(bloco))
                faixa.Style = doc.Styles("Codigo")
                faixa.Font.Size = 8
                faixa.ParagraphFormat.Shading.BackgroundPatternColor = -16777216  # sem sombreamento
                m._fim().InsertParagraphAfter()
            print("ok", pasta, len(fs), "arquivos")

        # numeração: capa sem número, resto com número no canto superior direito
        m.numerar_paginas(secao_textual=1)
        doc.Sections(1).PageSetup.DifferentFirstPageHeaderFooter = True
        m.atualizar()
        total = doc.ComputeStatistics(2)
        print("Páginas:", total)
        destino = DOCS / "APS_Biometria_Relatorio_de_Codigo"
        m.salvar(str(destino) + ".docx", str(destino) + ".pdf")
        print("Gravado:", destino.with_suffix(".docx"))
    finally:
        m.fechar()


if __name__ == "__main__":
    main()

"""Relatórios de auditoria: acessos, usuários e resumo estatístico.

Gera arquivos CSV (abrem no Excel) e um resumo em texto. O relatório de
acessos sempre começa informando se o histórico está íntegro.
"""

import csv
from collections import Counter
from datetime import datetime

from . import config


def _carimbo():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def relatorio_acessos(banco, desde=None):
    """Grava CSV com os acessos e devolve (caminho_csv, texto_do_resumo)."""
    acessos = banco.listar_acessos(desde)
    integro, linha_ruim = banco.verificar_integridade()
    config.PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho = config.PASTA_RELATORIOS / f"acessos_{_carimbo()}.csv"

    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["data_hora", "usuario", "compartimento", "resultado",
                           "motivo", "distancia"])
        for a in acessos:
            dist = "" if a["distancia"] is None else f"{a['distancia']:.4f}".replace(".", ",")
            escritor.writerow([a["data_hora"], a["nome"], a["compartimento"],
                               a["resultado"], a["motivo"], dist])

    # operações administrativas (cadastro, remoção, retreino) não são tentativas de acesso
    administrativos = sum(1 for a in acessos if a["resultado"] == "ADMIN")
    tentativas = [a for a in acessos if a["resultado"] != "ADMIN"]
    total = len(tentativas)
    permitidos = sum(1 for a in tentativas if a["resultado"] == "PERMITIDO")
    negados = total - permitidos
    por_comp = Counter(a["compartimento"] for a in tentativas)
    por_motivo = Counter(a["motivo"] for a in tentativas if a["resultado"] == "NEGADO")
    por_usuario = Counter(a["nome"] for a in tentativas)

    linhas = ["RELATÓRIO DE ACESSOS AO COFRE",
              f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}"]
    if desde:
        linhas.append(f"Período: a partir de {desde}")
    linhas.append("Integridade do histórico: " +
                  ("ÍNTEGRO" if integro else f"VIOLADO (primeira linha suspeita: {linha_ruim})"))
    linhas += ["", f"Total de tentativas: {total}",
               f"  Permitidas: {permitidos}", f"  Negadas:    {negados}"]
    if total:
        linhas.append(f"  Taxa de negação: {100.0 * negados / total:.1f}%")
    linhas.append(f"Operações administrativas registradas: {administrativos}")
    if por_comp:
        linhas += ["", "Tentativas por compartimento:"]
        linhas += [f"  {n:3d}  {c}" for c, n in por_comp.most_common()]
    if por_motivo:
        linhas += ["", "Motivos de negação:"]
        linhas += [f"  {n:3d}  {m}" for m, n in por_motivo.most_common()]
    if por_usuario:
        linhas += ["", "Tentativas por usuário:"]
        linhas += [f"  {n:3d}  {u}" for u, n in por_usuario.most_common()]
    linhas += ["", f"Arquivo CSV: {caminho}"]
    return caminho, "\n".join(linhas)


def relatorio_usuarios(banco):
    """Grava CSV com os usuários (sem qualquer dado biométrico)."""
    config.PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho = config.PASTA_RELATORIOS / f"usuarios_{_carimbo()}.csv"
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["id", "nome", "cargo", "nivel", "divisao", "ativo", "criado_em"])
        for u in banco.listar_usuarios(apenas_ativos=False):
            escritor.writerow([u["id"], u["nome"], u["cargo"], u["nivel"],
                               u["divisao"] or "", "sim" if u["ativo"] else "não",
                               u["criado_em"]])
    return caminho

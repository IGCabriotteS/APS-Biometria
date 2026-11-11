"""Ponto de entrada: `python -m cofre` abre o menu; subcomandos servem para
demonstrar partes do sistema sem câmera (arquivo de imagem, base pública)."""

import argparse
import sys

from . import avaliacao, config
from .erros import ErroCofre
from .interface import Menu
from .servico import Cofre


def _montar_parser():
    p = argparse.ArgumentParser(prog="cofre", description=__doc__)
    sub = p.add_subparsers(dest="comando")

    a = sub.add_parser("autenticar-arquivo", help="autentica a partir de uma imagem")
    a.add_argument("imagem")
    a.add_argument("--compartimento", type=int, required=True, help="id do compartimento")
    a.add_argument("--recorte", action="store_true",
                   help="a imagem já contém só o rosto (pula a detecção)")

    v = sub.add_parser("avaliar", help="mede FAR/FRR/EER em uma base de imagens")
    v.add_argument("pasta", help="pasta com uma subpasta por pessoa")
    v.add_argument("--amostras", type=int, default=5, help="imagens de cadastro por pessoa")
    v.add_argument("--detectar", action="store_true",
                   help="roda o detector de rosto (use se as imagens forem fotos completas)")
    v.add_argument("--csv", help="grava a curva FAR x FRR neste arquivo CSV")
    sub.add_parser("diagnostico", help="testa câmera, detecção de rosto/olhos e piscada")
    sub.add_parser("calibrar", help="mede distâncias entre as amostras de cadastro reais (limiar)")
    sub.add_parser("retreinar", help="ação LOCAL: refaz o modelo a partir das amostras guardadas")
    sub.add_parser("trocar-ministro", help="ação LOCAL: substitui o ministro e cadastra o novo")
    return p


def main(argv=None):
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    args = _montar_parser().parse_args(argv)
    try:
        if args.comando == "avaliar":
            relatorio = avaliacao.avaliar(args.pasta, args.amostras, args.detectar)
            print(avaliacao.resumo(relatorio))
            if args.csv:
                print("CSV:", avaliacao.salvar_csv(relatorio, args.csv))
            return 0
        cofre = Cofre()
        if args.comando == "diagnostico":
            from .interface import diagnosticar_camera
            print(diagnosticar_camera(cofre))
            return 0
        if args.comando == "calibrar":
            print(avaliacao.resumo_calibracao(avaliacao.calibrar_com_cadastros(cofre.banco)))
            return 0
        if args.comando == "retreinar":
            print("Esta ação refaz o modelo a partir das amostras em disco e fica registrada no histórico.")
            if input("Digite SIM para confirmar: ").strip() != "SIM":
                print("Cancelado.")
                return 1
            print(f"Modelo refeito com {cofre.retreinar_modelo()} amostras.")
            return 0
        if args.comando == "trocar-ministro":
            atual = [u for u in cofre.banco.listar_usuarios() if u["nivel"] == config.NIVEL_MINISTRO]
            if atual:
                print(f"Ministro atual: {atual[0]['nome']}. Ele será substituído; a biometria dele só "
                      "será apagada depois que o novo ministro for cadastrado com sucesso.")
                if input("Digite SIM para confirmar: ").strip() != "SIM":
                    print("Cancelado.")
                    return 1
            else:
                print("Não há ministro ativo. O novo ministro será cadastrado por ação local.")
            Menu(cofre).cadastrar(local=True, substituindo=atual[0] if atual else None)
            return 0
        if args.comando == "autenticar-arquivo":
            print("AVISO: autenticação por arquivo NÃO tem prova de vida (uma foto do titular serve). "
                  "Uso apenas para demonstração e teste; o registro fica marcado no histórico.",
                  file=sys.stderr)
            res = cofre.autenticar_arquivo(args.imagem, args.compartimento, args.recorte)
            print(("PERMITIDO" if res["permitido"] else "NEGADO"),
                  "-", res.get("usuario") or "ninguém identificado", "-", res["motivo"])
            return 0 if res["permitido"] else 2
        Menu(cofre).executar()
        return 0
    except ErroCofre as e:
        print(f"Erro: {e}")
        return 1
    except EOFError:
        print("\nEntrada encerrada.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

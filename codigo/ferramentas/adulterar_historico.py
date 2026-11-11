"""Adultera DE PROPÓSITO uma linha do histórico, para demonstrar a verificação de integridade.

Só roda se a variável COFRE_DADOS apontar para uma pasta de TESTE (nunca os dados da
apresentação). Uso (PowerShell, dentro da pasta `codigo`):

    $env:COFRE_DADOS = "C:\\temp\\dados_teste"
    python ferramentas\\adulterar_historico.py editar      # muda o resultado da linha 1
    python ferramentas\\adulterar_historico.py apagar      # apaga a ÚLTIMA linha

Depois, no menu, a opção 6 (verificar integridade) deve acusar violação.
"""

import os
import sqlite3
import sys
from pathlib import Path


def main():
    pasta = os.environ.get("COFRE_DADOS")
    if not pasta:
        print("Recusado: defina COFRE_DADOS apontando para uma pasta de teste.")
        return 1
    banco = Path(pasta) / "cofre.db"
    if not banco.is_file():
        print(f"Banco não encontrado: {banco}")
        return 1
    acao = sys.argv[1] if len(sys.argv) > 1 else "editar"
    con = sqlite3.connect(str(banco))
    if acao == "editar":
        con.execute("UPDATE acessos SET resultado='PERMITIDO' WHERE id=(SELECT MIN(id) FROM acessos)")
    elif acao == "apagar":
        con.execute("DELETE FROM acessos WHERE id=(SELECT MAX(id) FROM acessos)")
    else:
        print("Use: editar | apagar")
        return 1
    con.commit()
    print(f"Histórico em {banco} adulterado ({acao}). Rode a opção 6 do menu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

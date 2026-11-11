"""Isola os testes: aponta COFRE_DADOS para uma pasta temporária ANTES de o
pacote `cofre` ser importado, para nunca tocar nos dados reais."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

if "COFRE_TESTE_DIR" not in os.environ:
    _tmp = tempfile.mkdtemp(prefix="cofre_teste_")
    os.environ["COFRE_TESTE_DIR"] = _tmp
    os.environ["COFRE_DADOS"] = _tmp
    atexit.register(shutil.rmtree, _tmp, ignore_errors=True)

PASTA_DADOS = Path(os.environ["COFRE_DADOS"])
BASE_ORL = Path(__file__).resolve().parent.parent.parent / "base_teste" / "orl"

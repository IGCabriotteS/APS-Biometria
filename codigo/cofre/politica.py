"""Política de acesso aos compartimentos do cofre (três níveis).

Regras, derivadas do enunciado:
  Nível 1 (geral)    -> apenas compartimentos de nível mínimo 1.
  Nível 2 (diretor)  -> compartimentos de nível 1 e os de nível 2 da PRÓPRIA
                        divisão. Diretor de outra divisão é negado.
  Nível 3 (ministro) -> todos os compartimentos.

É um controle de acesso em camadas, no espírito do modelo Bell-LaPadula
(clearance do sujeito x classificação do objeto), com a restrição adicional por
divisão no nível intermediário (necessidade de conhecer).
"""

from dataclasses import dataclass

from . import config


@dataclass
class Decisao:
    permitido: bool
    motivo: str


def _mesma_divisao(a, b):
    return (a or "").strip().casefold() == (b or "").strip().casefold()


def decidir(usuario, compartimento):
    """Decide se `usuario` pode abrir `compartimento` (ambos como mapeamentos)."""
    if not usuario["ativo"]:
        return Decisao(False, "usuário desativado")

    nivel = usuario["nivel"]
    exigido = compartimento["nivel_minimo"]

    if nivel == config.NIVEL_MINISTRO:
        return Decisao(True, "Nível 3: acesso total")

    if exigido == config.NIVEL_MINISTRO:
        return Decisao(False, "compartimento exclusivo do ministro (Nível 3)")

    if exigido == config.NIVEL_GERAL:
        return Decisao(True, "compartimento de permissão geral")

    # compartimento de nível 2
    if nivel < config.NIVEL_DIRETOR:
        return Decisao(False, "compartimento restrito a diretores (Nível 2)")
    if compartimento["divisao"] and not _mesma_divisao(
            usuario["divisao"], compartimento["divisao"]):
        return Decisao(False, f"compartimento da divisão '{compartimento['divisao']}', "
                              f"diferente da divisão do diretor")
    return Decisao(True, "diretor da divisão responsável")

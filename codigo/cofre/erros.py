"""Exceções específicas do sistema.

Cada falha previsível tem a sua própria classe, para que a interface possa
explicar ao usuário o que aconteceu sem mostrar uma pilha de erro.
"""


class ErroCofre(Exception):
    """Classe base de todos os erros do sistema."""


class CameraIndisponivel(ErroCofre):
    """A câmera não pôde ser aberta (ocupada, desconectada ou sem permissão)."""


class ErroCaptura(ErroCofre):
    """A câmera abriu, mas deixou de entregar quadros."""


class ImagemInvalida(ErroCofre):
    """O arquivo de imagem não existe ou não pôde ser decodificado."""


class ModeloIndisponivel(ErroCofre):
    """Não há modelo treinado, ou o arquivo do modelo foi alterado/corrompido."""


class UsuarioInvalido(ErroCofre):
    """Dados de cadastro rejeitados (nome vazio, nível inexistente, etc.)."""


class RegraDeNegocio(ErroCofre):
    """Operação proibida por uma regra do cofre (ex.: segundo ministro)."""


class SistemaBloqueado(ErroCofre):
    """O terminal está em bloqueio temporário após falhas consecutivas."""

    def __init__(self, segundos_restantes):
        super().__init__(f"Terminal bloqueado por mais {segundos_restantes} s.")
        self.segundos_restantes = segundos_restantes

"""Camada de serviço: junta banco, pipeline, modelo, política e registro.

A interface (menus e janelas) só chama métodos desta classe; assim a mesma
lógica serve ao uso interativo, à autenticação por arquivo e aos testes.
"""

import shutil
from datetime import datetime

from . import caracteristicas, config, politica
from .aquisicao import carregar_imagem, salvar_imagem
from .autenticacao import ControleBloqueio
from .banco import Banco
from .classificacao import Reconhecedor
from .erros import ModeloIndisponivel, RegraDeNegocio, UsuarioInvalido
from .pipeline import Pipeline

DESCONHECIDO = "(desconhecido)"
ORIGEM_ARQUIVO = "por arquivo, sem prova de vida"

# "Compartimento" virtual: operações administrativas (cadastrar, remover,
# relatórios) exigem o mesmo critério do Nível 3, exclusivo do ministro.
ADMINISTRACAO = {"id": None, "nome": "Administração do sistema",
                 "nivel_minimo": config.NIVEL_MINISTRO, "divisao": None}


class Cofre:
    def __init__(self, banco=None, pipeline=None):
        self.banco = banco or Banco()
        self._pipeline = pipeline
        self.bloqueio = ControleBloqueio(self.banco)
        self.reconhecedor = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            self._pipeline = Pipeline()
        return self._pipeline

    # -- modelo -----------------------------------------------------------------
    def carregar_modelo(self):
        """Carrega o modelo conferindo a impressão digital SHA-256 guardada.

        Falha FECHADA: se o banco não tiver a impressão digital, o modelo não é
        usado (aceitar "sem hash" permitiria burlar a verificação apagando-o).
        """
        if not config.ARQUIVO_MODELO.is_file():
            raise ModeloIndisponivel("Nenhum modelo treinado foi encontrado.")
        esperado = self.banco.obter_parametro("hash_modelo")
        if not esperado:
            raise ModeloIndisponivel(
                "O modelo não tem impressão digital (SHA-256) registrada no banco. "
                "Um administrador local deve executar: python -m cofre retreinar")
        self.reconhecedor = Reconhecedor.carregar(hash_esperado=esperado)
        return self.reconhecedor

    def retreinar_modelo(self):
        """Recuperação local: refaz o modelo a partir das amostras guardadas.

        É uma ação de administrador da máquina (linha de comando), pois o modelo
        adulterado impede a autenticação do ministro, e é registrada no histórico.
        """
        n = self.treinar()
        self.banco.registrar_evento("(administrador local)",
                                    f"modelo retreinado a partir de {n} amostras guardadas")
        return n

    def modelo_pronto(self):
        try:
            self.carregar_modelo()
            return True
        except ModeloIndisponivel:
            return False

    def treinar(self):
        """Reconstrói o modelo a partir das amostras dos usuários ativos."""
        vetores, rotulos = [], []
        for usuario in self.banco.listar_usuarios():
            pasta = config.PASTA_AMOSTRAS / str(usuario["id"])
            for arquivo in sorted(pasta.glob("*.png")):
                vetores.append(caracteristicas.extrair(carregar_imagem(arquivo, cinza=True)))
                rotulos.append(usuario["id"])
        if not vetores:
            raise ModeloIndisponivel("Não há amostras de usuários ativos para treinar.")
        modelo = Reconhecedor().treinar(vetores, rotulos)
        self.banco.definir_parametro("hash_modelo", modelo.salvar())
        self.reconhecedor = modelo
        return len(vetores)

    # -- usuários ---------------------------------------------------------------
    def cadastrar(self, nome, cargo, nivel, divisao, faces_normalizadas,
                  responsavel="(administrador)"):
        """Grava usuário e amostras e retreina o modelo (e registra no histórico).

        `faces_normalizadas` são os recortes 100x100 já processados. Se algo
        falhar no meio, o usuário recém-criado é desfeito para não deixar um
        cadastro sem biometria no banco.
        """
        if len(faces_normalizadas) < config.AMOSTRAS_MINIMAS:
            raise UsuarioInvalido(
                f"Amostras insuficientes: {len(faces_normalizadas)} (mínimo {config.AMOSTRAS_MINIMAS}). "
                "Um cadastro sem biometria nunca poderia ser reconhecido.")
        usuario_id = self.banco.criar_usuario(nome, cargo, nivel, divisao)
        try:
            pasta = config.PASTA_AMOSTRAS / str(usuario_id)
            for i, face in enumerate(faces_normalizadas, start=1):
                salvar_imagem(pasta / f"{i:03d}.png", face)
            self.treinar()
        except Exception:
            self.banco.desativar_usuario(usuario_id)
            shutil.rmtree(config.PASTA_AMOSTRAS / str(usuario_id), ignore_errors=True)
            raise
        self.banco.registrar_evento(
            responsavel, f"usuário '{nome.strip()}' cadastrado (nível {nivel}) com "
                         f"{len(faces_normalizadas)} amostras", usuario_id)
        return usuario_id

    def trocar_ministro(self, antigo_id, nome, cargo, faces_normalizadas,
                        responsavel="(administrador local)"):
        """Substitui o ministro de forma ATÔMICA: se o cadastro do novo falhar, o antigo
        volta ao estado anterior (ativo, com biometria e modelo), e o sistema nunca fica
        sem ministro. A biometria do antigo só é apagada depois que o novo está cadastrado."""
        antigo = self.banco.obter_usuario(antigo_id)
        self.banco.desativar_usuario(antigo_id)          # libera a vaga única do nível 3
        try:
            novo_id = self.cadastrar(nome, cargo, config.NIVEL_MINISTRO, None,
                                     faces_normalizadas, responsavel)
        except Exception:
            self.banco.reativar_usuario(antigo_id)
            self.treinar()
            raise
        shutil.rmtree(config.PASTA_AMOSTRAS / str(antigo_id), ignore_errors=True)
        self.treinar()
        self.banco.registrar_evento(responsavel, f"ministro '{antigo['nome']}' substituído por "
                                                 f"'{nome.strip()}'; biometria do anterior apagada",
                                    antigo_id)
        return novo_id

    def remover_usuario(self, usuario_id, permitir_ministro=False, responsavel="(administrador)"):
        """Desativa o usuário, apaga as amostras biométricas e retreina.

        O ministro não pode ser removido pelo menu: se o fosse, ninguém mais
        conseguiria autenticar-se como administrador. A troca de ministro é uma
        ação local (comando `trocar-ministro`) que passa permitir_ministro=True.
        O histórico de acessos é mantido (finalidade de auditoria).
        """
        usuario = self.banco.obter_usuario(usuario_id)
        if usuario is None or not usuario["ativo"]:
            return False
        if usuario["nivel"] == config.NIVEL_MINISTRO and not permitir_ministro:
            raise RegraDeNegocio(
                "O ministro não pode ser removido pelo menu. Para substituí-lo, um administrador "
                "local deve executar: python -m cofre trocar-ministro")
        self.banco.desativar_usuario(usuario_id)
        self.banco.registrar_evento(responsavel, f"usuário '{usuario['nome']}' removido; "
                                                 "amostras biométricas apagadas", usuario_id)
        shutil.rmtree(config.PASTA_AMOSTRAS / str(usuario_id), ignore_errors=True)
        try:
            self.treinar()
        except ModeloIndisponivel:  # era o último usuário
            config.ARQUIVO_MODELO.unlink(missing_ok=True)
            self.banco.definir_parametro("hash_modelo", "")
            self.reconhecedor = None
        return True

    # -- decisão e registro ------------------------------------------------------
    def resolver_compartimento(self, referencia):
        """Aceita o id de um compartimento ou o próprio registro (ou ADMINISTRACAO)."""
        if isinstance(referencia, int):
            registro = self.banco.obter_compartimento(referencia)
            if registro is None:
                raise UsuarioInvalido(f"Compartimento {referencia} não existe.")
            return registro
        return referencia

    def concluir_identificacao(self, usuario_id, compartimento, distancia, origem=None):
        """Aplica a política ao usuário identificado e registra o resultado.

        O bloqueio por falhas protege o RECONHECIMENTO contra tentativas em série
        (rosto desconhecido, falha na prova de vida). Quem foi reconhecido mas não
        tem permissão para aquele compartimento é negado e registrado, porém não
        é bloqueado: errar de compartimento não é força bruta contra a biometria.
        """
        usuario = self.banco.obter_usuario(usuario_id)
        compartimento = self.resolver_compartimento(compartimento)
        decisao = politica.decidir(usuario, compartimento)
        resultado = "PERMITIDO" if decisao.permitido else "NEGADO"
        motivo = decisao.motivo + (f" [{origem}]" if origem else "")
        self.banco.registrar_acesso(usuario["id"], usuario["nome"], compartimento["nome"],
                                    resultado, motivo, distancia)
        self.bloqueio.registrar_sucesso()
        return decisao, usuario, False

    def registrar_falha_de_identificacao(self, compartimento, motivo, quadro=None,
                                         distancia=None, usuario_id=None, origem=None):
        """Registra tentativa negada e guarda a foto como evidência.

        `usuario_id` é preenchido quando a pessoa chegou a ser identificada
        mas falhou depois (ex.: prova de vida); caso contrário o registro
        sai como "(desconhecido)".
        """
        compartimento = self.resolver_compartimento(compartimento)
        usuario = self.banco.obter_usuario(usuario_id) if usuario_id else None
        if origem:
            motivo = f"{motivo} [{origem}]"
        self.banco.registrar_acesso(usuario["id"] if usuario else None,
                                    usuario["nome"] if usuario else DESCONHECIDO,
                                    compartimento["nome"], "NEGADO", motivo, distancia)
        if quadro is not None:
            nome = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
            salvar_imagem(config.PASTA_TENTATIVAS / nome, quadro)
        return self.bloqueio.registrar_falha()

    def autenticar_arquivo(self, caminho, compartimento_id, so_recorte=False):
        """Autentica a partir de um arquivo de imagem (scanner, foto).

        ATENÇÃO: não há prova de vida em arquivo (uma foto do titular serve). É
        um caminho de demonstração e de teste, e os registros que ele gera levam
        a marca "por arquivo, sem prova de vida" no motivo. Em produção, deve ser
        desativado ou restrito ao administrador. Devolve um dicionário com o veredito.
        """
        self.bloqueio.exigir_liberado()
        if self.reconhecedor is None:
            self.carregar_modelo()
        imagem = carregar_imagem(caminho)
        # mesmo caminho do cadastro por câmera (com alinhamento pelos olhos)
        r = (self.pipeline.processar_recorte(imagem) if so_recorte
             else self.pipeline.processar(imagem, com_olhos=True))
        if not r.tem_rosto:
            self.registrar_falha_de_identificacao(compartimento_id, "nenhum rosto detectado", origem=ORIGEM_ARQUIVO)
            return {"permitido": False, "motivo": "nenhum rosto detectado", "usuario": None}
        if r.intruso:
            self.registrar_falha_de_identificacao(compartimento_id, "mais de um rosto na imagem", origem=ORIGEM_ARQUIVO)
            return {"permitido": False, "motivo": "mais de um rosto na imagem", "usuario": None}
        previsao = self.reconhecedor.prever(r.vetor)
        if not (previsao.aceito and previsao.margem >= config.MARGEM_MINIMA):
            self.registrar_falha_de_identificacao(
                compartimento_id, "rosto não reconhecido", r.quadro, previsao.distancia,
                origem=ORIGEM_ARQUIVO)
            return {"permitido": False, "motivo": "rosto não reconhecido",
                    "usuario": None, "distancia": previsao.distancia}
        decisao, usuario, _ = self.concluir_identificacao(
            previsao.usuario_id, compartimento_id, previsao.distancia,
            origem=ORIGEM_ARQUIVO)
        return {"permitido": decisao.permitido, "motivo": decisao.motivo,
                "usuario": usuario["nome"], "distancia": previsao.distancia}

"""Persistência em SQLite: usuários, compartimentos do cofre e registro de acessos.

O registro de acessos é encadeado por hash (cada linha inclui o SHA-256 da
anterior), como em uma cadeia de blocos simplificada. Se alguém apagar ou
editar uma linha do histórico, a verificação de integridade acusa a quebra.
"""

import hashlib
import sqlite3
from datetime import datetime

from . import config
from .erros import RegraDeNegocio, UsuarioInvalido

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT    NOT NULL,
    cargo     TEXT    NOT NULL DEFAULT '',
    nivel     INTEGER NOT NULL CHECK (nivel IN (1, 2, 3)),
    divisao   TEXT,
    ativo     INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS compartimentos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL UNIQUE,
    nivel_minimo  INTEGER NOT NULL CHECK (nivel_minimo IN (1, 2, 3)),
    divisao       TEXT
);
CREATE TABLE IF NOT EXISTS acessos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora       TEXT    NOT NULL,
    usuario_id      INTEGER,
    nome            TEXT    NOT NULL,
    compartimento   TEXT    NOT NULL,
    resultado       TEXT    NOT NULL,
    motivo          TEXT    NOT NULL,
    distancia       REAL,
    hash_anterior   TEXT    NOT NULL,
    hash            TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS parametros (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

# Compartimentos padrão do cofre; a divisão só importa no nível 2.
COMPARTIMENTOS_PADRAO = [
    ("Arquivo Geral de Relatórios Ambientais", 1, None),
    ("Laboratório de Toxinas Agrícolas", 2, "Agrotóxicos e Biocidas"),
    ("Laboratório de Resíduos Perigosos", 2, "Resíduos Perigosos"),
    ("Câmara Central de Toxinas de Alto Risco", 3, None),
]

HASH_INICIAL = "0" * 64


def agora():
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Banco:
    def __init__(self, caminho=None):
        caminho = caminho or config.ARQUIVO_BANCO
        config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(caminho))
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_ESQUEMA)
        self._semear_compartimentos()

    def fechar(self):
        self._con.close()

    def _semear_compartimentos(self):
        if self._con.execute("SELECT COUNT(*) FROM compartimentos").fetchone()[0] == 0:
            self._con.executemany(
                "INSERT INTO compartimentos (nome, nivel_minimo, divisao) VALUES (?,?,?)",
                COMPARTIMENTOS_PADRAO)
            self._con.commit()

    # -- usuários --------------------------------------------------------------
    def validar_novo_usuario(self, nome, cargo, nivel, divisao=None):
        """Aplica as regras de cadastro sem gravar; devolve os dados limpos.

        Permite recusar um cadastro inválido ANTES de pedir ao usuário que
        posicione o rosto diante da câmera para a captura das amostras.
        """
        nome = (nome or "").strip()
        cargo = (cargo or "").strip()
        divisao = (divisao or "").strip() or None
        if len(nome) < 3:
            raise UsuarioInvalido("O nome deve ter pelo menos 3 caracteres.")
        if nivel not in config.NOMES_NIVEIS:
            raise UsuarioInvalido("Nível inexistente: use 1, 2 ou 3.")
        if nivel == config.NIVEL_DIRETOR and not divisao:
            raise UsuarioInvalido("O diretor precisa estar vinculado a uma divisão.")
        if nivel != config.NIVEL_DIRETOR:
            divisao = None
        if self._con.execute(
                "SELECT 1 FROM usuarios WHERE ativo=1 AND lower(nome)=lower(?)",
                (nome,)).fetchone():
            raise UsuarioInvalido(f"Já existe um usuário ativo chamado '{nome}'.")
        if nivel == config.NIVEL_MINISTRO and self.contar_ativos(config.NIVEL_MINISTRO) >= 1:
            raise RegraDeNegocio(
                "O Nível 3 é exclusivo do ministro: já existe um ministro ativo. "
                "Desative-o antes de cadastrar outro.")
        return nome, cargo, nivel, divisao

    def criar_usuario(self, nome, cargo, nivel, divisao=None):
        nome, cargo, nivel, divisao = self.validar_novo_usuario(nome, cargo, nivel, divisao)
        cur = self._con.execute(
            "INSERT INTO usuarios (nome, cargo, nivel, divisao, criado_em) VALUES (?,?,?,?,?)",
            (nome, cargo, nivel, divisao, agora()))
        self._con.commit()
        return cur.lastrowid

    def obter_usuario(self, usuario_id):
        return self._con.execute(
            "SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()

    def listar_usuarios(self, apenas_ativos=True):
        sql = "SELECT * FROM usuarios"
        if apenas_ativos:
            sql += " WHERE ativo=1"
        return self._con.execute(sql + " ORDER BY nivel DESC, nome").fetchall()

    def contar_ativos(self, nivel=None):
        if nivel is None:
            return self._con.execute(
                "SELECT COUNT(*) FROM usuarios WHERE ativo=1").fetchone()[0]
        return self._con.execute(
            "SELECT COUNT(*) FROM usuarios WHERE ativo=1 AND nivel=?",
            (nivel,)).fetchone()[0]

    def reativar_usuario(self, usuario_id):
        """Desfaz uma desativação (usada para reverter uma troca de ministro que falhou)."""
        cur = self._con.execute("UPDATE usuarios SET ativo=1 WHERE id=?", (usuario_id,))
        self._con.commit()
        return cur.rowcount > 0

    def desativar_usuario(self, usuario_id):
        cur = self._con.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (usuario_id,))
        self._con.commit()
        return cur.rowcount > 0

    # -- compartimentos --------------------------------------------------------
    def listar_compartimentos(self):
        return self._con.execute(
            "SELECT * FROM compartimentos ORDER BY nivel_minimo, nome").fetchall()

    def obter_compartimento(self, compartimento_id):
        return self._con.execute(
            "SELECT * FROM compartimentos WHERE id=?", (compartimento_id,)).fetchone()

    def listar_divisoes(self):
        linhas = self._con.execute(
            "SELECT DISTINCT divisao FROM compartimentos "
            "WHERE divisao IS NOT NULL ORDER BY divisao").fetchall()
        return [l[0] for l in linhas]

    # -- parâmetros (modelo, bloqueio) ------------------------------------------
    def obter_parametro(self, chave, padrao=None):
        linha = self._con.execute(
            "SELECT valor FROM parametros WHERE chave=?", (chave,)).fetchone()
        return linha[0] if linha else padrao

    def definir_parametro(self, chave, valor):
        self._con.execute(
            "INSERT INTO parametros (chave, valor) VALUES (?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))
        self._con.commit()

    # -- registro de acessos com hash encadeado ---------------------------------
    @staticmethod
    def _calcular_hash(anterior, data_hora, usuario_id, nome, comp, resultado, motivo, dist):
        texto = "|".join(str(v) for v in
                         (anterior, data_hora, usuario_id, nome, comp, resultado, motivo, dist))
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()

    def registrar_acesso(self, usuario_id, nome, compartimento, resultado, motivo,
                         distancia=None):
        ultimo = self._con.execute(
            "SELECT hash FROM acessos ORDER BY id DESC LIMIT 1").fetchone()
        anterior = ultimo[0] if ultimo else HASH_INICIAL
        data_hora = agora()
        h = self._calcular_hash(anterior, data_hora, usuario_id, nome, compartimento,
                                resultado, motivo, distancia)
        # Linha + âncora na MESMA transação: uma queda no meio não deixa a âncora
        # desencontrada (o que viraria falso alarme).
        # Âncora: total de linhas e último hash. Detecta a remoção das ÚLTIMAS
        # linhas, que o encadeamento sozinho não vê (a cadeia restante segue válida).
        # Limite: a âncora mora no mesmo banco; quem edita o banco inteiro refaz as duas.
        with self._con:
            self._con.execute(
                "INSERT INTO acessos (data_hora, usuario_id, nome, compartimento, resultado, "
                "motivo, distancia, hash_anterior, hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (data_hora, usuario_id, nome, compartimento, resultado, motivo,
                 distancia, anterior, h))
            total = self._con.execute("SELECT COUNT(*) FROM acessos").fetchone()[0]
            for chave, valor in (("log_total", total), ("log_ultimo_hash", h)):
                self._con.execute(
                    "INSERT INTO parametros (chave, valor) VALUES (?,?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))

    def registrar_evento(self, responsavel, descricao, usuario_id=None):
        """Registra uma operação administrativa (cadastro, remoção, retreino)."""
        self.registrar_acesso(usuario_id, responsavel, "Administração do sistema",
                              "ADMIN", descricao, None)

    def listar_acessos(self, desde=None):
        if desde:
            return self._con.execute(
                "SELECT * FROM acessos WHERE data_hora >= ? ORDER BY id", (desde,)).fetchall()
        return self._con.execute("SELECT * FROM acessos ORDER BY id").fetchall()

    def verificar_integridade(self):
        """Percorre o histórico; devolve (ok, id_da_primeira_linha_suspeita)."""
        anterior = HASH_INICIAL
        ultimo_id, contagem = 0, 0
        for linha in self._con.execute("SELECT * FROM acessos ORDER BY id"):
            esperado = self._calcular_hash(
                anterior, linha["data_hora"], linha["usuario_id"], linha["nome"],
                linha["compartimento"], linha["resultado"], linha["motivo"],
                linha["distancia"])
            if linha["hash_anterior"] != anterior or linha["hash"] != esperado:
                return False, linha["id"]
            anterior = linha["hash"]
            ultimo_id, contagem = linha["id"], contagem + 1
        # confere a âncora (truncagem do fim do histórico)
        total = self.obter_parametro("log_total")
        ultimo = self.obter_parametro("log_ultimo_hash")
        if total is None or ultimo is None:
            # Falha FECHADA: com linhas no histórico, a âncora tem de existir; sem ela
            # (apagada junto com o fim do histórico) não dá para afirmar que está íntegro.
            if contagem > 0:
                return False, 0
        elif int(total) != contagem or ultimo != anterior:
            return False, ultimo_id + 1            # linha(s) ausente(s) no fim
        return True, None

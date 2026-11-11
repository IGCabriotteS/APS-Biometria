"""Interface com o usuário: janelas em tempo real (OpenCV) e menus de texto.

Os textos desenhados nas janelas não têm acentos porque as fontes do OpenCV
só cobrem ASCII; os menus do terminal usam o português completo.
"""

import time

import cv2
import numpy as np

from . import autenticacao as aut
from . import config, relatorios
from .aquisicao import Camera
from .erros import (CameraIndisponivel, ErroCaptura, ErroCofre, ModeloIndisponivel,
                    SistemaBloqueado, UsuarioInvalido)
from .servico import ADMINISTRACAO, Cofre

VERDE, VERMELHO, AMARELO, AZUL, BRANCO = (60, 200, 60), (50, 50, 230), (0, 200, 255), (230, 160, 40), (255, 255, 255)
JANELA = "Cofre biometrico - ESC cancela"
_DURACAO_ADMIN = 300  # segundos de validade da sessão de administrador


# --------------------------------------------------------------------------
# desenho
# --------------------------------------------------------------------------
def _texto(img, texto, pos, cor=BRANCO, escala=0.6, espessura=2):
    cv2.putText(img, texto, pos, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0),
                espessura + 2, cv2.LINE_AA)
    cv2.putText(img, texto, pos, cv2.FONT_HERSHEY_SIMPLEX, escala, cor, espessura, cv2.LINE_AA)


def _sem_acentos(texto):
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                           "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
    return texto.translate(tabela)


def _desenhar_estado(quadro, r, estado, restante=None):
    saida = quadro.copy()
    cor = {aut.PROCURANDO: AMARELO, aut.VALIDANDO: AZUL, aut.PROVA_DE_VIDA: AZUL,
           aut.IDENTIFICADO: VERDE, aut.FALHA: VERMELHO}[estado.fase]
    for caixa in r.caixas:
        x, y, w, h = caixa
        espessura = 3 if caixa == r.caixa else 1
        cv2.rectangle(saida, (x, y), (x + w, y + h), cor if caixa == r.caixa else VERMELHO,
                      espessura)
    barra = np.zeros((70, saida.shape[1], 3), np.uint8)
    _texto(barra, _sem_acentos(estado.mensagem), (10, 28), cor, 0.7)
    info = []
    if estado.distancia is not None:
        info.append(f"distancia {estado.distancia:.3f} (limiar {config.LIMIAR_DISTANCIA})")
    if restante is not None:
        info.append(f"tempo {restante:0.0f}s")
    _texto(barra, "  |  ".join(info), (10, 56), BRANCO, 0.5, 1)
    return np.vstack([saida, barra])


def _mostrar_resultado(quadro, permitido, linhas, segundos=2.5):
    tela = quadro.copy()
    cor = VERDE if permitido else VERMELHO
    cv2.rectangle(tela, (0, 0), (tela.shape[1] - 1, tela.shape[0] - 1), cor, 14)
    _texto(tela, "ACESSO PERMITIDO" if permitido else "ACESSO NEGADO", (30, 70), cor, 1.2, 3)
    for i, linha in enumerate(linhas):
        _texto(tela, _sem_acentos(linha), (30, 120 + 34 * i), BRANCO, 0.65)
    cv2.imshow(JANELA, tela)
    cv2.waitKey(int(segundos * 1000))


def montar_painel(r, previsao=None):
    """Imagem com as cinco fases lado a lado (usada na apresentação)."""
    lado = 220

    def bloco(img, titulo):
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        img = cv2.resize(img, (lado, lado), interpolation=cv2.INTER_NEAREST)
        _texto(img, titulo, (6, 20), AMARELO, 0.5, 1)
        return img

    vazio = np.zeros((lado, lado, 3), np.uint8)
    original = r.quadro if r.quadro.ndim == 3 else cv2.cvtColor(r.quadro, cv2.COLOR_GRAY2BGR)
    original = original.copy()
    if r.caixa:
        x, y, w, h = r.caixa
        cv2.rectangle(original, (x, y), (x + w, y + h), VERDE, 2)
    t1 = bloco(original, "1 Aquisicao")
    t2 = bloco(r.recorte, "2 Pre-proc.") if r.recorte is not None else bloco(vazio, "2 Pre-proc.")
    t3 = bloco(r.normalizada, "3 Segmentacao") if r.normalizada is not None else bloco(vazio, "3 Segmentacao")
    t4 = bloco(r.lbp, "4 LBP") if r.lbp is not None else bloco(vazio, "4 LBP")

    t5 = np.zeros((lado, lado, 3), np.uint8)
    _texto(t5, "5 Classificacao", (6, 20), AMARELO, 0.5, 1)
    if previsao is not None:
        cor = VERDE if previsao.aceito else VERMELHO
        _texto(t5, f"dist {previsao.distancia:.3f}", (10, 70), BRANCO, 0.6)
        _texto(t5, f"limiar {config.LIMIAR_DISTANCIA}", (10, 100), BRANCO, 0.6)
        _texto(t5, "RECONHECIDO" if previsao.aceito else "DESCONHECIDO", (10, 150), cor, 0.7)
    elif r.vetor is not None:
        pontos = np.clip(r.vetor[:lado] / max(r.vetor[:lado].max(), 1e-9), 0, 1)
        for i, v in enumerate(pontos):
            cv2.line(t5, (i, lado - 1), (i, lado - 1 - int(v * 150)), AZUL, 1)
    return np.hstack([t1, t2, t3, t4, t5])


# --------------------------------------------------------------------------
# operações com câmera
# --------------------------------------------------------------------------
def _janela_aberta():
    try:
        return cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


def capturar_amostras(cofre, quantidade=None):
    """Captura rostos de qualidade para o cadastro. Devolve a lista de faces
    normalizadas, ou None se o usuário cancelar."""
    quantidade = quantidade or config.AMOSTRAS_POR_CADASTRO
    faces, ultimo, inicio = [], 0.0, time.monotonic()
    dicas = ["Olhe de frente", "Vire levemente para a esquerda", "Vire levemente para a direita",
             "Incline a cabeca um pouco", "Sorria", "Expressao neutra"]
    with Camera() as camera:
        while len(faces) < quantidade:
            if time.monotonic() - inicio > 120:
                raise ErroCofre("Tempo esgotado na captura. Tente de novo em local mais iluminado.")
            quadro = camera.ler()
            r = cofre.pipeline.processar(quadro)
            estado = "Posicione o rosto na camera"
            cor = AMARELO
            if r.tem_rosto and r.intruso:
                estado = "Apenas uma pessoa no cadastro"
            elif r.tem_rosto and not r.qualidade_ok:
                estado = "Qualidade ruim: " + ", ".join(r.motivos)
            elif r.tem_rosto:
                cor = VERDE
                estado = dicas[(len(faces) * len(dicas)) // quantidade]
                if time.monotonic() - ultimo >= config.INTERVALO_ENTRE_AMOSTRAS:
                    faces.append(r.normalizada)
                    ultimo = time.monotonic()
            tela = quadro.copy()
            if r.caixa:
                x, y, w, h = r.caixa
                cv2.rectangle(tela, (x, y), (x + w, y + h), cor, 3)
            _texto(tela, f"Amostras {len(faces)}/{quantidade}", (10, 28), BRANCO, 0.8)
            _texto(tela, estado, (10, 460), cor, 0.7)
            cv2.imshow(JANELA, tela)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == 27 or not _janela_aberta():
                cv2.destroyAllWindows()
                return None
    cv2.destroyAllWindows()
    return faces


def autenticar_ao_vivo(cofre, compartimento):
    """Autentica uma pessoa pela câmera. Devolve (permitido, usuario, motivo).

    `usuario` é None quando a identidade não foi confirmada.
    """
    cofre.bloqueio.exigir_liberado()
    if cofre.reconhecedor is None:
        cofre.carregar_modelo()
    compartimento = cofre.resolver_compartimento(compartimento)
    sessao = aut.SessaoAutenticacao(cofre.reconhecedor)
    inicio = time.monotonic()
    try:
        with Camera() as camera:
            while True:
                quadro = camera.ler()
                r = cofre.pipeline.processar(quadro)
                estado = sessao.processar(r)
                restante = max(0, config.TEMPO_MAX_AUTENTICACAO - (time.monotonic() - inicio))
                cv2.imshow(JANELA, _desenhar_estado(quadro, r, estado, restante))
                tecla = cv2.waitKey(1) & 0xFF
                if tecla == 27 or not _janela_aberta():
                    return False, None, "cancelado pelo usuário"
                if estado.finalizado:
                    break
            if estado.fase == aut.FALHA:
                bloqueou = cofre.registrar_falha_de_identificacao(
                    compartimento, estado.motivo_falha, quadro, estado.distancia,
                    estado.usuario_id)
                _mostrar_resultado(quadro, False, [estado.motivo_falha] +
                                   (["Terminal bloqueado por 60 s"] if bloqueou else []))
                return False, None, estado.motivo_falha
            decisao, usuario, bloqueou = cofre.concluir_identificacao(
                estado.usuario_id, compartimento, estado.distancia)
            linhas = [usuario["nome"], config.NOMES_NIVEIS[usuario["nivel"]],
                      compartimento["nome"], decisao.motivo]
            if bloqueou:
                linhas.append("Terminal bloqueado por 60 s")
            _mostrar_resultado(quadro, decisao.permitido, linhas)
            return decisao.permitido, usuario, decisao.motivo
    finally:
        cv2.destroyAllWindows()


def demonstrar_fases(cofre):
    """Mostra ao vivo as cinco fases; se houver modelo, mostra também o veredito."""
    previsor = None
    try:
        previsor = cofre.carregar_modelo()
    except ModeloIndisponivel:
        pass
    try:
        with Camera() as camera:
            while True:
                r = cofre.pipeline.processar(camera.ler())
                previsao = previsor.prever(r.vetor) if (previsor and r.vetor is not None) else None
                painel = montar_painel(r, previsao)
                cv2.imshow(JANELA, painel)
                if cv2.waitKey(1) & 0xFF == 27 or not _janela_aberta():
                    break
    finally:
        cv2.destroyAllWindows()


def diagnosticar_camera(cofre, segundos=12):
    """Mede, durante alguns segundos, a detecção de rosto e olhos e quantas
    piscadas o desafio reconhece. Não grava nenhuma imagem."""
    from .prova_vida import DesafioPiscada
    desafio = DesafioPiscada()
    n = com_rosto = qualidade = dois_olhos = piscadas = 0
    tempos = []
    fim = time.monotonic() + segundos
    try:
        with Camera() as camera:
            while time.monotonic() < fim:
                quadro = camera.ler()
                t0 = time.perf_counter()
                r = cofre.pipeline.processar(quadro)
                tempos.append(time.perf_counter() - t0)
                n += 1
                if r.tem_rosto:
                    com_rosto += 1
                    qualidade += int(r.qualidade_ok)
                    dois_olhos += int(r.olhos >= 2)
                    desafio.registrar(r.olhos)
                    if desafio.concluido:
                        piscadas += 1
                        desafio.reiniciar()
                else:
                    desafio.registrar(None)
                tela = quadro.copy()
                if r.caixa:
                    x, y, w, h = r.caixa
                    cv2.rectangle(tela, (x, y), (x + w, y + h), VERDE, 2)
                _texto(tela, "Olhe para a camera e PISQUE varias vezes", (10, 28), AMARELO, 0.7)
                _texto(tela, f"olhos detectados: {r.olhos}   piscadas: {piscadas}   "
                             f"restam {max(0, fim - time.monotonic()):.0f}s", (10, 460), BRANCO, 0.6)
                cv2.imshow(JANELA, tela)
                if cv2.waitKey(1) & 0xFF == 27 or not _janela_aberta():
                    break
    finally:
        cv2.destroyAllWindows()
    if n == 0:
        return "Nenhum quadro foi processado."
    pct = lambda v: 100.0 * v / n
    return "\n".join([
        f"Quadros processados: {n}  ({1.0 / np.mean(tempos):.0f} quadros/s de processamento)",
        f"Rosto detectado:       {pct(com_rosto):5.1f}% dos quadros",
        f"Qualidade aprovada:    {pct(qualidade):5.1f}% dos quadros",
        f"Dois olhos abertos:    {pct(dois_olhos):5.1f}% dos quadros",
        f"Piscadas reconhecidas: {piscadas}",
    ])


# --------------------------------------------------------------------------
# menus
# --------------------------------------------------------------------------
def _perguntar(texto, padrao=None):
    resposta = input(texto).strip()
    return resposta or padrao


def _escolher_nivel():
    print("\nNíveis de segurança:")
    for n, nome in config.NOMES_NIVEIS.items():
        print(f"  {n} - {nome}")
    while True:
        valor = _perguntar("Nível (1-3): ")
        if valor in ("1", "2", "3"):
            return int(valor)
        print("Digite 1, 2 ou 3.")


def _escolher_divisao(cofre):
    divisoes = cofre.banco.listar_divisoes()
    print("\nDivisões:")
    for i, d in enumerate(divisoes, start=1):
        print(f"  {i} - {d}")
    while True:
        valor = _perguntar("Divisão: ")
        if valor and valor.isdigit() and 1 <= int(valor) <= len(divisoes):
            return divisoes[int(valor) - 1]
        print("Escolha o número de uma divisão da lista.")


def _escolher_compartimento(cofre):
    compartimentos = cofre.banco.listar_compartimentos()
    print("\nCompartimentos do cofre:")
    for c in compartimentos:
        extra = f" - divisão {c['divisao']}" if c["divisao"] else ""
        print(f"  {c['id']} - {c['nome']} (nível mínimo {c['nivel_minimo']}{extra})")
    ids = {c["id"] for c in compartimentos}
    while True:
        valor = _perguntar("Compartimento que deseja abrir: ")
        if valor and valor.isdigit() and int(valor) in ids:
            return int(valor)
        print("Número inválido.")


class Menu:
    def __init__(self, cofre):
        self.cofre = cofre
        self._admin_ate = 0.0
        self._admin_nome = "(administrador)"

    # -- administração protegida pelo ministro -----------------------------------
    def _exigir_ministro(self):
        """True se o ministro estiver autenticado (sessão de 5 min)."""
        if time.monotonic() < self._admin_ate:
            return True
        print("\nEsta operação exige a autenticação facial do ministro (Nível 3).")
        permitido, usuario, motivo = autenticar_ao_vivo(self.cofre, ADMINISTRACAO)
        if permitido:
            self._admin_ate = time.monotonic() + _DURACAO_ADMIN
            self._admin_nome = usuario["nome"]
            return True
        print(f"Operação negada: {motivo}.")
        return False

    # -- opções ---------------------------------------------------------------------
    def cadastrar(self, local=False, substituindo=None):
        """Cadastra um usuário pela câmera.

        Regras de quem pode cadastrar (todas verificadas no código):
          * banco vazio: o primeiro cadastro é o do ministro, sem autenticação (não há
            ninguém para autenticar);
          * há ministro: ele precisa se autenticar (sessão de 5 min);
          * há usuários mas NÃO há ministro: o menu recusa. Cadastrar o ministro nesse
            estado, sem autenticação, deixaria qualquer um com acesso ao menu virar
            ministro; só o administrador da máquina, pelo comando local
            `trocar-ministro` (local=True), pode fazê-lo;
          * `substituindo`: troca atômica do ministro (o antigo volta se o novo falhar).
        """
        banco = self.cofre.banco
        sem_ministro = banco.contar_ativos(config.NIVEL_MINISTRO) == 0
        primeiro = sem_ministro and banco.contar_ativos() == 0
        como_ministro = False
        if substituindo is not None or (sem_ministro and local):
            como_ministro = True
        elif primeiro:
            como_ministro = True
            print("\nNenhum usuário cadastrado. O primeiro cadastro é o do ministro (Nível 3).")
        elif sem_ministro:
            print("Não há ministro ativo. Para recuperar a administração, um administrador da "
                  "máquina deve executar: python -m cofre trocar-ministro")
            return
        elif not self._exigir_ministro():
            return
        nome = _perguntar("Nome completo: ")
        cargo = _perguntar("Cargo: ", "")
        nivel = config.NIVEL_MINISTRO if como_ministro else _escolher_nivel()
        divisao = _escolher_divisao(self.cofre) if nivel == config.NIVEL_DIRETOR else None
        if substituindo is None:
            banco.validar_novo_usuario(nome, cargo, nivel, divisao)  # falha cedo
        elif len((nome or "").strip()) < 3:
            raise UsuarioInvalido("O nome deve ter pelo menos 3 caracteres.")
        print("\nA janela da câmera vai abrir. Mantenha apenas o seu rosto no quadro e "
              "siga as instruções. ESC cancela.")
        faces = capturar_amostras(self.cofre)
        if faces is None:
            print("Cadastro cancelado. Nada foi alterado.")
            return
        if substituindo is not None:
            uid = self.cofre.trocar_ministro(substituindo["id"], nome, cargo, faces)
            print(f"Ministro substituído (novo id {uid}). A biometria do anterior foi apagada.")
            return
        if primeiro:
            responsavel = "(primeiro cadastro do ministro)"
        elif local:
            responsavel = "(administrador local)"
        else:
            responsavel = self._admin_nome
        uid = self.cofre.cadastrar(nome, cargo, nivel, divisao, faces, responsavel)
        print(f"Usuário cadastrado (id {uid}) com {len(faces)} amostras. Modelo atualizado.")

    def autenticar(self):
        if self.cofre.banco.contar_ativos() == 0:
            print("Ainda não há usuários cadastrados.")
            return
        # Se o modelo estiver ausente ou adulterado, carregar_modelo explica o motivo
        # (a mensagem chega ao usuário pelo tratamento de ModeloIndisponivel do menu).
        self.cofre.carregar_modelo()
        comp = _escolher_compartimento(self.cofre)
        permitido, usuario, motivo = autenticar_ao_vivo(self.cofre, comp)
        print(("ACESSO PERMITIDO" if permitido else "ACESSO NEGADO") +
              (f" - {usuario['nome']}" if usuario else "") + f" ({motivo})")

    def listar(self):
        usuarios = self.cofre.banco.listar_usuarios()
        if not usuarios:
            print("Nenhum usuário cadastrado.")
        for u in usuarios:
            div = f" | divisão {u['divisao']}" if u["divisao"] else ""
            print(f"  [{u['id']}] {u['nome']} - {u['cargo']} | {config.NOMES_NIVEIS[u['nivel']]}{div}")

    def remover(self):
        if not self._exigir_ministro():
            return
        self.listar()
        valor = _perguntar("Id do usuário a remover: ")
        if not (valor and valor.isdigit()):
            print("Id inválido.")
            return
        usuario = self.cofre.banco.obter_usuario(int(valor))
        if usuario is None or not usuario["ativo"]:
            print("Usuário não encontrado.")
            return
        if _perguntar(f"Remover '{usuario['nome']}' e apagar a biometria? (s/N): ", "n").lower() == "s":
            self.cofre.remover_usuario(usuario["id"], responsavel=self._admin_nome)
            print("Usuário removido (amostras biométricas apagadas) e modelo atualizado. "
                  "O histórico de acessos é mantido.")

    def relatorio(self):
        if not self._exigir_ministro():
            return
        _, resumo = relatorios.relatorio_acessos(self.cofre.banco)
        print("\n" + resumo)
        print("Lista de usuários:", relatorios.relatorio_usuarios(self.cofre.banco))

    def integridade(self):
        ok, linha = self.cofre.banco.verificar_integridade()
        if ok:
            print("Histórico ÍNTEGRO.")
        elif linha == 0:
            print("HISTÓRICO SUSPEITO: a âncora (total de linhas e último hash) está ausente.")
        else:
            print(f"HISTÓRICO VIOLADO a partir da linha {linha}!")

    def executar(self):
        opcoes = {
            "1": ("Cadastrar usuário", self.cadastrar),
            "2": ("Autenticar e abrir compartimento", self.autenticar),
            "3": ("Listar usuários", self.listar),
            "4": ("Remover usuário", self.remover),
            "5": ("Relatórios de acesso", self.relatorio),
            "6": ("Verificar integridade do histórico", self.integridade),
            "7": ("Demonstração das 5 fases (ao vivo)", lambda: demonstrar_fases(self.cofre)),
            "8": ("Diagnóstico da câmera e da prova de vida",
                  lambda: print(diagnosticar_camera(self.cofre))),
            "0": ("Sair", None),
        }
        while True:
            print("\n=== COFRE DE SEGURANÇA MÁXIMA - Ministério do Meio Ambiente ===")
            for chave, (titulo, _) in opcoes.items():
                print(f"  {chave} - {titulo}")
            try:
                escolha = input("Opção: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if escolha == "0":
                return
            if escolha not in opcoes:
                print("Opção inválida.")
                continue
            try:
                opcoes[escolha][1]()
            except SistemaBloqueado as e:
                print(f"Terminal bloqueado por falhas consecutivas. Aguarde {e.segundos_restantes} s.")
            except CameraIndisponivel as e:
                print(f"Câmera indisponível: {e}")
            except ErroCaptura as e:
                print(f"Falha na captura: {e}")
            except ModeloIndisponivel as e:
                print(f"Modelo: {e}")
            except ErroCofre as e:
                print(f"Erro: {e}")
            except KeyboardInterrupt:
                cv2.destroyAllWindows()
                print("\nOperação interrompida.")

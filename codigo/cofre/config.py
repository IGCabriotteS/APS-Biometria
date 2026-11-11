"""Parâmetros centrais do sistema.

Todos os valores que influenciam o desempenho ou a segurança ficam aqui, para
que possam ser ajustados (e justificados no relatório) em um único lugar.
A pasta de dados pode ser trocada pela variável de ambiente COFRE_DADOS, o que
é usado pelos testes automatizados para não tocar nos dados reais.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = Path(os.environ.get("COFRE_DADOS", RAIZ / "dados"))
PASTA_AMOSTRAS = PASTA_DADOS / "amostras"
PASTA_RELATORIOS = PASTA_DADOS / "relatorios"
PASTA_TENTATIVAS = PASTA_DADOS / "tentativas_negadas"
ARQUIVO_BANCO = PASTA_DADOS / "cofre.db"
ARQUIVO_MODELO = PASTA_DADOS / "modelo.npz"

# --- Níveis de segurança (conforme o enunciado) -----------------------------
NIVEL_GERAL = 1       # permissão geral
NIVEL_DIRETOR = 2     # diretores de divisões específicas
NIVEL_MINISTRO = 3    # exclusivo do ministro do Meio Ambiente
NOMES_NIVEIS = {
    NIVEL_GERAL: "Nível 1 - Permissão geral",
    NIVEL_DIRETOR: "Nível 2 - Diretor de divisão",
    NIVEL_MINISTRO: "Nível 3 - Ministro do Meio Ambiente",
}

# --- Aquisição ---------------------------------------------------------------
INDICE_CAMERA = 0
LARGURA_CAPTURA = 640
ALTURA_CAPTURA = 480

# --- Segmentação -------------------------------------------------------------
ESCALA_DETECCAO = 1.1        # passo da pirâmide de escalas do detector Haar
VIZINHOS_DETECCAO = 5        # detecções vizinhas exigidas (reduz falsos positivos)
TAMANHO_MIN_FACE = 90        # lado mínimo (px) do rosto no quadro original
MARGEM_RECORTE = 0.15        # folga ao redor da caixa do rosto (fração do lado)
FRACAO_MIN_SEGUNDA_FACE = 0.5  # outro rosto com >= 50% da área do maior é "intruso"
ANGULO_MAX_ALINHAMENTO = 25.0  # graus; acima disso a detecção de olhos é descartada

# --- Pré-processamento e normalização ---------------------------------------
TAMANHO_FACE = (100, 100)    # largura x altura do rosto normalizado
CLAHE_LIMITE = 2.0
CLAHE_BLOCO = (8, 8)
# Duas etapas que, na base ORL (recortes justos, luz controlada), PIORARAM o resultado
# (EER médio de 15,1% com as duas contra 10,5% sem elas, em 30 divisões). Foram mantidas
# ligadas por serem pensadas para câmera real (fundo variável, luz irregular), mas isso é
# uma hipótese: compare as duas configurações com a sua câmera (comando `calibrar`).
USAR_CLAHE = True
USAR_MASCARA = True

# --- Qualidade mínima da amostra --------------------------------------------
BRILHO_MIN = 45.0
BRILHO_MAX = 215.0
NITIDEZ_MIN = 20.0           # variância do laplaciano no recorte normalizado

# --- Extração de características --------------------------------------------
GRADE_BLOCOS = (8, 8)        # linhas x colunas de blocos do histograma LBP

# --- Classificação e decisão -------------------------------------------------
# Limiar de distância qui-quadrado: abaixo dele o rosto é aceito como o usuário
# previsto. O valor padrão foi escolhido a partir da avaliação em base pública
# (ver módulo avaliacao) e deve ser CONFERIDO com os rostos reais de quem usa o
# sistema (comando `python -m cofre calibrar`), editando este arquivo se preciso.
LIMIAR_DISTANCIA = 0.38      # ORL, 40 pessoas, conjunto aberto: 1 impostor aceito em 200 testes
                             # (a menor distância de impostor na ORL foi 0,378). O valor foi
                             # escolhido NOS MESMOS dados em que foi medido e vale para imagens
                             # de 64x64 sem detecção; para webcam é uma estimativa de partida.
                             # Prioriza a segurança: aceitar intruso é pior que pedir ao usuário
                             # legítimo que tente de novo
MARGEM_MINIMA = 0.03         # folga mínima entre o 1º e o 2º usuário mais próximos
MELHORES_AMOSTRAS = 1        # média das k menores distâncias de cada usuário (k=1 foi o
                             # melhor na avaliação com a base ORL: EER 17,3% contra 21,0% com
                             # k=2; diferença dentro da incerteza estatística, ver relatório)
AMOSTRAS_POR_CADASTRO = 25
AMOSTRAS_MINIMAS = 5         # menos que isso o cadastro é recusado (e a calibração exige o mesmo)
INTERVALO_ENTRE_AMOSTRAS = 0.35   # segundos

# --- Autenticação em tempo real ---------------------------------------------
QUADROS_JANELA = 12          # janela de votação (últimos N quadros)
QUADROS_CONFIRMACAO = 8      # votos iguais necessários na janela
QUADROS_RECONFIRMACAO = 3    # quadros seguidos reconhecendo o MESMO usuário ao fim da prova de vida
TEMPO_MAX_AUTENTICACAO = 15  # segundos para o usuário ser reconhecido
TENTATIVAS_ATE_BLOQUEIO = 3
SEGUNDOS_BLOQUEIO = 60
EXIGIR_PROVA_DE_VIDA = True  # desafio de piscada (ver modulo prova_vida)
TEMPO_MAX_PISCADA = 8        # segundos para completar o desafio

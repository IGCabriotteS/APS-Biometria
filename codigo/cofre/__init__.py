"""Sistema de identificação e autenticação biométrica facial para o cofre do
Ministério do Meio Ambiente (APS de Processamento de Imagem e Visão Computacional).

O pacote está organizado segundo as cinco fases do processamento de imagens
digitais:

    aquisicao         -> sensor (câmera ou arquivo de imagem)
    preprocessamento  -> tons de cinza, redução de ruído, equalização
    segmentacao       -> detecção, recorte, alinhamento e máscara do rosto
    caracteristicas   -> LBP uniforme e histogramas por blocos
    classificacao     -> distância qui-quadrado e decisão de aceitação

e pelos módulos de apoio de segurança: banco, politica, autenticacao,
relatorios, avaliacao e interface.
"""

__version__ = "1.0.0"

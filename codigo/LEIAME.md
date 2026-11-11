# Cofre biométrico facial (APS de PIVC)

Sistema de identificação e autenticação por reconhecimento facial, em Python, organizado nas cinco fases do
processamento de imagens digitais. O trabalho escrito e o guia do grupo estão na pasta `documentos`.

## Instalar

```
python -m pip install -r requirements.txt
```

Python 3.12. A série 4.11 do OpenCV é obrigatória (a 5.0 não traz os classificadores de rosto e olhos).

## Usar

| Comando | O que faz |
|---|---|
| `python -m cofre` | Abre o menu (cadastro, autenticação, relatórios, demonstração das fases) |
| `python -m cofre diagnostico` | Testa a câmera, a detecção de rosto e olhos e a piscada |
| `python -m cofre autenticar-arquivo foto.jpg --compartimento 4` | Autentica a partir de uma imagem |
| `python -m cofre avaliar ..\base_teste\orl --amostras 5` | Mede FAR, FRR e EER em uma base de imagens |
| `python -m unittest discover -s testes` | Roda os 41 testes automatizados (sem câmera) |

O primeiro cadastro é sempre o do ministro (nível 3). Depois disso, cadastrar, remover usuários e gerar
relatórios exigem a autenticação facial do ministro. Os dados ficam na pasta `dados` (ou em `COFRE_DADOS`).

## Refazer experimentos e figuras (opcional)

```
python -m pip install -r requirements-ferramentas.txt
python ferramentas\baixar_orl.py ..\base_teste\orl
python ferramentas\experimentos.py ..\base_teste\orl ..\figuras ..\documentos\resultados.json
python ferramentas\gerar_figuras.py ..\base_teste\orl ..\figuras ..\documentos\resultados.json
python ferramentas\simulacao_interface.py ..\base_teste\orl
```

## Estrutura

- `cofre/`: o sistema. Um módulo por fase (`aquisicao`, `preprocessamento`, `segmentacao`, `caracteristicas`,
  `classificacao`), mais `pipeline`, `autenticacao`, `prova_vida`, `politica`, `banco`, `servico`, `relatorios`,
  `avaliacao` e `interface`.
- `testes/`: testes automatizados.
- `ferramentas/`: experimentos, figuras, download da base ORL e simulação dos fluxos de câmera.

Os parâmetros de desempenho e de segurança (limiar de decisão, janela de votação, tempos, bloqueio) ficam
todos em `cofre/config.py`.

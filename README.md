# Painel DCC

Aplicacao Dash multipagina para acompanhamento de processos, contratos, PCA, fiscais, atas e portarias.

## Requisitos

- Python 3.11+
- Dependencias de `requirements.txt`

## Como executar

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

O app sobe por padrao em `http://localhost:8050`.

## Configuracoes uteis

- `PAINEL_CACHE_DIR`: define a pasta raiz de cache em disco.
- `PAINEL_DEFAULT_YEAR`: define o ano padrao usado nas telas que dependem de um ano inicial.

Se nenhuma variavel for informada, o projeto usa:

- cache em uma pasta temporaria do sistema
- ano padrao igual ao ano corrente em `America/Sao_Paulo`

## Estrutura

- [app.py](C:/Users/PRAD130_176/Desktop/Painel_DCC/app.py): inicializacao do Dash e layout principal
- `pages/`: paginas e callbacks do painel
- `assets/`: CSS e imagens
- `utils/`: utilitarios compartilhados de runtime/configuracao

## Melhorias aplicadas

- padronizacao do diretorio de cache entre as paginas
- extracao de utilitarios compartilhados para timezone, cache e ano padrao
- documentacao inicial do projeto
- `.gitignore` para evitar ruido de ambiente local

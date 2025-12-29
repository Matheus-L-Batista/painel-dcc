import dash
from dash import html, dcc, dash_table, Input, Output
import pandas as pd

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/statusdoprocesso",
    name="Status do Processo",
    title="Status do Processo",
)

# --------------------------------------------------
# Fonte de dados (Consulta BI)
# --------------------------------------------------
URL_CONSULTA_BI = (
    "https://docs.google.com/spreadsheets/d/"
    "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog/"
    "gviz/tq?tqx=out:csv&sheet=Consulta%20BI"
)

# --------------------------------------------------
# Carga e tratamento dos dados (espelhando a consulta M,
# usando Data Mov, Data Mov.1, ..., Data Mov.39)
# --------------------------------------------------
def carregar_dados_status():
    df = pd.read_csv(URL_CONSULTA_BI)
    df.columns = [c.strip() for c in df.columns]

    # -------- Grupo base (sem sufixo) --------
    col_base = [
        "Linha", "Finalizado", "Processo", "Requisitante", "Objeto", "Modalidade",
        "Número", "Valor inicial", "Não concluído", "Entrada na DCC",
        "Data Mov", "E/S", "Deptº", "Ação",
    ]

    # Garante que colunas base existam, para evitar KeyError
    for c in col_base:
        if c not in df.columns:
            df[c] = None

    grupo0 = df[col_base].copy()

    # Tipos de data (como no M antes de combinar)
    for col in ["Finalizado", "Entrada na DCC", "Data Mov"]:
        if col in grupo0.columns:
            grupo0[col] = pd.to_datetime(grupo0[col], errors="coerce")

    grupos = [grupo0]

    # -------- Função para gerar grupos com sufixos .1, .2, ..., .39 --------
    def gerar_grupo(indice: int) -> pd.DataFrame:
        # Ex.: indice = 1 -> Data Mov.1, E/S.1, Deptº.1, Ação.1
        col_data_mov = f"Data Mov.{indice}"
        col_es = f"E/S.{indice}"
        col_dept = f"Deptº.{indice}"
        col_acao = f"Ação.{indice}"

        colunas_originais = [
            "Linha", "Finalizado", "Processo", "Requisitante", "Objeto", "Modalidade",
            "Número", "Valor inicial", "Não concluído", "Entrada na DCC",
            col_data_mov, col_es, col_dept, col_acao,
        ]

        # Seleciona apenas as colunas que realmente existem
        cols_existentes = [c for c in colunas_originais if c in df.columns]
        if not cols_existentes:
            return pd.DataFrame(columns=col_base)

        tabela = df[cols_existentes].copy()

        # Renomeia para o padrão sem sufixo
        renomear = {}
        if col_data_mov in tabela.columns:
            renomear[col_data_mov] = "Data Mov"
        if col_es in tabela.columns:
            renomear[col_es] = "E/S"
        if col_dept in tabela.columns:
            renomear[col_dept] = "Deptº"
        if col_acao in tabela.columns:
            renomear[col_acao] = "Ação"
        tabela = tabela.rename(columns=renomear)

        # Garante todas as colunas do modelo final
        for c in col_base:
            if c not in tabela.columns:
                tabela[c] = None

        # Reordena
        tabela = tabela[col_base]

        # Tipos de data nesse grupo
        for col in ["Finalizado", "Entrada na DCC", "Data Mov"]:
            if col in tabela.columns:
                tabela[col] = pd.to_datetime(tabela[col], errors="coerce")

        return tabela

    # -------- Gera grupos dinâmicos de 1 a 39 --------
    for i in range(1, 40):
        g = gerar_grupo(i)
        if not g.empty:
            grupos.append(g)

    # -------- Une tudo (equivalente a Table.Combine) --------
    tabela_unida = pd.concat(grupos, ignore_index=True)

    # Tipagem final (equivalente a TabelaFormatada)
    tabela_unida["Linha"] = tabela_unida["Linha"].astype(str)

    for col in [
        "Finalizado", "Processo", "Requisitante", "Objeto",
        "Modalidade", "Número", "Não concluído", "E/S", "Deptº", "Ação",
    ]:
        if col in tabela_unida.columns:
            tabela_unida[col] = tabela_unida[col].astype("string")

    if "Valor inicial" in tabela_unida.columns:
        tabela_unida["Valor inicial"] = pd.to_numeric(
            tabela_unida["Valor inicial"], errors="coerce"
        )

    # Entrada na DCC e Data Mov como datetime
    for col in ["Entrada na DCC", "Data Mov"]:
        if col in tabela_unida.columns:
            tabela_unida[col] = pd.to_datetime(tabela_unida[col], errors="coerce")

    # -------- Remove linhas totalmente em branco --------
    t_aux = tabela_unida.fillna("")
    mask_nao_vazia = t_aux.apply(
        lambda row: any(v not in ("", None) for v in row.values), axis=1
    )
    tabela_unida = tabela_unida[mask_nao_vazia].copy()

    # -------- Substitui null em Finalizado por "" --------
    if "Finalizado" in tabela_unida.columns:
        tabela_unida["Finalizado"] = tabela_unida["Finalizado"].fillna("")

    return tabela_unida


df_status = carregar_dados_status()

dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

# --------------------------------------------------
# Layout: filtros + duas tabelas lado a lado
# --------------------------------------------------
layout = html.Div(
    children=[
        # Barra de filtros
        html.Div(
            id="barra_filtros_status",
            className="filtros-sticky",
            children=[
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-start",
                    },
                    children=[
                        # Filtro de digitação para Processo
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Processo (digitação)"),
                                dcc.Input(
                                    id="filtro_processo_texto",
                                    type="text",
                                    placeholder="Digite parte do processo",
                                    style={
                                        "width": "100%",
                                        "marginBottom": "6px",
                                    },
                                ),
                            ],
                        ),
                        # Filtro dropdown para Processo
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Processo (seleção)"),
                                dcc.Dropdown(
                                    id="filtro_processo",
                                    options=[
                                        {"label": p, "value": p}
                                        for p in sorted(
                                            df_status["Processo"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(p) != ""
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Requisitante
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Requisitante"),
                                dcc.Dropdown(
                                    id="filtro_requisitante",
                                    options=[
                                        {"label": r, "value": r}
                                        for r in sorted(
                                            df_status["Requisitante"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(r) != ""
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Objeto
                        html.Div(
                            style={"minWidth": "260px", "flex": "2 1 320px"},
                            children=[
                                html.Label("Objeto"),
                                dcc.Dropdown(
                                    id="filtro_objeto",
                                    options=[
                                        {"label": o, "value": o}
                                        for o in sorted(
                                            df_status["Objeto"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(o) != ""
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Modalidade
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Modalidade"),
                                dcc.Dropdown(
                                    id="filtro_modalidade",
                                    options=[
                                        {"label": m, "value": m}
                                        for m in sorted(
                                            df_status["Modalidade"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(m) != ""
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        # Duas tabelas lado a lado
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "10px",
                "marginTop": "10px",
            },
            children=[
                # Tabela da esquerda
                html.Div(
                    style={"flex": "1 1 50%", "minWidth": "300px"},
                    children=[
                        html.H4("Dados do Processo"),
                        dash_table.DataTable(
                            id="tabela_status_esquerda",
                            columns=[
                                {"name": "Processo", "id": "Processo"},
                                {"name": "Requisitante", "id": "Requisitante"},
                                {"name": "Objeto", "id": "Objeto"},
                                {"name": "Modalidade", "id": "Modalidade"},
                                {"name": "Linha", "id": "Linha"},
                            ],
                            data=[],
                            style_table={
                                "overflowX": "auto",
                                "maxHeight": "500px",
                            },
                            style_cell={
                                "textAlign": "center",
                                "padding": "6px",
                                "fontSize": "12px",
                                "whiteSpace": "normal",
                            },
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": "#0b2b57",
                                "color": "white",
                            },
                        ),
                    ],
                ),
                # Tabela da direita
                html.Div(
                    style={"flex": "1 1 50%", "minWidth": "300px"},
                    children=[
                        html.H4("Movimentações"),
                        dash_table.DataTable(
                            id="tabela_status_direita",
                            columns=[
                                {"name": "Data Mov", "id": "Data Mov"},
                                {"name": "E/S", "id": "E/S"},
                                {"name": "Ação", "id": "Ação"},
                                {"name": "Deptº", "id": "Deptº"},
                            ],
                            data=[],
                            style_table={
                                "overflowX": "auto",
                                "maxHeight": "500px",
                            },
                            style_cell={
                                "textAlign": "center",
                                "padding": "6px",
                                "fontSize": "12px",
                                "whiteSpace": "normal",
                            },
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": "#0b2b57",
                                "color": "white",
                            },
                        ),
                    ],
                ),
            ],
        ),
    ]
)

# --------------------------------------------------
# Callback de filtros, regras e formatação de datas
# --------------------------------------------------
@dash.callback(
    Output("tabela_status_esquerda", "data"),
    Output("tabela_status_direita", "data"),
    Input("filtro_processo_texto", "value"),
    Input("filtro_processo", "value"),
    Input("filtro_requisitante", "value"),
    Input("filtro_objeto", "value"),
    Input("filtro_modalidade", "value"),
)
def atualizar_tabelas(
    proc_texto,
    proc_select,
    requisitante,
    objeto,
    modalidade,
):
    dff = df_status.copy()

    # Filtro por digitação em Processo
    if proc_texto and str(proc_texto).strip():
        termo = str(proc_texto).strip()
        dff = dff[
            dff["Processo"]
            .astype(str)
            .str.contains(termo, case=False, na=False)
        ]

    # Filtro dropdown de Processo
    if proc_select:
        dff = dff[dff["Processo"] == proc_select]

    if requisitante:
        dff = dff[dff["Requisitante"] == requisitante]

    if objeto:
        dff = dff[dff["Objeto"] == objeto]

    if modalidade:
        dff = dff[dff["Modalidade"] == modalidade]

    # Ordenar em ordem decrescente pela coluna Linha
    try:
        dff["Linha_ordenacao"] = pd.to_numeric(dff["Linha"], errors="coerce")
    except Exception:
        dff["Linha_ordenacao"] = dff["Linha"]

    dff = dff.sort_values("Linha_ordenacao", ascending=False)

    # ---------------------------
    # TABELA ESQUERDA (Processo)
    # ---------------------------
    # Remove processos vazios/brancos
    mask_proc_valido = (
        dff["Processo"]
        .astype(str)
        .str.strip()
        .ne("")
    )
    dff_esq = dff[mask_proc_valido].copy()

    # Mantém apenas uma linha por Processo (primeira após ordenação)
    dff_esq = dff_esq.drop_duplicates(subset=["Processo"], keep="first")

    # Formata datas para dd/mm/aaaa, se existirem
    if "Data Mov" in dff_esq.columns:
        dff_esq["Data Mov"] = pd.to_datetime(
            dff_esq["Data Mov"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")
    if "Entrada na DCC" in dff_esq.columns:
        dff_esq["Entrada na DCC"] = pd.to_datetime(
            dff_esq["Entrada na DCC"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")

    cols_esq = ["Processo", "Requisitante", "Objeto", "Modalidade", "Linha"]
    dados_esquerda = dff_esq[cols_esq].to_dict("records")

    # ---------------------------
    # TABELA DIREITA (Movimentações)
    # ---------------------------
    dff_dir = dff.copy()

    # Remove linhas com Ação vazia/branca
    mask_acao_valida = (
        dff_dir["Ação"]
        .astype(str)
        .str.strip()
        .ne("")
    )
    # Remove linhas com E/S vazia/branca
    mask_es_valida = (
        dff_dir["E/S"]
        .astype(str)
        .str.strip()
        .ne("")
    )
    dff_dir = dff_dir[mask_acao_valida & mask_es_valida].copy()

    # Formata Data Mov para dd/mm/aaaa
    if "Data Mov" in dff_dir.columns:
        dff_dir["Data Mov"] = pd.to_datetime(
            dff_dir["Data Mov"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")

    cols_dir = ["Data Mov", "E/S", "Ação", "Deptº"]
    dados_direita = dff_dir[cols_dir].to_dict("records")

    return dados_esquerda, dados_direita

import dash
from dash import html, dcc, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib import colors
from datetime import datetime, timedelta
from pytz import timezone
import os
import threading
import pickle

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
# Carga e tratamento: empilha Data Mov, Data Mov.1, ...
# --------------------------------------------------
def carregar_dados_status():
    """
    Lê a planilha de Consulta BI e:
    - garante colunas fixas
    - empilha colunas Data Mov / E/S / Deptº / Ação em um único bloco
    - remove linhas totalmente vazias
    - converte tipos básicos (datas, numéricos)
    """
    df = pd.read_csv(URL_CONSULTA_BI, header=0)
    df.columns = [c.strip() for c in df.columns]

    col_fixas = [
        "Linha",
        "Finalizado",
        "Processo",
        "Requisitante",
        "Objeto",
        "Modalidade",
        "Número",
        "Valor inicial",
        "Não concluído",
        "Entrada na DCC",
    ]

    for c in col_fixas:
        if c not in df.columns:
            df[c] = None

    if "Data Mov" not in df.columns:
        df["Data Mov"] = None

    for c in ["E/S", "Deptº", "Ação"]:
        if c not in df.columns:
            df[c] = None

    # Identifica todas as colunas de Data Mov (Data Mov, Data Mov.1, ...)
    data_cols = [c for c in df.columns if c.startswith("Data Mov")]
    grupos = []

    # Bloco base (Data Mov "principal")
    grupo0 = df[col_fixas + ["Data Mov", "E/S", "Deptº", "Ação"]].copy()
    grupos.append(grupo0)

    # Demais blocos Data MovX / E/SX / DeptºX / AçãoX
    for col in data_cols:
        if col == "Data Mov":
            continue

        suf = col[len("Data Mov") :]
        col_data = f"Data Mov{suf}"
        col_es = f"E/S{suf}"
        col_dept = f"Deptº{suf}"
        col_acao = f"Ação{suf}"

        for c in [col_data, col_es, col_dept, col_acao]:
            if c not in df.columns:
                df[c] = None

        bloco = df[col_fixas + [col_data, col_es, col_dept, col_acao]].copy()
        bloco = bloco.rename(
            columns={
                col_data: "Data Mov",
                col_es: "E/S",
                col_dept: "Deptº",
                col_acao: "Ação",
            }
        )
        grupos.append(bloco)

    tabela_unida = pd.concat(grupos, ignore_index=True)

    # Remove linhas totalmente vazias
    t_aux = tabela_unida.replace({None: pd.NA}).fillna("")
    mask_nao_vazia = t_aux.apply(
        lambda row: any(v not in ("", None) for v in row.values), axis=1
    )
    tabela_unida = tabela_unida[mask_nao_vazia].copy()

    # Ajustes de tipos
    tabela_unida["Linha"] = tabela_unida["Linha"].astype(str)

    for col in [
        "Finalizado",
        "Processo",
        "Requisitante",
        "Objeto",
        "Modalidade",
        "Número",
        "Não concluído",
        "E/S",
        "Deptº",
        "Ação",
    ]:
        if col in tabela_unida.columns:
            tabela_unida[col] = tabela_unida[col].astype("string")

    if "Valor inicial" in tabela_unida.columns:
        tabela_unida["Valor inicial"] = pd.to_numeric(
            tabela_unida["Valor inicial"], errors="coerce"
        )

    for col in ["Entrada na DCC", "Data Mov"]:
        if col in tabela_unida.columns:
            tabela_unida[col] = pd.to_datetime(
                tabela_unida[col], errors="coerce", dayfirst=True
            )

    tabela_unida["Finalizado"] = tabela_unida["Finalizado"].fillna("")

    return tabela_unida


# --------------------------------------------------
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h (igual aos outros painéis)
_CACHE_LOCK = threading.Lock()
_DF_CACHE = None
_DF_CACHE_AT = None

# cache em disco (para sobreviver a restart do processo)
_CACHE_DIR = os.path.join(os.path.dirname(__file__) if "__file__" in globals() else os.getcwd(), ".cache_status")
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "df_status.pkl")
_CACHE_META = os.path.join(_CACHE_DIR, "meta.pkl")


def _now_sp():
    return datetime.now(timezone("America/Sao_Paulo"))


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "-"
    try:
        return dt.astimezone(timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return dt.strftime("%d/%m/%Y %H:%M:%S")


def _load_disk_cache():
    try:
        if not (os.path.exists(_CACHE_FILE) and os.path.exists(_CACHE_META)):
            return None, None
        with open(_CACHE_META, "rb") as f:
            meta = pickle.load(f)
        cached_at = meta.get("cached_at")
        if not cached_at:
            return None, None
        # cached_at salvo como iso str
        cached_at_dt = datetime.fromisoformat(cached_at)
        age = datetime.now() - cached_at_dt
        if age > timedelta(minutes=CACHE_TTL_MINUTOS):
            return None, None
        df = pd.read_pickle(_CACHE_FILE)
        return df, cached_at_dt
    except Exception:
        return None, None


def _save_disk_cache(df: pd.DataFrame, cached_at: datetime):
    try:
        df.to_pickle(_CACHE_FILE)
        with open(_CACHE_META, "wb") as f:
            pickle.dump({"cached_at": cached_at.isoformat()}, f)
    except Exception:
        pass


def get_df_status(force: bool = False):
    """
    Retorna (df, status_msg).
    - Usa cache em memória (mais rápido)
    - Se memória vazia, tenta cache em disco
    - Se TTL expirou ou force=True, lê da planilha
    """
    global _DF_CACHE, _DF_CACHE_AT

    now_naive = datetime.now()
    stale = (
        _DF_CACHE is None
        or _DF_CACHE_AT is None
        or (now_naive - _DF_CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
    )

    if force or stale:
        with _CACHE_LOCK:
            now2 = datetime.now()
            stale2 = (
                _DF_CACHE is None
                or _DF_CACHE_AT is None
                or (now2 - _DF_CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
            )

            # tenta disco antes de ir na planilha, se não for force
            if (not force) and stale2:
                df_disk, at_disk = _load_disk_cache()
                if df_disk is not None and at_disk is not None:
                    _DF_CACHE = df_disk
                    _DF_CACHE_AT = now2  # marca "agora" como uso em memória
                    return _DF_CACHE, f"Dados carregados do cache em disco ({_fmt_dt(at_disk)})."

            if force or stale2:
                df = carregar_dados_status()
                _DF_CACHE = df
                _DF_CACHE_AT = now2
                _save_disk_cache(df, now2)
                return _DF_CACHE, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())})."

    return _DF_CACHE, f"Dados em cache (memória) — último refresh: {_fmt_dt(_now_sp())}."


def verificar_pagina_status():
    """
    Segurança: evita callback rodar fora da página /statusdoprocesso.
    """
    try:
        trig = dash.ctx.triggered_id
        # se for None (primeira renderização), deixa passar
        return True
    except Exception:
        return True


# --------------------------------------------------
# Estilos / layout (Dash)
# --------------------------------------------------
dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
    "position": "relative",
    "zIndex": 9999,
}

botao_style = {
    "backgroundColor": "#0b2b57",
    "color": "white",
    "border": "none",
    "padding": "6px 12px",
    "borderRadius": "4px",
    "cursor": "pointer",
}

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    children=[
        dcc.Location(id="url"),
        # Barra de filtros
        html.Div(
            id="barra_filtros_status",
            style={
                "position": "relative",
                "zIndex": 10,
                "overflow": "visible",
                "backgroundColor": "white",
                "paddingBottom": "4px",
            },
            children=[
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-start",
                    },
                    children=[
                        # Processo
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Processo"),
                                dcc.Dropdown(
                                    id="filtro_processo",
                                    options=[],
                                    placeholder="Selecione um processo...",
                                    clearable=True,
                                    searchable=True,
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
                                    options=[],
                                    placeholder="Selecione um requisitante...",
                                    clearable=True,
                                    searchable=True,
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
                                    options=[],
                                    placeholder="Selecione um objeto...",
                                    clearable=True,
                                    searchable=True,
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
                                    options=[],
                                    placeholder="Selecione uma modalidade...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                    ],
                ),
                # Botões
                html.Div(
                    style={"marginTop": "4px", "display": "flex", "flexWrap": "wrap", "gap": "10px", "alignItems": "center"},
                    children=[
                        html.Button(
                            "Limpar filtros",
                            id="btn_limpar_filtros_status",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        html.Button(
                            "Atualizar Dados",
                            id="btn_reload_status",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        html.Button(
                            "Baixar Relatório PDF",
                            id="btn_download_relatorio_status",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        dcc.Download(id="download_relatorio_status"),
                        html.Div(
                            id="info-atualizacao-status",
                            style={"fontSize": "12px", "color": "#333"},
                        ),
                    ],
                ),
            ],
        ),
        # Tabelas esquerda / direita
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "10px",
                "marginTop": "10px",
            },
            children=[
                # ---------------- TABELA ESQUERDA ----------------
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
                            fixed_rows={"headers": True},
                            style_table={
                                "overflowX": "auto",
                                "overflowY": "auto",
                                "maxHeight": "500px",
                                "position": "relative",
                                "zIndex": 1,
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
                                "zIndex": 2,
                            },
                            row_selectable=False,
                            cell_selectable=False,
                        ),
                    ],
                ),
                # ---------------- TABELA DIREITA ----------------
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
                            fixed_rows={"headers": True},
                            style_table={
                                "overflowX": "auto",
                                "overflowY": "auto",
                                "maxHeight": "500px",
                                "position": "relative",
                                "zIndex": 1,
                            },
                            style_cell={
                                "textAlign": "center",
                                "padding": "6px",
                                "fontSize": "12px",
                                "whiteSpace": "normal",
                            },
                            style_cell_conditional=[
                                {"if": {"column_id": "Data Mov"}, "width": "15%"},
                                {"if": {"column_id": "E/S"}, "width": "15%"},
                                {"if": {"column_id": "Ação"}, "width": "50%", "textAlign": "center"},
                                {"if": {"column_id": "Deptº"}, "width": "20%"},
                            ],
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": "#0b2b57",
                                "color": "white",
                                "textAlign": "center",
                                "zIndex": 2,
                            },
                            style_data_conditional=[
                                {
                                    "if": {"row_index": 0},
                                    "backgroundColor": "#ff9800",
                                    "fontWeight": "bold",
                                    "color": "white",
                                },
                            ],
                            row_selectable=False,
                            cell_selectable=False,
                        ),
                    ],
                ),
            ],
        ),
        # Stores / interval
        dcc.Store(id="store-reload-status"),
        dcc.Interval(id="interval-reload-status", interval=60 * 60 * 1000, n_intervals=0),  # 1h
        dcc.Store(id="store_dados_status"),
    ],
)

# --------------------------------------------------
# Função auxiliar: filtro e limpeza de linhas
# --------------------------------------------------
def limpar_linhas_invalidas(df, colunas_check=None):
    """
    Remove linhas onde TODAS as colunas_check são NaN/vazias/ inválidas.
    Se colunas_check não for fornecido, verifica todas as colunas.
    """
    if df.empty:
        return df

    if colunas_check is None:
        colunas_check = df.columns.tolist()

    colunas_check = [c for c in colunas_check if c in df.columns]

    def eh_valido(valor):
        if pd.isna(valor):
            return False
        valor_str = str(valor).strip().lower()
        if valor_str in ("", "nan", "none", "nat", "<na>"):
            return False
        return True

    mask = df[colunas_check].apply(
        lambda row: any(eh_valido(v) for v in row.values), axis=1
    )

    return df[mask].copy()


def _opcoes(col):
    df, _ = get_df_status(force=False)
    if df is None or df.empty or col not in df.columns:
        return []
    vals = [str(v) for v in sorted(df[col].dropna().unique()) if str(v).strip() != ""]
    return [{"label": v, "value": v} for v in vals]


# --------------------------------------------------
# Callback: carregar ao abrir / interval / botão (atualiza cache + opções)
# --------------------------------------------------
@dash.callback(
    Output("store-reload-status", "data"),
    Output("info-atualizacao-status", "children"),
    Output("filtro_processo", "options"),
    Output("filtro_requisitante", "options"),
    Output("filtro_objeto", "options"),
    Output("filtro_modalidade", "options"),
    Input("url", "pathname"),
    Input("interval-reload-status", "n_intervals"),
    Input("btn_reload_status", "n_clicks"),
)
def carregar_ao_abrir_interval_ou_recarregar(pathname, n_intervals, n_clicks):
    if pathname != "/statusdoprocesso":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    df, status = get_df_status(force=force)

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    op_proc = [{"label": str(p), "value": str(p)} for p in sorted(df["Processo"].dropna().unique()) if str(p).strip() != ""] if df is not None and "Processo" in df.columns else []
    op_req  = [{"label": str(r), "value": str(r)} for r in sorted(df["Requisitante"].dropna().unique()) if str(r).strip() != ""] if df is not None and "Requisitante" in df.columns else []
    op_obj  = [{"label": str(o), "value": str(o)} for o in sorted(df["Objeto"].dropna().unique()) if str(o).strip() != ""] if df is not None and "Objeto" in df.columns else []
    op_mod  = [{"label": str(m), "value": str(m)} for m in sorted(df["Modalidade"].dropna().unique()) if str(m).strip() != ""] if df is not None and "Modalidade" in df.columns else []

    return {"ts": datetime.now().isoformat()}, msg, op_proc, op_req, op_obj, op_mod


# --------------------------------------------------
# Função auxiliar: filtrar dados com base nos filtros atuais
# --------------------------------------------------
def filtrar_dados(df_base, processo=None, requisitante=None, objeto=None, modalidade=None):
    """Filtra df_base conforme filtros"""
    if df_base is None or df_base.empty:
        return pd.DataFrame()

    dff = df_base.copy()
    mask = pd.Series(True, index=dff.index)

    if processo:
        mask &= dff["Processo"] == processo
    if requisitante:
        mask &= dff["Requisitante"] == requisitante
    if objeto:
        mask &= dff["Objeto"] == objeto
    if modalidade:
        mask &= dff["Modalidade"] == modalidade

    return dff[mask].copy()


# --------------------------------------------------
# Callback principal: tabelas (agora reage ao store-reload-status)
# --------------------------------------------------
@dash.callback(
    Output("tabela_status_esquerda", "data"),
    Output("tabela_status_direita", "data"),
    Output("store_dados_status", "data"),
    Input("store-reload-status", "data"),
    Input("filtro_processo", "value"),
    Input("filtro_requisitante", "value"),
    Input("filtro_objeto", "value"),
    Input("filtro_modalidade", "value"),
)
def atualizar_tabelas(_reload, processo, requisitante, objeto, modalidade):
    df_base, _ = get_df_status(force=False)
    dff = filtrar_dados(df_base, processo, requisitante, objeto, modalidade)

    if dff.empty:
        return [], [], []

    # Ordenar pela linha (desc)
    try:
        dff["Linha_ordenacao"] = pd.to_numeric(dff["Linha"], errors="coerce")
    except Exception:
        dff["Linha_ordenacao"] = dff["Linha"]
    dff = dff.sort_values("Linha_ordenacao", ascending=False)

    # Esquerda: Dados do Processo
    mask_proc_valido = dff["Processo"].astype(str).str.strip().ne("")
    dff_esq = dff[mask_proc_valido].copy()
    dff_esq = dff_esq.drop_duplicates(subset=["Processo"], keep="first")
    dff_esq = limpar_linhas_invalidas(
        dff_esq,
        colunas_check=["Processo", "Requisitante", "Objeto", "Modalidade"],
    )

    dados_esquerda = dff_esq[
        ["Processo", "Requisitante", "Objeto", "Modalidade", "Linha"]
    ].to_dict("records")

    # Direita: Movimentações
    dff_dir = dff.copy()
    for c in ["Data Mov", "E/S", "Ação", "Deptº"]:
        if c in dff_dir.columns:
            dff_dir[c] = dff_dir[c].astype(str).str.strip()

    if "Ação" in dff_dir.columns:
        mask_acao_valida = (
            dff_dir["Ação"].ne("")
            & dff_dir["Ação"].str.lower().ne("none")
            & dff_dir["Ação"].str.lower().ne("nan")
            & dff_dir["Ação"].str.lower().ne("nat")
            & dff_dir["Ação"].str.lower().ne("<na>")
        )
        dff_dir = dff_dir[mask_acao_valida].copy()

    dff_dir["Data Mov_dt"] = pd.to_datetime(dff_dir["Data Mov"], errors="coerce")
    dff_dir["ordem_acao"] = (
        dff_dir["Ação"].astype(str).str.strip() != "FIM DCC"
    ).astype(int)

    dff_dir = dff_dir.sort_values(
        by=["Data Mov_dt", "ordem_acao"],
        ascending=[False, True],
        na_position="last",
    )

    dff_dir["Data Mov"] = dff_dir["Data Mov_dt"].dt.strftime("%d/%m/%Y").fillna("")
    dff_dir = limpar_linhas_invalidas(dff_dir, colunas_check=["Data Mov", "E/S", "Ação", "Deptº"])

    dados_direita = dff_dir[["Data Mov", "E/S", "Ação", "Deptº"]].to_dict("records")

    # store_dados_status: mantém apenas o "direita" (como antes), suficiente p/ PDF
    return dados_esquerda, dados_direita, dff_dir.to_dict("records")


# --------------------------------------------------
# Callback: atualizar opções dos filtros em cascata (reage ao reload também)
# --------------------------------------------------
@dash.callback(
    Output("filtro_processo", "options", allow_duplicate=True),
    Output("filtro_requisitante", "options", allow_duplicate=True),
    Output("filtro_objeto", "options", allow_duplicate=True),
    Output("filtro_modalidade", "options", allow_duplicate=True),
    Input("store-reload-status", "data"),
    Input("filtro_processo", "value"),
    Input("filtro_requisitante", "value"),
    Input("filtro_objeto", "value"),
    Input("filtro_modalidade", "value"),
    prevent_initial_call=True,
)
def atualizar_opcoes_filtros_cascata(_reload, processo, requisitante, objeto, modalidade):
    df_base, _ = get_df_status(force=False)
    dff = filtrar_dados(df_base, processo, requisitante, objeto, modalidade)
    dff = limpar_linhas_invalidas(dff)

    def opts(col):
        if dff.empty or col not in dff.columns:
            return []
        return [
            {"label": str(v), "value": str(v)}
            for v in sorted(dff[col].dropna().unique())
            if str(v).strip().lower() not in ("", "nan", "none", "nat", "<na>")
        ]

    return opts("Processo"), opts("Requisitante"), opts("Objeto"), opts("Modalidade")


# --------------------------------------------------
# Callback: limpar filtros
# --------------------------------------------------
@dash.callback(
    Output("filtro_processo", "value"),
    Output("filtro_requisitante", "value"),
    Output("filtro_objeto", "value"),
    Output("filtro_modalidade", "value"),
    Input("btn_limpar_filtros_status", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_status(_n):
    return None, None, None, None


# ========================================
# BLOCO PDF (ReportLab) – STATUS
# ========================================
wrap_style_status = ParagraphStyle(
    name="wrap_status",
    fontSize=7,
    leading=9,
    spaceAfter=2,
)

simple_style_status = ParagraphStyle(
    name="simple_status",
    fontSize=7,
    alignment=TA_CENTER,
)


def wrap_pdf(text):
    return Paragraph(str(text), wrap_style_status)


def simple_pdf(text):
    return Paragraph(str(text), simple_style_status)


def adicionar_cabecalho_status(story, df_esq, df_dir, styles):
    logo_esq = (
        Image("assets/brasaobrasil.png", 1.2 * inch, 1.2 * inch)
        if os.path.exists("assets/brasaobrasil.png") else ""
    )

    logo_dir = (
        Image("assets/simbolo_RGB.png", 1.2 * inch, 1.2 * inch)
        if os.path.exists("assets/simbolo_RGB.png") else ""
    )

    texto_instituicao = (
        "<b><font color='#0b2b57' size=13>Ministério da Educação</font></b><br/>"
        "<b><font color='#0b2b57' size=13>Universidade Federal de Itajubá</font></b><br/>"
        "<font color='#0b2b57' size=11>Diretoria de Compras e Contratos</font>"
    )

    instituicao = Paragraph(
        texto_instituicao,
        ParagraphStyle(
            "instituicao",
            alignment=TA_CENTER,
            leading=16,
        ),
    )

    cabecalho = Table(
        [[logo_esq, instituicao, logo_dir]],
        colWidths=[1.4 * inch, 4.2 * inch, 1.4 * inch],
    )
    cabecalho.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(cabecalho)
    story.append(Spacer(1, 0.25 * inch))

    titulo = Paragraph(
        "RELATÓRIO DE STATUS DO PROCESSO<br/>",
        ParagraphStyle(
            "titulo_status",
            alignment=TA_CENTER,
            fontSize=10,
            leading=14,
            textColor=colors.black,
        ),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))

    total_esq = len(df_esq) if not df_esq.empty else 0
    total_dir = len(df_dir) if not df_dir.empty else 0
    total_geral = total_esq + total_dir

    story.append(
        Paragraph(f"Total de registros: {total_geral}", styles["Normal"])
    )
    story.append(Spacer(1, 0.15 * inch))


def criar_tabela_dados_processo(story, df_esq, styles):
    if df_esq.empty:
        return

    story.append(
        Paragraph(
            "DADOS DO PROCESSO",
            ParagraphStyle(
                "subtitulo_status_esq",
                fontSize=9,
                alignment=TA_LEFT,
                textColor="#0b2b57",
                fontName="Helvetica-Bold",
                spaceAfter=6,
            ),
        )
    )

    story.append(Paragraph(f"Total de registros: {len(df_esq)}", styles["Normal"]))
    story.append(Spacer(1, 0.08 * inch))

    cols_esq = ["Processo", "Requisitante", "Objeto", "Modalidade", "Linha"]
    cols_esq = [c for c in cols_esq if c in df_esq.columns]
    df_esq_filtered = df_esq[cols_esq].copy()

    table_data_esq = [cols_esq]
    for _, row in df_esq_filtered.iterrows():
        table_data_esq.append([simple_pdf("" if pd.isna(row[c]) else str(row[c]).strip()) for c in cols_esq])

    col_widths_esq = [2.0 * inch, 1.2 * inch, 2.5 * inch, 1.2 * inch, 0.6 * inch][: len(cols_esq)]
    tbl_esq = Table(table_data_esq, colWidths=col_widths_esq, repeatRows=1)

    tbl_esq.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTWEIGHT", (0, 0), (-1, 0), "bold"),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#0b2b57")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                ("WORDWRAP", (0, 0), (-1, -1), True),
            ]
        )
    )

    story.append(tbl_esq)
    story.append(Spacer(1, 0.2 * inch))


def criar_tabela_movimentacoes(story, df_dir, styles):
    if df_dir.empty:
        return

    story.append(
        Paragraph(
            "MOVIMENTAÇÕES",
            ParagraphStyle(
                "subtitulo_status_dir",
                fontSize=9,
                alignment=TA_LEFT,
                textColor="#0b2b57",
                fontName="Helvetica-Bold",
                spaceAfter=6,
            ),
        )
    )

    story.append(Paragraph(f"Total de registros: {len(df_dir)}", styles["Normal"]))
    story.append(Spacer(1, 0.08 * inch))

    cols_dir = ["Data Mov", "E/S", "Ação", "Deptº"]
    cols_dir = [c for c in cols_dir if c in df_dir.columns]

    df_dir_copy = df_dir.copy()
    df_dir_copy["Data Mov_dt"] = pd.to_datetime(df_dir_copy["Data Mov"], errors="coerce")
    df_dir_copy["ordem_acao"] = (df_dir_copy["Ação"].astype(str).str.strip() != "FIM DCC").astype(int)
    df_dir_copy = df_dir_copy.sort_values(by=["Data Mov_dt", "ordem_acao"], ascending=[False, True], na_position="last")
    df_dir_copy["Data Mov"] = df_dir_copy["Data Mov_dt"].dt.strftime("%d/%m/%Y").fillna("")

    df_dir_copy["Ação"] = df_dir_copy["Ação"].astype(str).str.strip()
    df_dir_copy = df_dir_copy[
        (df_dir_copy["Ação"] != "")
        & (df_dir_copy["Ação"].str.lower() != "none")
        & (df_dir_copy["Ação"].str.lower() != "nan")
        & (df_dir_copy["Ação"].str.lower() != "nat")
        & (df_dir_copy["Ação"].str.lower() != "<na>")
    ]

    df_dir_copy = limpar_linhas_invalidas(df_dir_copy, colunas_check=cols_dir)
    df_dir_filtered = df_dir_copy[cols_dir].copy()

    table_data_dir = [cols_dir]
    for _, row in df_dir_filtered.iterrows():
        linha = []
        for c in cols_dir:
            valor = "" if pd.isna(row[c]) else str(row[c]).strip()
            linha.append(wrap_pdf(valor) if c == "Ação" else simple_pdf(valor))
        table_data_dir.append(linha)

    col_widths_dir = [1.0 * inch, 1.0 * inch, 3.0 * inch, 1.0 * inch][: len(cols_dir)]
    tbl_dir = Table(table_data_dir, colWidths=col_widths_dir, repeatRows=1)

    tbl_dir.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTWEIGHT", (0, 0), (-1, 0), "bold"),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#0b2b57")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ff9800")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
                ("FONTWEIGHT", (0, 1), (-1, 1), "bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                ("WORDWRAP", (0, 0), (-1, -1), True),
            ]
        )
    )

    story.append(tbl_dir)


@dash.callback(
    Output("download_relatorio_status", "data"),
    Input("btn_download_relatorio_status", "n_clicks"),
    State("store_dados_status", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_status(n, dados_status):
    if not n or not dados_status:
        return None

    df_todos = pd.DataFrame(dados_status)

    df_esq = df_todos.copy()
    df_esq = df_esq.drop_duplicates(subset=["Processo"], keep="first")
    df_esq["Processo"] = df_esq["Processo"].astype(str).str.strip()
    df_esq = df_esq[df_esq["Processo"] != ""]
    df_esq = df_esq[df_esq["Processo"].str.lower() != "nan"]
    df_esq = limpar_linhas_invalidas(df_esq, colunas_check=["Processo", "Requisitante", "Objeto", "Modalidade"])

    df_dir = df_todos.copy()
    if "Ação" in df_dir.columns:
        df_dir["Ação"] = df_dir["Ação"].astype(str).str.strip()
        df_dir = df_dir[df_dir["Ação"] != ""]
        df_dir = df_dir[df_dir["Ação"].str.lower() not in ("nan", "none", "nat", "<na>")]

    df_dir = limpar_linhas_invalidas(df_dir, colunas_check=["Data Mov", "E/S", "Ação", "Deptº"])

    if df_esq.empty and df_dir.empty:
        return None

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.2 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    adicionar_cabecalho_status(story, df_esq, df_dir, styles)
    if not df_esq.empty:
        criar_tabela_dados_processo(story, df_esq, styles)
    if not df_dir.empty:
        criar_tabela_movimentacoes(story, df_dir, styles)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"status_processos_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

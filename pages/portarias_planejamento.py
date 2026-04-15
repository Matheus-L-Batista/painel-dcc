import dash
from dash import html, dcc, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd

from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
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
from reportlab.lib import colors

from datetime import datetime, timedelta
from pytz import timezone
import os
import threading
import pickle

from utils.runtime import format_datetime_sp, get_cache_dir, now_sp

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/portarias_planejamento",
    name="Portarias – Planejamento",
    title="Portarias – Planejamento",
)

# --------------------------------------------------
# URL da planilha de Portarias
# --------------------------------------------------
URL_PORTARIAS = (
    "https://docs.google.com/spreadsheets/d/"
    "17nBhvSoCeK3hNgCj2S57q3pF2Uxj6iBpZDvCX481KcU/"
    "gviz/tq?tqx=out:csv&sheet=Check%20List"
)

# nome EXATO da coluna de link no CSV
NOME_COL_LINK_ORIGINAL = "Link do documento\nEquipe de Planejamento"

# --------------------------------------------------
# Carga e tratamento dos dados
# --------------------------------------------------
def carregar_dados_portarias():
    df = pd.read_csv(URL_PORTARIAS, header=1)
    df.columns = [c.strip() for c in df.columns]

    df = df.rename(
        columns={
            "Unnamed: 5": "Data",
            "N° / ANO": "N°/ANO da Portaria",
            "ORIGEM": "Setor de Origem",
        }
    )

    # Colunas de servidores (1..15) se existirem
    cols_serv = [str(i) for i in range(1, 16) if str(i) in df.columns]

    # Concatena servidores em uma única coluna
    if cols_serv:
        df["Servidores"] = (
            df[cols_serv]
            .astype(str)
            .replace({"nan": ""})
            .agg("; ".join, axis=1)
            .str.replace(r"(; )+$", "", regex=True)
        )
    else:
        df["Servidores"] = ""

    if "TIPO" not in df.columns:
        df["TIPO"] = ""

    # Tipos específicos desta página
    tipos_validos = [
        "PORTARIA DE PLANEJAMENTO DA CONTRATAÇÃO",
        "PORTARIA DE PLANEJAMENTO DA CONTRATAÇÃO - TI",
    ]
    df = df[df["TIPO"].isin(tipos_validos)]

    if NOME_COL_LINK_ORIGINAL not in df.columns:
        df[NOME_COL_LINK_ORIGINAL] = ""

    # mantém apenas linhas com link válido
    df = df[
        df[NOME_COL_LINK_ORIGINAL]
        .astype(str)
        .str.strip()
        .str.startswith("http")
    ]

    # Coluna técnica de data para ordenação correta
    df["Data_dt"] = pd.to_datetime(df["Data"], dayfirst=True, errors="coerce")

    # Quebra N°/ANO da Portaria em ano e número para ordenação correta
    def split_portaria(valor):
        s = str(valor).strip()
        if "/" in s:
            a, b = s.split("/", 1)
            try:
                return int(b), int(a)
            except Exception:
                return 0, 0
        return 0, 0

    df["_portaria_ano"] = df["N°/ANO da Portaria"].apply(lambda x: split_portaria(x)[0])
    df["_portaria_num"] = df["N°/ANO da Portaria"].apply(lambda x: split_portaria(x)[1])

    # Ordenação padrão: data mais recente, depois ano e número da portaria
    df = df.sort_values(
        by=["Data_dt", "_portaria_ano", "_portaria_num"],
        ascending=[False, False, False],
        na_position="last",
    )

    # lista de servidores únicos após o filtro
    if cols_serv:
        todos_serv = pd.Series(df[cols_serv].values.ravel("K"), dtype="object")
        servidores_unicos = sorted(
            [s for s in todos_serv.unique() if isinstance(s, str) and s.strip() != ""]
        )
    else:
        servidores_unicos = []

    # armazena lista de servidores únicos como atributo
    df._lista_servidores_unicos = servidores_unicos

    return df


# --------------------------------------------------
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h (padrão)
_CACHE_LOCK = threading.Lock()
_DF_CACHE = None
_DF_CACHE_AT = None

_CACHE_DIR = os.path.join(
    str(get_cache_dir("portarias_planejamento"))
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "df_portarias_planej.pkl")
_CACHE_META = os.path.join(_CACHE_DIR, "meta.pkl")


def _now_sp():
    return now_sp()


def _fmt_dt(dt):
    return format_datetime_sp(dt)


def _load_disk_cache():
    try:
        if not (os.path.exists(_CACHE_FILE) and os.path.exists(_CACHE_META)):
            return None, None
        with open(_CACHE_META, "rb") as f:
            meta = pickle.load(f)
        cached_at = meta.get("cached_at")
        if not cached_at:
            return None, None
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


def get_df_portarias(force: bool = False):
    """
    Retorna (df, status_msg).

    - Cache em memória (mais rápido)
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

            if (not force) and stale2:
                df_disk, at_disk = _load_disk_cache()
                if df_disk is not None and at_disk is not None:
                    _DF_CACHE = df_disk
                    _DF_CACHE_AT = now2
                    return _DF_CACHE, f"Dados carregados do cache em disco ({_fmt_dt(at_disk)})."

            if force or stale2:
                df = carregar_dados_portarias()
                _DF_CACHE = df
                _DF_CACHE_AT = now2
                _save_disk_cache(df, now2)
                return _DF_CACHE, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())})."

    return _DF_CACHE, f"Dados em cache (memória) — verificado em {_fmt_dt(_now_sp())}."


def _opcoes_dropdown(dff: pd.DataFrame, col: str):
    if dff is None or dff.empty or col not in dff.columns:
        return []
    return [
        {"label": str(v), "value": str(v)}
        for v in sorted(dff[col].dropna().unique())
        if str(v).strip() != ""
    ]


def _servidores_unicos_do_subset(dff: pd.DataFrame):
    if dff is None or dff.empty:
        return []
    cols_serv = [str(i) for i in range(1, 16) if str(i) in dff.columns]
    if not cols_serv:
        return []
    todos_serv = pd.Series(dff[cols_serv].values.ravel("K"), dtype="object")
    return sorted([s for s in todos_serv.unique() if isinstance(s, str) and s.strip() != ""])


# --------------------------------------------------
# Estilos
# --------------------------------------------------
dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

botao_style = {
    "backgroundColor": "#0b2b57",
    "color": "white",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
    "marginRight": "6px",
}

botao_limpar_style = {
    "backgroundColor": "#adb5bd",
    "color": "black",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
    "marginRight": "6px",
}

botao_pdf_style = {
    "backgroundColor": "#e1261c",
    "color": "white",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
    "marginRight": "6px",
}

page_style = {"padding": "14px", "backgroundColor": "#f6f8fb", "minHeight": "100vh"}
card_shell_style = {
    "backgroundColor": "white",
    "border": "1px solid #e6ebf2",
    "borderRadius": "14px",
    "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
}

datatable_links_css = [
    {"selector": "p", "rule": "margin: 0; text-align: center;"},
    {
        "selector": "td a",
        "rule": "display:inline-block; padding:4px 10px; border-radius:999px; background:#eaf2ff; color:#0b2b57; font-weight:600; text-decoration:none;",
    },
]

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style=page_style,
    children=[
        dcc.Location(id="url"),
        html.Div(
            id="barra_filtros_port_planej",
            className="filtros-sticky",
            style={**card_shell_style, "padding": "14px 16px", "marginBottom": "14px"},
            children=[
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-start",
                    },
                    children=[
                        # N°/ANO da Portaria (digitação)
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("N°/Ano da Portaria"),
                                dcc.Input(
                                    id="filtro_numero_ano_planej",
                                    type="text",
                                    placeholder="Digite parte do número/ano",
                                    style={"width": "100%", "marginBottom": "6px"},
                                ),
                            ],
                        ),
                        # Setor de Origem
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Setor de Origem"),
                                dcc.Dropdown(
                                    id="filtro_setor_dropdown_planej",
                                    placeholder="Selecione um setor...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Servidor
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Servidores"),
                                dcc.Dropdown(
                                    id="filtro_servidor_dropdown_planej",
                                    placeholder="Selecione um servidor...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Tipo
                        html.Div(
                            style={"minWidth": "220px", "flex": "0 0 320px"},
                            children=[
                                html.Label("Tipo"),
                                dcc.Dropdown(
                                    id="filtro_tipo_planej",
                                    placeholder="Selecione um tipo...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    style={"marginTop": "4px", "display": "flex", "flexWrap": "wrap", "gap": "10px", "alignItems": "center"},
                    children=[
                        html.Button(
                            "Limpar filtros",
                            id="btn_limpar_filtros_port_planej",
                            n_clicks=0,
                            style=botao_limpar_style,
                        ),
                        html.Button(
                            "Atualizar Dados",
                            id="btn_reload_port_planej",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        html.Button(
                            "Baixar Relatório PDF",
                            id="btn_download_relatorio_port_planej",
                            n_clicks=0,
                            style=botao_pdf_style,
                        ),
                        dcc.Download(id="download_relatorio_port_planej"),
                        html.Div(
                            id="info-atualizacao-port-planej",
                            style={
                                "fontSize": "12px",
                                "color": "#334155",
                                "backgroundColor": "#f8fafc",
                                "border": "1px solid #e6ebf2",
                                "borderRadius": "999px",
                                "padding": "8px 12px",
                            },
                        ),
                    ],
                ),
            ],
        ),
        # Texto de orientação
        html.Div(
            style={
                "marginTop": "15px",
                "marginBottom": "15px",
                "textAlign": "center",
                "color": "#b30000",
                "fontSize": "14px",
                "whiteSpace": "normal",
            },
            children=[
                html.Span(
                    "Portarias válidas para composição das Equipes de Planejamento da Contratação (inclusive TI)",
                    style={"fontWeight": "bold"},
                ),
            ],
        ),
        # Tabela
        html.Div(
            style={**card_shell_style, "padding": "16px"},
            children=[
                dash_table.DataTable(
            id="tabela_portarias_planej",
            columns=[
                {"name": "Data", "id": "Data"},
                {"name": "N°/ANO da Portaria", "id": "N°/ANO da Portaria"},
                {"name": "Setor de Origem", "id": "Setor de Origem"},
                {"name": "Servidores", "id": "Servidores"},
                {"name": "TIPO", "id": "TIPO"},
                {"name": "Link", "id": "Link_markdown", "presentation": "markdown"},
            ],
            data=[],
            row_selectable=False,
            cell_selectable=False,
            style_table={
                "overflowX": "auto",
                "overflowY": "auto",
                "height": "calc(100vh - 220px)",
                "minHeight": "300px",
                "position": "relative",
            },
            style_cell={
                "textAlign": "center",
                "padding": "10px 8px",
                "fontSize": "12px",
                "minWidth": "80px",
                "maxWidth": "260px",
                "whiteSpace": "normal",
                "lineHeight": "1.35",
                "border": "1px solid #e4e8ef",
            },
            style_header={
                "fontWeight": "bold",
                "backgroundColor": "#0b2b57",
                "color": "white",
                "textAlign": "center",
                "position": "sticky",
                "top": 0,
                "zIndex": 5,
            },
            style_data={"color": "black", "backgroundColor": "white"},
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "rgb(240, 240, 240)"},
            ],
            style_cell_conditional=[
                {"if": {"column_id": "Link_markdown"}, "textAlign": "center"},
            ],
            sort_action="custom",
            sort_mode="single",
            sort_by=[],
            css=datatable_links_css,
        ),
            ],
        ),
        dcc.Store(id="store-reload-port-planej"),
        dcc.Interval(id="interval-reload-port-planej", interval=60 * 60 * 1000, n_intervals=0),  # 1h
        dcc.Store(id="store_dados_port_planej"),
    ]
)

# --------------------------------------------------
# Callback: abrir página / interval / botão (recarrega cache + popula opções)
# --------------------------------------------------
@dash.callback(
    Output("store-reload-port-planej", "data"),
    Output("info-atualizacao-port-planej", "children"),
    Output("filtro_setor_dropdown_planej", "options"),
    Output("filtro_servidor_dropdown_planej", "options"),
    Output("filtro_tipo_planej", "options"),
    Input("url", "pathname"),
    Input("interval-reload-port-planej", "n_intervals"),
    Input("btn_reload_port_planej", "n_clicks"),
)
def carregar_ao_abrir_interval_ou_recarregar(pathname, _n_intervals, n_clicks):
    if pathname != "/portarias_planejamento":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    df, status = get_df_portarias(force=force)

    # opções base (sem filtros)
    op_setor = _opcoes_dropdown(df, "Setor de Origem")
    op_servidor = [{"label": s, "value": s} for s in _servidores_unicos_do_subset(df)]
    op_tipo = _opcoes_dropdown(df, "TIPO")

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    return {"ts": datetime.now().isoformat()}, msg, op_setor, op_servidor, op_tipo


# --------------------------------------------------
# Callback: aplicar filtros + link clicável (máscara única)
# --------------------------------------------------
@dash.callback(
    Output("tabela_portarias_planej", "data"),
    Output("store_dados_port_planej", "data"),
    Input("store-reload-port-planej", "data"),
    Input("filtro_numero_ano_planej", "value"),
    Input("filtro_setor_dropdown_planej", "value"),
    Input("filtro_servidor_dropdown_planej", "value"),
    Input("filtro_tipo_planej", "value"),
    Input("tabela_portarias_planej", "sort_by"),
)
def atualizar_tabela_portarias_planej(_reload, numero_ano_texto, setor_drop, servidor_drop, tipo_sel, sort_by):
    """
    Aplica todos os filtros em um único dataframe base (cache),
    usando uma máscara booleana combinada. A ordem dos filtros não importa.
    """
    df_base, _ = get_df_portarias(force=False)
    dff = df_base.copy() if df_base is not None else pd.DataFrame()

    if dff.empty:
        return [], []

    mask = pd.Series(True, index=dff.index)

    # Tipo
    if tipo_sel:
        mask &= dff["TIPO"] == tipo_sel

    # Nº/ANO da Portaria (contains, case-insensitive)
    if numero_ano_texto and str(numero_ano_texto).strip():
        termo = str(numero_ano_texto).strip().lower()
        mask &= (
            dff["N°/ANO da Portaria"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    # Setor de Origem (igualdade)
    if setor_drop:
        mask &= dff["Setor de Origem"] == setor_drop

    # Servidor dropdown (contains)
    if servidor_drop:
        termo = str(servidor_drop).strip().lower()
        mask &= (
            dff["Servidores"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    dff = dff[mask].copy()

    # Garante apenas linhas com link válido
    dff = dff[
        dff[NOME_COL_LINK_ORIGINAL]
        .astype(str)
        .str.strip()
        .str.startswith("http")
    ]

    dff_display = dff.copy()

    def formatar_link(url):
        if isinstance(url, str) and url.strip():
            return f"[Abrir]({url.strip()})"
        return ""

    dff_display["Link_markdown"] = dff_display[NOME_COL_LINK_ORIGINAL].apply(formatar_link)

    if sort_by:
        col = sort_by[0]["column_id"]
        ascending = sort_by[0]["direction"] == "asc"

        if col == "Data":
            dff_display = dff_display.sort_values(
                by="Data_dt",
                ascending=ascending,
                na_position="last",
            )
        elif col == "N°/ANO da Portaria":
            dff_display = dff_display.sort_values(
                by=["_portaria_ano", "_portaria_num"],
                ascending=[ascending, ascending],
                na_position="last",
            )
        else:
            dff_display = dff_display.sort_values(
                by=col,
                ascending=ascending,
                na_position="last",
            )
    else:
        dff_display = dff_display.sort_values(
            by=["Data_dt", "_portaria_ano", "_portaria_num"],
            ascending=[False, False, False],
            na_position="last",
        )

    cols_tabela = [
        "Data",
        "N°/ANO da Portaria",
        "Setor de Origem",
        "Servidores",
        "TIPO",
        "Link_markdown",
    ]

    for c in cols_tabela:
        if c not in dff_display.columns:
            dff_display[c] = ""

    return dff_display[cols_tabela].to_dict("records"), dff.to_dict("records")


# --------------------------------------------------
# Callback: filtros em cascata (ordem-invariante)
# --------------------------------------------------
@dash.callback(
    Output("filtro_setor_dropdown_planej", "options", allow_duplicate=True),
    Output("filtro_servidor_dropdown_planej", "options", allow_duplicate=True),
    Output("filtro_tipo_planej", "options", allow_duplicate=True),
    Input("store-reload-port-planej", "data"),
    Input("filtro_numero_ano_planej", "value"),
    Input("filtro_setor_dropdown_planej", "value"),
    Input("filtro_servidor_dropdown_planej", "value"),
    Input("filtro_tipo_planej", "value"),
    prevent_initial_call=True,
)
def atualizar_opcoes_filtros_portarias(_reload, numero_ano_texto, setor_drop, servidor_drop, tipo_sel):
    """
    Atualiza as opções de Setor, Servidores e Tipo em cascata,
    usando um único filtro global. A ordem dos filtros não importa.
    """
    df_base, _ = get_df_portarias(force=False)
    dff = df_base.copy() if df_base is not None else pd.DataFrame()

    if dff.empty:
        return [], [], []

    mask = pd.Series(True, index=dff.index)

    # Tipo
    if tipo_sel:
        mask &= dff["TIPO"] == tipo_sel

    # Nº/ANO da Portaria
    if numero_ano_texto and str(numero_ano_texto).strip():
        termo = str(numero_ano_texto).strip().lower()
        mask &= (
            dff["N°/ANO da Portaria"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    # Setor de Origem
    if setor_drop:
        mask &= dff["Setor de Origem"] == setor_drop

    # Servidor dropdown
    if servidor_drop:
        termo = str(servidor_drop).strip().lower()
        mask &= (
            dff["Servidores"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    dff = dff[mask].copy()

    op_setor = _opcoes_dropdown(dff, "Setor de Origem")
    op_servidor = [{"label": s, "value": s} for s in _servidores_unicos_do_subset(dff)]
    op_tipo = _opcoes_dropdown(dff, "TIPO")

    return op_setor, op_servidor, op_tipo


# --------------------------------------------------
# Callback: limpar filtros
# --------------------------------------------------
@dash.callback(
    Output("filtro_numero_ano_planej", "value"),
    Output("filtro_setor_dropdown_planej", "value"),
    Output("filtro_servidor_dropdown_planej", "value"),
    Output("filtro_tipo_planej", "value"),
    Input("btn_limpar_filtros_port_planej", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_port_planej(_n):
    return None, None, None, None


# --------------------------------------------------
# Estilos para o PDF (planejamento)
# --------------------------------------------------
wrap_style_data = ParagraphStyle(
    name="wrap_planej_data",
    fontSize=7,
    leading=8,
    spaceAfter=2,
    wordWrap="CJK",
    alignment=TA_CENTER,
)

wrap_style_header = ParagraphStyle(
    name="wrap_planej_header",
    fontSize=7,
    leading=8,
    alignment=TA_CENTER,
    textColor=colors.white,
)


def wrap_data(text):
    return Paragraph(str(text), wrap_style_data)


def wrap_header(text):
    return Paragraph(str(text), wrap_style_header)


# --------------------------------------------------
# Callback: gerar PDF
# --------------------------------------------------
@dash.callback(
    Output("download_relatorio_port_planej", "data"),
    Input("btn_download_relatorio_port_planej", "n_clicks"),
    State("store_dados_port_planej", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_port_planej(n, dados_port):
    if not n or not dados_port:
        return None

    df = pd.DataFrame(dados_port)

    buffer = BytesIO()
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.2 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # Data / Hora (topo direito)
    tz_brasilia = timezone("America/Sao_Paulo")
    data_hora = datetime.now(tz_brasilia).strftime("%d/%m/%Y %H:%M:%S")

    story.append(
        Table(
            [[Paragraph(
                data_hora,
                ParagraphStyle(
                    "data_topo",
                    fontSize=9,
                    alignment=TA_RIGHT,
                    textColor="#333333",
                ),
            )]],
            colWidths=[pagesize[0] - 0.6 * inch],
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    # Cabeçalho: Logo esq | Instituição | Logo dir
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
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )

    story.append(cabecalho)
    story.append(Spacer(1, 0.25 * inch))

    # Título
    titulo = Paragraph(
        "Portarias vigentes – Equipes de Planejamento da Contratação (inclusive TI)<br/>",
        ParagraphStyle(
            "titulo",
            alignment=TA_CENTER,
            fontSize=10,
            leading=14,
            textColor=colors.black,
        ),
    )

    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Total de registros: {len(df)}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    # Preparação da tabela de dados
    cols = ["Data", "N°/ANO da Portaria", "Setor de Origem", "Servidores", "TIPO"]

    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df_pdf = df.copy()

    header = [wrap_header(c) for c in cols]
    table_data = [header]
    for _, row in df_pdf[cols].iterrows():
        table_data.append([wrap_data(row[c]) for c in cols])

    # Larguras das colunas (ajustadas para landscape)
    page_width = pagesize[0] - 0.6 * inch
    col_widths = [
        0.9 * inch,               # Data
        1.2 * inch,               # N°/ANO da Portaria
        1.2 * inch,               # Setor de Origem
        3.0 * inch,               # Servidores
        page_width - (0.9 + 1.2 + 1.2 + 3.0) * inch,  # TIPO
    ]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]

    tbl.setStyle(TableStyle(table_styles))
    story.append(tbl)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"relatorio_portarias_planejamento_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

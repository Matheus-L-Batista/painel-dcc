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

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/portarias_agentedecompras",
    name="Portarias – Agente de Compras",
    title="Portarias – Agente de Compras",
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
NOME_COL_LINK_ORIGINAL = "Link do documento\nAgentes de Compras e\nContratos tipo empenho"

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

    cols_serv = [str(i) for i in range(1, 16) if str(i) in df.columns]

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

    tipos_validos = ["AGENTES DE COMPRAS", "CONTRATOS TIPO EMPENHO"]
    df = df[df["TIPO"].isin(tipos_validos)]

    if NOME_COL_LINK_ORIGINAL not in df.columns:
        df[NOME_COL_LINK_ORIGINAL] = ""

    df = df[
        df[NOME_COL_LINK_ORIGINAL]
        .astype(str)
        .str.strip()
        .str.startswith("http")
    ]

    df["Data_dt"] = pd.to_datetime(df["Data"], dayfirst=True, errors="coerce")

    def split_portaria(valor):
        try:
            num, ano = str(valor).strip().split("/")
            return int(ano), int(num)
        except Exception:
            return (0, 0)

    df["_portaria_ano"] = df["N°/ANO da Portaria"].apply(lambda x: split_portaria(x)[0])
    df["_portaria_num"] = df["N°/ANO da Portaria"].apply(lambda x: split_portaria(x)[1])

    # Ordenação padrão: data mais recente primeiro e, em empate, ano/número da portaria
    df = df.sort_values(
        by=["Data_dt", "_portaria_ano", "_portaria_num"],
        ascending=[False, False, False],
        na_position="last",
    )

    return df


# --------------------------------------------------
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h
_CACHE_LOCK = threading.Lock()
_DF_CACHE = None
_DF_CACHE_AT = None

_CACHE_DIR = os.path.join(
    os.path.dirname(__file__) if "__file__" in globals() else os.getcwd(),
    ".cache_agentedecompras",
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "df_agentedecompras.pkl")
_CACHE_META = os.path.join(_CACHE_DIR, "meta.pkl")


def _now_sp():
    return datetime.now(timezone("America/Sao_Paulo"))


def _fmt_dt(dt):
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
}

botao_limpar_style = {
    "backgroundColor": "#A2AAAD",
    "color": "black",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
}

botao_pdf_style = {
    "backgroundColor": "#DA291C",
    "color": "white",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
}

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    children=[
        dcc.Location(id="url"),
        html.Div(
            id="barra_filtros_port",
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
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("N°/Ano da Portaria"),
                                dcc.Input(
                                    id="filtro_numero_ano",
                                    type="text",
                                    placeholder="Digite parte do número/ano",
                                    style={"width": "100%", "marginBottom": "6px"},
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Setor de Origem"),
                                dcc.Dropdown(
                                    id="filtro_setor_dropdown",
                                    placeholder="Selecione um setor...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Servidores"),
                                dcc.Dropdown(
                                    id="filtro_servidor_dropdown",
                                    placeholder="Selecione um servidor...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "0 0 320px"},
                            children=[
                                html.Label("Tipo"),
                                dcc.Dropdown(
                                    id="filtro_tipo",
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
                            id="btn_limpar_filtros_port",
                            n_clicks=0,
                            style=botao_limpar_style,
                        ),
                        html.Button(
                            "Atualizar Dados",
                            id="btn_reload_port_agente",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        html.Button(
                            "Baixar Relatório PDF",
                            id="btn_download_relatorio_port",
                            n_clicks=0,
                            style=botao_pdf_style,
                        ),
                        dcc.Download(id="download_relatorio_port"),
                        html.Div(
                            id="info-atualizacao-port-agente",
                            style={"fontSize": "12px", "color": "#333"},
                        ),
                    ],
                ),
            ],
        ),
        # Texto
        html.Div(
            style={
                "marginTop": "15px",
                "marginBottom": "15px",
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "baseline",
                "gap": "5px",
                "color": "#b30000",
                "fontSize": "14px",
                "whiteSpace": "nowrap",
            },
            children=[
                html.Span(
                    "Portarias válidas para vinculação dos servidores às notas de empenho",
                    style={"fontWeight": "bold"},
                ),
                html.Span(
                    "(fase que antecede o lançamento dos ",
                    style={"fontSize": "15px"},
                ),
                html.Span(
                    "Instrumentos de Cobrança",
                    style={
                        "fontSize": "15px",
                        "textDecoration": "underline",
                    },
                ),
                html.Span(
                    " no sistema contratos.gov.br)",
                    style={"fontSize": "15px"},
                ),
            ],
        ),
        dash_table.DataTable(
            id="tabela_portarias",
            columns=[
                {"name": "Data", "id": "Data"},
                {"name": "N°/ANO da Portaria", "id": "N°/ANO da Portaria"},
                {"name": "Setor de Origem", "id": "Setor de Origem"},
                {"name": "Servidores", "id": "Servidores"},
                {"name": "TIPO", "id": "TIPO"},
                {"name": "Link", "id": "Link_markdown", "presentation": "markdown"},
            ],
            data=[],
            sort_action="custom",
            sort_mode="single",
            sort_by=[],
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
                "padding": "6px",
                "fontSize": "12px",
                "minWidth": "80px",
                "maxWidth": "260px",
                "whiteSpace": "normal",
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
                {"if": {"row_index": "odd"}, "backgroundColor": "#f0f0f0"},
                {"if": {"row_index": "even"}, "backgroundColor": "white"},
            ],
            style_cell_conditional=[
                {"if": {"column_id": "Link_markdown"}, "textAlign": "center"},
            ],
            css=[dict(selector="p", rule="margin: 0; text-align: center;")],
        ),
        dcc.Store(id="store-reload-port-agente"),
        dcc.Interval(id="interval-reload-port-agente", interval=60 * 60 * 1000, n_intervals=0),  # 1h
        dcc.Store(id="store_dados_port"),
    ]
)

# --------------------------------------------------
# Callback: abrir página / interval / botão (recarrega cache + popula opções)
# --------------------------------------------------
@dash.callback(
    Output("store-reload-port-agente", "data"),
    Output("info-atualizacao-port-agente", "children"),
    Output("filtro_setor_dropdown", "options"),
    Output("filtro_servidor_dropdown", "options"),
    Output("filtro_tipo", "options"),
    Input("url", "pathname"),
    Input("interval-reload-port-agente", "n_intervals"),
    Input("btn_reload_port_agente", "n_clicks"),
)
def carregar_ao_abrir_interval_ou_recarregar(pathname, _n_intervals, n_clicks):
    if pathname != "/portarias_agentedecompras":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    df, status = get_df_portarias(force=force)

    op_setor = _opcoes_dropdown(df, "Setor de Origem")
    op_servidor = [{"label": s, "value": s} for s in _servidores_unicos_do_subset(df)]
    op_tipo = _opcoes_dropdown(df, "TIPO")

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    return {"ts": datetime.now().isoformat()}, msg, op_setor, op_servidor, op_tipo


# --------------------------------------------------
# Callback: aplicar filtros + link clicável (máscara única)
# --------------------------------------------------
@dash.callback(
    Output("tabela_portarias", "data"),
    Output("store_dados_port", "data"),
    Input("store-reload-port-agente", "data"),
    Input("filtro_numero_ano", "value"),
    Input("filtro_setor_dropdown", "value"),
    Input("filtro_servidor_dropdown", "value"),
    Input("filtro_tipo", "value"),
    Input("tabela_portarias", "sort_by"),
)
def atualizar_tabela_portarias(_reload, numero_ano_texto, setor_drop, servidor_drop, tipo_sel, sort_by):
    dff_base, _ = get_df_portarias(force=False)
    dff = dff_base.copy() if dff_base is not None else pd.DataFrame()

    if dff.empty:
        return [], []

    mask = pd.Series(True, index=dff.index)

    if tipo_sel:
        mask &= dff["TIPO"] == tipo_sel

    if numero_ano_texto and str(numero_ano_texto).strip():
        termo = str(numero_ano_texto).strip().lower()
        mask &= (
            dff["N°/ANO da Portaria"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    if setor_drop:
        mask &= dff["Setor de Origem"] == setor_drop

    if servidor_drop:
        termo = str(servidor_drop).strip().lower()
        mask &= (
            dff["Servidores"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    dff = dff[mask].copy()

    dff = dff[
        dff[NOME_COL_LINK_ORIGINAL]
        .astype(str)
        .str.strip()
        .str.startswith("http")
    ]

    dff_display = dff.copy()

    def formatar_link(url):
        if isinstance(url, str) and url.strip():
            return f"[Link]({url.strip()})"
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

    cols_tabela = ["Data", "N°/ANO da Portaria", "Setor de Origem", "Servidores", "TIPO", "Link_markdown"]

    for c in cols_tabela:
        if c not in dff_display.columns:
            dff_display[c] = ""

    return dff_display[cols_tabela].to_dict("records"), dff.to_dict("records")


# --------------------------------------------------
# Callback: filtros em cascata (ordem-invariante)
# --------------------------------------------------
@dash.callback(
    Output("filtro_setor_dropdown", "options", allow_duplicate=True),
    Output("filtro_servidor_dropdown", "options", allow_duplicate=True),
    Output("filtro_tipo", "options", allow_duplicate=True),
    Input("store-reload-port-agente", "data"),
    Input("filtro_numero_ano", "value"),
    Input("filtro_setor_dropdown", "value"),
    Input("filtro_servidor_dropdown", "value"),
    Input("filtro_tipo", "value"),
    prevent_initial_call=True,
)
def atualizar_opcoes_filtros_portarias(_reload, numero_ano_texto, setor_drop, servidor_drop, tipo_sel):
    dff_base, _ = get_df_portarias(force=False)
    dff = dff_base.copy() if dff_base is not None else pd.DataFrame()

    if dff.empty:
        return [], [], []

    mask = pd.Series(True, index=dff.index)

    if tipo_sel:
        mask &= dff["TIPO"] == tipo_sel

    if numero_ano_texto and str(numero_ano_texto).strip():
        termo = str(numero_ano_texto).strip().lower()
        mask &= (
            dff["N°/ANO da Portaria"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        )

    if setor_drop:
        mask &= dff["Setor de Origem"] == setor_drop

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
    Output("filtro_numero_ano", "value"),
    Output("filtro_setor_dropdown", "value"),
    Output("filtro_servidor_dropdown", "value"),
    Output("filtro_tipo", "value"),
    Input("btn_limpar_filtros_port", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_port(_n):
    return None, None, None, None


# --------------------------------------------------
# Estilos para o PDF (portarias)
# --------------------------------------------------
wrap_style_data = ParagraphStyle(
    name="wrap_portarias_data",
    fontSize=7,
    leading=8,
    spaceAfter=2,
    wordWrap="CJK",
    alignment=TA_CENTER,
)

wrap_style_header = ParagraphStyle(
    name="wrap_portarias_header",
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
# Callback: gerar PDF de portarias
# --------------------------------------------------
@dash.callback(
    Output("download_relatorio_port", "data"),
    Input("btn_download_relatorio_port", "n_clicks"),
    State("store_dados_port", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_port(n, dados_port):
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
        ParagraphStyle("instituicao", alignment=TA_CENTER, leading=16),
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

    titulo = Paragraph(
        "Portarias vigentes de Agentes de Compras e Contratos tipo empenho<br/>",
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

    cols = ["Data", "N°/ANO da Portaria", "Setor de Origem", "Servidores", "TIPO"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df_pdf = df.copy()
    header = [wrap_header(c) for c in cols]
    table_data = [header]
    for _, row in df_pdf[cols].iterrows():
        table_data.append([wrap_data(row[c]) for c in cols])

    col_widths = [
        0.9 * inch,   # Data
        1.2 * inch,   # N°/ANO da Portaria
        1.6 * inch,   # Setor de Origem
        3.0 * inch,   # Servidores
        1.4 * inch,   # TIPO
    ]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
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
        )
    )

    story.append(tbl)
    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"relatorio_portarias_agentedecompras_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

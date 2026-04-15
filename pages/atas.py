import dash
from dash import html, dcc, dash_table, callback
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
import pandas as pd
from datetime import datetime, timedelta
import os
import threading
import pickle

from utils.runtime import format_datetime_sp, get_cache_dir, now_sp

# --------------------------------------------------
# Registro da pagina
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/atas",
    name="Atas",
    title="Atas",
)

# --------------------------------------------------
# Planilha (aba unica por GID)
# --------------------------------------------------
SHEET_ID = "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog"
GID_CONTROLE = "1976446622"

URL_CONTROLE_ATAS = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
    f"?format=csv&gid={GID_CONTROLE}"
)


# --------------------------------------------------
# Carga e tratamento
# --------------------------------------------------
def carregar_base_controle() -> pd.DataFrame:
    df = pd.read_csv(URL_CONTROLE_ATAS, header=1)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def carregar_atas_vigentes(df_base: pd.DataFrame) -> pd.DataFrame:
    df = df_base.copy()

    if df.shape[1] < 5:
        return pd.DataFrame(columns=["Numero", "Ata Vigente", "Data Inicial", "Data de Termino", "Link_markdown"])

    df = df.iloc[:, 0:5].copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={"ATAS VIGENTES": "Ata Vigente"})
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]

    if "Data de Término" in df.columns:
        df["Data de Término_dt"] = pd.to_datetime(df["Data de Término"], dayfirst=True, errors="coerce")
        hoje = datetime.now().date()
        df = df[df["Data de Término_dt"].notna()]
        df = df[df["Data de Término_dt"].dt.date >= hoje]
        df["Data de Término"] = df["Data de Término_dt"].dt.strftime("%d/%m/%Y")

    def formatar_link(url) -> str:
        url = str(url).strip()
        return f"[Abrir]({url})" if url.startswith("http") else ""

    if "Link" in df.columns:
        df["Link_markdown"] = df["Link"].apply(formatar_link)
    else:
        df["Link_markdown"] = ""

    cols = ["Número", "Ata Vigente", "Data Inicial", "Data de Término", "Link_markdown"]
    return df[[c for c in cols if c in df.columns]]


def carregar_atas_andamento(df_base: pd.DataFrame) -> pd.DataFrame:
    df = df_base.copy()

    if df.shape[1] < 9:
        return pd.DataFrame(columns=["Atas em Andamento", "Situação", "Previsão para estar disponível"])

    df = df.iloc[:, 6:9].copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]
    df = df.rename(
        columns={
            "ATAS EM ANDAMENTO": "Atas em Andamento",
            "Situação ": "Situação",
            "Previsão para estar disponível": "Previsão para estar disponível",
        }
    )

    cols = ["Atas em Andamento", "Situação", "Previsão para estar disponível"]
    return df[[c for c in cols if c in df.columns]]


# --------------------------------------------------
# Cache
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60
_CACHE_LOCK = threading.Lock()
_CACHE_OBJ = None
_CACHE_AT = None

_CACHE_DIR = os.path.join(str(get_cache_dir("atas")))
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "atas_cache.pkl")
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
        obj = pd.read_pickle(_CACHE_FILE)
        return obj, cached_at_dt
    except Exception:
        return None, None


def _save_disk_cache(obj, cached_at: datetime):
    try:
        pd.to_pickle(obj, _CACHE_FILE)
        with open(_CACHE_META, "wb") as f:
            pickle.dump({"cached_at": cached_at.isoformat()}, f)
    except Exception:
        pass


def get_atas_cache(force: bool = False):
    global _CACHE_OBJ, _CACHE_AT

    now_naive = datetime.now()
    stale = (
        _CACHE_OBJ is None
        or _CACHE_AT is None
        or (now_naive - _CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
    )

    if force or stale:
        with _CACHE_LOCK:
            now2 = datetime.now()
            stale2 = (
                _CACHE_OBJ is None
                or _CACHE_AT is None
                or (now2 - _CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
            )

            if (not force) and stale2:
                disk_obj, at_disk = _load_disk_cache()
                if disk_obj is not None and at_disk is not None:
                    _CACHE_OBJ = disk_obj
                    _CACHE_AT = now2
                    return _CACHE_OBJ, f"Dados carregados do cache em disco ({_fmt_dt(at_disk)})."

            if force or stale2:
                df_base = carregar_base_controle()
                df_vig = carregar_atas_vigentes(df_base)
                df_and = carregar_atas_andamento(df_base)
                _CACHE_OBJ = {"vig": df_vig, "and": df_and}
                _CACHE_AT = now2
                _save_disk_cache(_CACHE_OBJ, now2)
                return _CACHE_OBJ, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())})."

    return _CACHE_OBJ, f"Dados em cache (memória) - verificado em {_fmt_dt(_now_sp())}."


# --------------------------------------------------
# Estilos
# --------------------------------------------------
header_style = {
    "fontWeight": "bold",
    "backgroundColor": "#0b2b57",
    "color": "white",
    "position": "sticky",
    "top": 0,
    "zIndex": 1,
    "padding": "12px 10px",
    "fontSize": "12px",
    "border": "none",
}

header_style_andamento = {
    **header_style,
    "backgroundColor": "#b3261e",
}

cell_style = {
    "textAlign": "center",
    "padding": "10px 12px",
    "fontSize": "12px",
    "whiteSpace": "normal",
    "height": "auto",
    "lineHeight": "1.35",
    "border": "1px solid #e4e8ef",
}

zebra_style = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
    {"if": {"state": "active"}, "backgroundColor": "#eef4ff", "border": "1px solid #9bb8ea"},
]

datatable_links_css = [
    {"selector": "p", "rule": "margin: 0; text-align: center;"},
    {
        "selector": "td a",
        "rule": "display:inline-block; padding:4px 10px; border-radius:999px; background:#eaf2ff; color:#0b2b57; font-weight:600; text-decoration:none;",
    },
]

botao_style = {
    "backgroundColor": "#0b2b57",
    "color": "white",
    "padding": "10px 18px",
    "border": "none",
    "borderRadius": "10px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
    "boxShadow": "0 4px 12px rgba(11, 43, 87, 0.18)",
}

card_style = {
    "backgroundColor": "white",
    "border": "1px solid #e6ebf2",
    "borderRadius": "14px",
    "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
    "padding": "16px",
}

section_title_style = {
    "textAlign": "center",
    "margin": "0 0 14px 0",
    "color": "#0b2b57",
    "fontWeight": "700",
}


# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style={"padding": "14px", "backgroundColor": "#f6f8fb", "minHeight": "100vh"},
    children=[
        dcc.Location(id="url"),
        dcc.Store(id="store-reload-atas"),
        dcc.Interval(id="interval-reload-atas", interval=60 * 60 * 1000, n_intervals=0),
        html.Div(
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
                "gap": "14px",
                "flexWrap": "wrap",
                "marginBottom": "14px",
                "padding": "14px 16px",
                "backgroundColor": "white",
                "border": "1px solid #e6ebf2",
                "borderRadius": "14px",
                "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
            },
            children=[
                html.Div(
                    children=[
                        html.Div("Controle de Atas", style={"fontSize": "20px", "fontWeight": "700", "color": "#0b2b57"}),
                        html.Div("Acompanhamento das atas vigentes e em andamento", style={"fontSize": "12px", "color": "#5f6b7a"}),
                    ]
                ),
                html.Div(
                    style={"display": "flex", "alignItems": "center", "gap": "12px", "flexWrap": "wrap"},
                    children=[
                        html.Button("Atualizar Dados", id="btn_reload_atas", n_clicks=0, style=botao_style),
                        html.Div(
                            id="info-atualizacao-atas",
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
        html.Div(id="atas_erro", style={"color": "crimson", "textAlign": "center", "marginBottom": "10px"}),
        html.Div(
            style={**card_style, "marginBottom": "18px"},
            children=[
                html.H3("Atas Vigentes", style=section_title_style),
                dash_table.DataTable(
                    id="tabela_atas_vigentes",
                    columns=[
                        {"name": "Número", "id": "Número"},
                        {"name": "Ata Vigente", "id": "Ata Vigente"},
                        {"name": "Data Inicial", "id": "Data Inicial"},
                        {"name": "Data de Término", "id": "Data de Término"},
                        {"name": "Link", "id": "Link_markdown", "presentation": "markdown"},
                    ],
                    data=[],
                    style_table={
                        "maxHeight": "500px",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "borderRadius": "10px",
                        "overflow": "hidden",
                    },
                    style_cell=cell_style,
                    style_header=header_style,
                    style_data_conditional=zebra_style,
                    style_cell_conditional=[
                        {"if": {"column_id": "Número"}, "width": "140px", "minWidth": "140px", "maxWidth": "140px"},
                        {"if": {"column_id": "Ata Vigente"}, "textAlign": "left"},
                        {"if": {"column_id": "Data Inicial"}, "width": "165px", "minWidth": "165px", "maxWidth": "165px"},
                        {"if": {"column_id": "Data de Término"}, "width": "165px", "minWidth": "165px", "maxWidth": "165px"},
                        {"if": {"column_id": "Link_markdown"}, "width": "90px", "minWidth": "90px", "maxWidth": "90px"},
                    ],
                    css=datatable_links_css,
                ),
            ],
        ),
        html.Div(
            style=card_style,
            children=[
                html.H3("Atas em Andamento", style=section_title_style),
                dash_table.DataTable(
                    id="tabela_atas_andamento",
                    columns=[
                        {"name": "Atas em Andamento", "id": "Atas em Andamento"},
                        {"name": "Situação", "id": "Situação"},
                        {"name": "Previsão para estar disponível", "id": "Previsão para estar disponível"},
                    ],
                    data=[],
                    style_table={
                        "maxHeight": "260px",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "borderRadius": "10px",
                        "overflow": "hidden",
                    },
                    style_cell=cell_style,
                    style_header=header_style_andamento,
                    style_data_conditional=zebra_style,
                    style_cell_conditional=[
                        {"if": {"column_id": "Atas em Andamento"}, "textAlign": "left"},
                        {"if": {"column_id": "Previsão para estar disponível"}, "width": "240px", "minWidth": "240px", "maxWidth": "240px"},
                    ],
                ),
            ],
        ),
    ],
)


# --------------------------------------------------
# Callbacks
# --------------------------------------------------
@callback(
    Output("store-reload-atas", "data"),
    Output("info-atualizacao-atas", "children"),
    Input("url", "pathname"),
    Input("interval-reload-atas", "n_intervals"),
    Input("btn_reload_atas", "n_clicks"),
)
def controlar_reload(pathname, _n_intervals, n_clicks):
    if pathname != "/atas":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    _, status = get_atas_cache(force=force)
    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    return {"ts": datetime.now().isoformat()}, msg


@callback(
    Output("tabela_atas_vigentes", "data"),
    Output("tabela_atas_andamento", "data"),
    Output("atas_erro", "children"),
    Input("store-reload-atas", "data"),
)
def atualizar_tabelas(_reload):
    try:
        cache, _ = get_atas_cache(force=False)
        if not cache:
            return [], [], "Sem dados disponíveis no momento."
        df_vig = cache.get("vig", pd.DataFrame())
        df_and = cache.get("and", pd.DataFrame())
        return df_vig.to_dict("records"), df_and.to_dict("records"), ""
    except Exception as e:
        msg = f"Erro ao carregar dados da planilha: {e}"
        print(f"[ATAS] {msg}")
        return [], [], msg

import dash
from dash import html, dcc, dash_table, callback
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
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
    path="/atas",
    name="Atas",
    title="Atas",
)

# --------------------------------------------------
# Planilha (aba única por GID) - MAIS CONFIÁVEL
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
    # Cabeçalho começa na 2ª linha
    df = pd.read_csv(URL_CONTROLE_ATAS, header=1)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def carregar_atas_vigentes(df_base: pd.DataFrame) -> pd.DataFrame:
    df = df_base.copy()

    # A:E => índices 0..4 (5 colunas)
    if df.shape[1] < 5:
        return pd.DataFrame(columns=["Número", "Ata Vigente", "Data Inicial", "Data de Término", "Link_markdown"])

    df = df.iloc[:, 0:5].copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Padroniza nome
    df = df.rename(columns={"ATAS VIGENTES": "Ata Vigente"})

    # Remove colunas Unnamed (caso existam dentro do recorte)
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]

    # Filtra somente vigentes
    if "Data de Término" in df.columns:
        df["Data de Término_dt"] = pd.to_datetime(df["Data de Término"], dayfirst=True, errors="coerce")
        hoje = datetime.now().date()
        df = df[df["Data de Término_dt"].notna()]
        df = df[df["Data de Término_dt"].dt.date >= hoje]
        df["Data de Término"] = df["Data de Término_dt"].dt.strftime("%d/%m/%Y")

    # Link em markdown (valida URL)
    def formatar_link(url) -> str:
        url = str(url).strip()
        return f"[link]({url})" if url.startswith("http") else ""

    if "Link" in df.columns:
        df["Link_markdown"] = df["Link"].apply(formatar_link)
    else:
        df["Link_markdown"] = ""

    cols = ["Número", "Ata Vigente", "Data Inicial", "Data de Término", "Link_markdown"]
    return df[[c for c in cols if c in df.columns]]


def carregar_atas_andamento(df_base: pd.DataFrame) -> pd.DataFrame:
    df = df_base.copy()

    # G:I => índices 6..8 (9ª coluna é índice 8)
    if df.shape[1] < 9:
        return pd.DataFrame(columns=["Atas em Andamento", "Situação", "Previsão para estar disponível"])

    df = df.iloc[:, 6:9].copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Remove Unnamed do recorte
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]

    # Padroniza nomes
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
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h
_CACHE_LOCK = threading.Lock()
_CACHE_OBJ = None          # dict: {"vig": df, "and": df}
_CACHE_AT = None

_CACHE_DIR = os.path.join(
    os.path.dirname(__file__) if "__file__" in globals() else os.getcwd(),
    ".cache_atas",
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "atas_cache.pkl")
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
    """
    Retorna (cache_obj, status_msg).
    cache_obj: {"vig": df_atas_vigentes, "and": df_atas_andamento}
    """
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

    return _CACHE_OBJ, f"Dados em cache (memória) — verificado em {_fmt_dt(_now_sp())}."


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
}

cell_style = {
    "textAlign": "center",
    "padding": "6px",
    "fontSize": "12px",
    "whiteSpace": "normal",
    "height": "auto",
}

zebra_style = [{"if": {"row_index": "odd"}, "backgroundColor": "#f5f5f5"}]
datatable_links_css = [{"selector": "p", "rule": "margin: 0; text-align: center;"}]

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


# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style={"padding": "10px"},
    children=[
        dcc.Location(id="url"),
        dcc.Store(id="store-reload-atas"),
        dcc.Interval(id="interval-reload-atas", interval=60 * 60 * 1000, n_intervals=0),  # 1h

        html.Div(
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "gap": "10px",
                "flexWrap": "wrap",
                "marginBottom": "10px",
            },
            children=[
                html.Button("Atualizar Dados", id="btn_reload_atas", n_clicks=0, style=botao_style),
                html.Div(id="info-atualizacao-atas", style={"fontSize": "12px", "color": "#333"}),
            ],
        ),

        # Mostra erro de carregamento na tela (sem esconder)
        html.Div(id="atas_erro", style={"color": "crimson", "textAlign": "center", "marginBottom": "8px"}),

        html.H3("Atas Vigentes", style={"textAlign": "center"}),

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
            style_table={"maxHeight": "450px", "overflowY": "auto", "overflowX": "auto"},
            style_cell=cell_style,
            style_header=header_style,
            style_data_conditional=zebra_style,
            css=datatable_links_css,
        ),

        html.H3("Atas em Andamento", style={"marginTop": "20px", "textAlign": "center"}),

        dash_table.DataTable(
            id="tabela_atas_andamento",
            columns=[
                {"name": "Atas em Andamento", "id": "Atas em Andamento"},
                {"name": "Situação", "id": "Situação"},
                {"name": "Previsão para estar disponível", "id": "Previsão para estar disponível"},
            ],
            data=[],
            style_table={"maxHeight": "220px", "overflowY": "auto", "overflowX": "auto"},
            style_cell=cell_style,
            style_header=header_style,
            style_data_conditional=zebra_style,
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

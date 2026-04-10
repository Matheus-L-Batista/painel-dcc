import dash
from dash import html, dcc, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd

from io import BytesIO
from reportlab.lib.pagesizes import portrait, A4
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
import re

from utils.runtime import format_datetime_sp, get_cache_dir, get_default_year, now_sp


ANO_PADRAO_PCA = str(get_default_year())


dash.register_page(
    __name__,
    path="/pca",
    name="PCA",
    title="PCA",
)

URL_PCA = (
    "https://docs.google.com/spreadsheets/d/"
    "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog/"
    "gviz/tq?tqx=out:csv&sheet=PCA%20-%20BI"
)

dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
    "position": "relative",
    "zIndex": 1000,
}

button_base_style = {
    "color": "white",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "14px",
    "fontWeight": "bold",
}

button_limpar_style = {**button_base_style, "backgroundColor": "#9aa0a6", "color": "#111111"}
button_atualizar_style = {**button_base_style, "backgroundColor": "#0b2b57"}
button_pdf_style = {**button_base_style, "backgroundColor": "#d93025"}


def conv_moeda_br(v):
    if isinstance(v, str):
        v = v.strip()
        if v == "":
            return None
        v = v.replace(".", "").replace(",", ".")
        try:
            return float(v)
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def formatar_moeda(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def normalizar_item(v):
    """Normaliza Item para inteiro quando possível, sem quebrar com valores sujos."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return ""
    # tenta extrair número (ex.: '1', '1.0', ' 2 ')
    try:
        n = pd.to_numeric(s, errors="raise")
        if pd.isna(n):
            return ""
        return str(int(float(n)))
    except Exception:
        # mantém texto original (melhor do que derrubar o callback)
        return s

# --------------------------------------------------
# Carga e tratamento de dados
# --------------------------------------------------
def carregar_dados_pca():
    df = pd.read_csv(URL_PCA, header=0)
    df.columns = [c.strip() for c in df.columns]

    base_cols = [
        "Ano",
        "Área requisitante",
        "Material ou Serviço",
        "DFD",
        "Valor Total",
        "Saldo",
        "Item",
        "Código Classe / Grupo",
        "Nome Classe/Grupo",
        "Código PDM material",
        "Nome do PDM material",
        "Processo",
        "Observações",
        "Objeto",
        "SRP ou Outro Valor",
        "Valor",
    ]

    for c in base_cols:
        if c not in df.columns:
            df[c] = None

    df["Valor Total"] = df["Valor Total"].apply(conv_moeda_br)
    df["Saldo"] = df["Saldo"].apply(conv_moeda_br)

    for c in df.columns:
        if c.startswith("Valor"):
            df[c] = df[c].apply(conv_moeda_br)
        if c.startswith("SRP ou Outro Valor"):
            df[c] = df[c].apply(conv_moeda_br)

    df["Ano"] = df["Ano"].astype("string")

    for c in [
        "Área requisitante",
        "Material ou Serviço",
        "DFD",
        "Item",
        "Código Classe / Grupo",
        "Nome Classe/Grupo",
        "Nome do PDM material",
        "Processo",
        "Observações",
        "Objeto",
    ]:
        if c in df.columns:
            df[c] = df[c].astype("string")

    if "Código PDM material" in df.columns:
        df["Código PDM material"] = (
            df["Código PDM material"]
            .apply(lambda x: str(x).strip() if pd.notna(x) else "")
        )
        df["Código PDM material"] = pd.to_numeric(
            df["Código PDM material"].replace({"": None}), errors="coerce"
        ).astype("Int64")

    return df


def _build_derivados(df_pca_base: pd.DataFrame):
    # Tabela 1: Planejamento
    df_planejamento = df_pca_base.copy()
    df_planejamento["Planejado"] = df_planejamento["Valor Total"]
    df_planejamento["Executado"] = (
        df_planejamento["Planejado"] - df_planejamento["Saldo"]
    )

    # Tabela 2: Processos (normalizando colunas com sufixos .N sem forçar 1..31)
    # Identifica quais sufixos realmente existem no arquivo ('' e '.N')
    base_id_cols = [
        "Ano",
        "Área requisitante",
        "Material ou Serviço",
        "DFD",
        "Item",
        "Valor Total",
        "Saldo",
    ]
    for c in base_id_cols:
        if c not in df_pca_base.columns:
            df_pca_base[c] = None

    proc_fields = ["Processo", "Observações", "Objeto", "SRP ou Outro Valor", "Valor"]

    # Coleta sufixos existentes a partir das colunas presentes
    sufixos = set([""])
    rx = re.compile(r"^(Processo|Observações|Objeto|SRP ou Outro Valor|Valor)(\.\d+)?$")
    for col in df_pca_base.columns:
        m = rx.match(col)
        if m:
            suf = m.group(2) or ""
            sufixos.add(suf)

    # Monta tabelas apenas para sufixos existentes
    tabelas = []
    for suf in sorted(sufixos, key=lambda s: (0 if s == "" else int(s[1:]))):
        cols = base_id_cols + [f"{f}{suf}" for f in proc_fields]
        for c in cols:
            if c not in df_pca_base.columns:
                df_pca_base[c] = None

        sel = df_pca_base[cols].copy()
        ren = {f"{f}{suf}": f for f in proc_fields}
        sel = sel.rename(columns=ren)
        tabelas.append(sel)

    tabela_processos_unida = pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame(columns=base_id_cols + proc_fields)

    # Normalizações de tipo
    for c in [
        "Área requisitante",
        "Material ou Serviço",
        "DFD",
        "Item",
        "Processo",
        "Observações",
        "Objeto",
    ]:
        if c in tabela_processos_unida.columns:
            tabela_processos_unida[c] = tabela_processos_unida[c].astype("string")

    if "Valor" in tabela_processos_unida.columns:
        tabela_processos_unida["Valor"] = tabela_processos_unida["Valor"].apply(conv_moeda_br)

    return df_planejamento, tabela_processos_unida


# --------------------------------------------------
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h
_CACHE_LOCK = threading.Lock()
_CACHE = None          # dict: {"base": df, "plan": df, "proc": df}
_CACHE_AT = None

_CACHE_DIR = os.path.join(
    str(get_cache_dir("pca")),
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "pca_cache.pkl")
_CACHE_META = os.path.join(_CACHE_DIR, "meta.pkl")


def _now_sp():
    return now_sp()


def _fmt_dt(dt):
    return format_datetime_sp(dt)


def _load_disk_cache(allow_stale: bool = False):
    """
    Retorna (obj, cached_at_dt, is_stale).
    Se allow_stale=True, retorna também cache expirado (melhor do que tela vazia).
    """
    try:
        if not (os.path.exists(_CACHE_FILE) and os.path.exists(_CACHE_META)):
            return None, None, False

        with open(_CACHE_META, "rb") as f:
            meta = pickle.load(f)

        cached_at = meta.get("cached_at")
        if not cached_at:
            return None, None, False

        cached_at_dt = datetime.fromisoformat(cached_at)
        # garante timezone coerente
        if cached_at_dt.tzinfo is None:
            cached_at_dt = cached_at_dt.replace(tzinfo=timezone("America/Sao_Paulo"))

        age = _now_sp() - cached_at_dt
        is_stale = age > timedelta(minutes=CACHE_TTL_MINUTOS)
        if is_stale and not allow_stale:
            return None, None, False

        obj = pd.read_pickle(_CACHE_FILE)
        return obj, cached_at_dt, is_stale
    except Exception:
        return None, None, False


def _save_disk_cache(obj, cached_at: datetime):
    try:
        pd.to_pickle(obj, _CACHE_FILE)
        with open(_CACHE_META, "wb") as f:
            pickle.dump({"cached_at": cached_at.isoformat()}, f)
    except Exception:
        pass


def get_pca_cache(force: bool = False):
    """
    Retorna (cache_obj, status_msg)

    cache_obj: {"base": df_pca_base, "plan": df_planejamento, "proc": tabela_processos_unida}
    """
    global _CACHE, _CACHE_AT

    now = _now_sp()
    stale = (
        _CACHE is None
        or _CACHE_AT is None
        or (now - _CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
    )

    if force or stale:
        with _CACHE_LOCK:
            now2 = _now_sp()
            stale2 = (
                _CACHE is None
                or _CACHE_AT is None
                or (now2 - _CACHE_AT > timedelta(minutes=CACHE_TTL_MINUTOS))
            )

            # 1) tenta cache em disco (fresco) quando não for reload manual
            if (not force) and stale2:
                disk_obj, at_disk, is_stale = _load_disk_cache(allow_stale=False)
                if disk_obj is not None and at_disk is not None:
                    _CACHE = disk_obj
                    _CACHE_AT = now2
                    return _CACHE, f"Dados carregados do cache em disco ({_fmt_dt(at_disk)})."

            # 2) tenta recarregar da planilha
            try:
                df_base = carregar_dados_pca()
                df_plan, df_proc = _build_derivados(df_base.copy())
                _CACHE = {"base": df_base, "plan": df_plan, "proc": df_proc}
                _CACHE_AT = now2
                _save_disk_cache(_CACHE, now2)
                return _CACHE, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())})."
            except Exception as e:
                # 3) fallback: mantém dados anteriores (memória) ou usa cache em disco mesmo vencido
                if _CACHE is not None:
                    return _CACHE, f"Falha ao recarregar a planilha; mantendo último cache em memória. ({type(e).__name__})"

                disk_obj, at_disk, is_stale = _load_disk_cache(allow_stale=True)
                if disk_obj is not None and at_disk is not None:
                    _CACHE = disk_obj
                    _CACHE_AT = now2
                    msg_stale = "(cache vencido) " if is_stale else ""
                    return _CACHE, f"Falha ao recarregar a planilha; usando {msg_stale}cache em disco ({_fmt_dt(at_disk)}). ({type(e).__name__})"

                return {"base": pd.DataFrame(), "plan": pd.DataFrame(), "proc": pd.DataFrame()}, f"Falha ao carregar dados. ({type(e).__name__})"

    return _CACHE, f"Dados em cache (memória) — verificado em {_fmt_dt(_now_sp())}."


def _opcoes_unicas(df: pd.DataFrame, col: str):
    if df is None or df.empty or col not in df.columns:
        return []
    vals = [v for v in sorted(df[col].dropna().unique()) if str(v).strip() != ""]
    return [{"label": str(v), "value": str(v)} for v in vals]


def _aplicar_filtro_saldo(df_plan: pd.DataFrame, filtro_saldo: str):
    if df_plan is None or df_plan.empty:
        return df_plan
    filtro = str(filtro_saldo or "").strip().lower()
    if filtro == "positivo":
        return df_plan[df_plan["Saldo"].fillna(0) > 0]
    if filtro == "negativo":
        return df_plan[df_plan["Saldo"].fillna(0) < 0]
    return df_plan


# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    children=[
        dcc.Location(id="url"),
        # Barra de filtros (sobrepõe as tabelas)
        html.Div(
            id="barra_filtros_pca",
            className="filtros-sticky",
            style={
                "position": "relative",
                "zIndex": 1100,
                "backgroundColor": "white",
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
                        html.Div(
                            style={"minWidth": "120px", "flex": "0 0 140px"},
                            children=[
                                html.Label("Ano"),
                                dcc.Dropdown(
                                    id="filtro_ano_pca",
                                    options=[{"label": ANO_PADRAO_PCA, "value": ANO_PADRAO_PCA}],
                                    value=ANO_PADRAO_PCA,
                                    placeholder=None,
                                    clearable=False,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Material ou Serviço"),
                                dcc.Dropdown(
                                    id="filtro_tipo_pca",
                                    options=[],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Área requisitante"),
                                dcc.Dropdown(
                                    id="filtro_area_pca",
                                    options=[],
                                    value=None,
                                    placeholder="Todas",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "180px", "flex": "0 0 190px"},
                            children=[
                                html.Label("Saldo do item"),
                                dcc.Dropdown(
                                    id="filtro_saldo_pca",
                                    options=[
                                        {"label": "Todos", "value": "todos"},
                                        {"label": "Saldo positivo", "value": "positivo"},
                                        {"label": "Saldo negativo", "value": "negativo"},
                                    ],
                                    value="todos",
                                    clearable=False,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Nome Classe/Grupo (digitação)"),
                                dcc.Input(
                                    id="filtro_classe_texto_pca",
                                    type="text",
                                    placeholder="Digite parte do nome da classe/grupo",
                                    debounce=True,
                                    style={
                                        "width": "100%",
                                        "marginBottom": "6px",
                                    },
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("DFD (digitação)"),
                                dcc.Input(
                                    id="filtro_dfd_texto_pca",
                                    type="text",
                                    placeholder="Digite parte do DFD",
                                    debounce=True,
                                    style={
                                        "width": "100%",
                                        "marginBottom": "6px",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "space-between",
                        "marginTop": "6px",
                        "flexWrap": "wrap",
                        "gap": "10px",
                    },
                    children=[
                        html.Div(
                            children=[
                                html.Button(
                                    "Limpar filtros",
                                    id="btn_limpar_filtros_pca",
                                    n_clicks=0,
                                    style={**button_limpar_style, "marginRight": "10px"},
                                ),
                                html.Button(
                                    "Atualizar Dados",
                                    id="btn_reload_pca",
                                    n_clicks=0,
                                    style={**button_atualizar_style, "marginRight": "10px"},
                                ),
                                html.Button(
                                    "Baixar Relatório PDF",
                                    id="btn_download_relatorio_pca",
                                    n_clicks=0,
                                    style=button_pdf_style,
                                ),
                                dcc.Download(id="download_relatorio_pca"),
                                html.Div(
                                    id="info-atualizacao-pca",
                                    style={"fontSize": "12px", "color": "#333", "marginTop": "6px"},
                                ),
                            ],
                        ),
                        html.Div(
                            style={
                                "display": "flex",
                                "justifyContent": "center",
                                "flexGrow": 1,
                                "gap": "10px",
                                "flexWrap": "wrap",
                            },
                            children=[
                                html.Div(
                                    id="card_planejado_pca",
                                    style={
                                        "minWidth": "180px",
                                        "padding": "10px 15px",
                                        "textAlign": "center",
                                    },
                                ),
                                html.Div(
                                    id="card_executado_pca",
                                    style={
                                        "minWidth": "180px",
                                        "padding": "10px 15px",
                                        "textAlign": "center",
                                    },
                                ),
                                html.Div(
                                    id="card_saldo_pca",
                                    style={
                                        "minWidth": "180px",
                                        "padding": "10px 15px",
                                        "textAlign": "center",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        # Tabelas
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "10px",
                "marginTop": "10px",
            },
            children=[
                # Planejamento
                html.Div(
                    style={
                        "flex": "1 1 50%",
                        "minWidth": "300px",
                        "position": "relative",
                        "zIndex": 1,
                    },
                    children=[
                        html.H4("Planejamento (PCA)"),
                        dash_table.DataTable(
                            id="tabela_pca_planejamento",
                            columns=[
                                {"name": "DFD", "id": "DFD"},
                                {"name": "Área requisitante", "id": "Área requisitante"},
                                {"name": "Material ou Serviço", "id": "Material ou Serviço"},
                                {"name": "Item", "id": "Item"},
                                {"name": "Nome Classe/Grupo", "id": "Nome Classe/Grupo"},
                                {"name": "Código PDM material", "id": "Código PDM material"},
                                {"name": "Nome do PDM material", "id": "Nome do PDM material"},
                                {"name": "Planejado", "id": "Planejado_fmt"},
                                {"name": "Executado", "id": "Executado_fmt"},
                                {"name": "Saldo", "id": "Saldo_fmt"},
                                # colunas técnicas (para condição)
                                {"name": "Saldo_num", "id": "Saldo_num"},
                                {"name": "Planejado_num", "id": "Planejado_num"},
                            ],
                            hidden_columns=["Saldo_num", "Planejado_num"],
                            data=[],
                            css=[{"selector": ".show-hide", "rule": "display: none !important;"}],
                            page_action="none",
                            fixed_rows={"headers": True},
                            virtualization=True,
                            row_selectable=False,
                            cell_selectable=False,
                            column_selectable=False,
                            style_table={
                                "overflowX": "auto",
                                "overflowY": "auto",
                                "maxHeight": "420px",
                                "width": "100%",
                                "tableLayout": "fixed",
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
                                {"if": {"column_id": "DFD"}, "width": "80px", "minWidth": "80px", "maxWidth": "80px"},
                                {"if": {"column_id": "Área requisitante"}, "width": "130px", "minWidth": "130px", "maxWidth": "130px"},
                                {"if": {"column_id": "Material ou Serviço"}, "width": "130px", "minWidth": "130px", "maxWidth": "130px"},
                                {"if": {"column_id": "Item"}, "width": "60px", "minWidth": "60px", "maxWidth": "60px"},
                                {"if": {"column_id": "Nome Classe/Grupo"}, "width": "320px", "minWidth": "320px", "maxWidth": "320px"},
                                {"if": {"column_id": "Código PDM material"}, "width": "115px", "minWidth": "115px", "maxWidth": "115px"},
                                {"if": {"column_id": "Nome do PDM material"}, "width": "235px", "minWidth": "235px", "maxWidth": "235px"},
                                {"if": {"column_id": "Planejado_fmt"}, "width": "130px", "minWidth": "130px", "maxWidth": "130px"},
                                {"if": {"column_id": "Executado_fmt"}, "width": "130px", "minWidth": "130px", "maxWidth": "130px"},
                                {"if": {"column_id": "Saldo_fmt"}, "width": "130px", "minWidth": "130px", "maxWidth": "130px"},
                            ],
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": "#0b2b57",
                                "color": "white",
                            },
                            style_data_conditional=[
                                {"if": {"filter_query": "{Saldo_num} <= 0"}, "backgroundColor": "#ffcccc"},
                                {
                                    "if": {"filter_query": "{Saldo_num} > 0 && {Saldo_num} < {Planejado_num}"},
                                    "backgroundColor": "#ccffcc",
                                },
                            ],
                        ),
                    ],
                ),
                html.Div(
                    style={
                        "width": "100%",
                        "border": "1px solid #9e9e9e",
                        "padding": "10px 12px",
                        "backgroundColor": "white",
                        "fontSize": "12px",
                        "lineHeight": "1.35",
                        "color": "#333333",
                    },
                    children=[
                        html.Div(
                            [
                                "Os processos listados abaixo podem ser consultados na área pública do SIPAC. Link de acesso: ",
                                html.A(
                                    "https://sipac.unifei.edu.br/public/jsp/portal.jsf",
                                    href="https://sipac.unifei.edu.br/public/jsp/portal.jsf",
                                    target="_blank",
                                    style={"fontWeight": "bold"},
                                ),
                                html.Br(),
                                "Clicar em CONSULTAS >> PROCESSOS. Em seguida, informar o número do processo desejado, obedecendo à máscara da tela. Exemplo para o processo 23088.099999.2023-90:",
                            ]
                        ),
                        html.Div(
                            style={"display": "flex", "justifyContent": "center", "gap": "6px", "margin": "10px 0"},
                            children=[
                                html.Div("23088", style={"border": "1px solid #777", "padding": "4px 6px", "fontWeight": "bold", "backgroundColor": "#f4f4f4"}),
                                html.Div("099999", style={"border": "1px solid #777", "padding": "4px 6px", "fontWeight": "bold", "backgroundColor": "#f4f4f4"}),
                                html.Div("2023", style={"border": "1px solid #777", "padding": "4px 6px", "fontWeight": "bold", "backgroundColor": "#f4f4f4"}),
                                html.Div("90", style={"border": "1px solid #777", "padding": "4px 6px", "fontWeight": "bold", "backgroundColor": "#f4f4f4"}),
                            ],
                        ),
                        html.Div(
                            [
                                "Em seguida, clicar na lupa à direita ",
                                html.Span("🔍", style={"fontSize": "16px"}),
                                " para ter acesso ao conteúdo do processo que esteja classificado como OSTENSIVO.",
                            ]
                        ),
                    ],
                ),
                # Processos vinculados
                html.Div(
                    style={
                        "flex": "1 1 50%",
                        "minWidth": "300px",
                        "position": "relative",
                        "zIndex": 1,
                    },
                    children=[
                        html.H4("Processos vinculados ao PCA"),
                        dash_table.DataTable(
                            id="tabela_pca_processos",
                            columns=[
                                {"name": "DFD", "id": "DFD"},
                                {"name": "Área requisitante", "id": "Área requisitante"},
                                {"name": "Material ou Serviço", "id": "Material ou Serviço"},
                                {"name": "Item", "id": "Item"},
                                {"name": "Processo", "id": "Processo"},
                                {"name": "Objeto", "id": "Objeto"},
                                {"name": "Observações", "id": "Observações"},
                                {"name": "Valor", "id": "Valor_fmt"},
                            ],
                            data=[],
                            css=[{"selector": ".show-hide", "rule": "display: none !important;"}],
                            page_action="none",
                            fixed_rows={"headers": True},
                            virtualization=True,
                            row_selectable=False,
                            cell_selectable=False,
                            column_selectable=False,
                            style_table={
                                "overflowX": "auto",
                                "overflowY": "auto",
                                "maxHeight": "420px",
                                "width": "100%",
                                "tableLayout": "fixed",
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
                                {"if": {"column_id": "DFD"}, "width": "90px", "minWidth": "90px", "maxWidth": "90px"},
                                {"if": {"column_id": "Área requisitante"}, "width": "155px", "minWidth": "155px", "maxWidth": "155px"},
                                {"if": {"column_id": "Material ou Serviço"}, "width": "155px", "minWidth": "155px", "maxWidth": "155px"},
                                {"if": {"column_id": "Item"}, "width": "70px", "minWidth": "70px", "maxWidth": "70px"},
                                {"if": {"column_id": "Processo"}, "width": "205px", "minWidth": "205px", "maxWidth": "205px"},
                                {"if": {"column_id": "Objeto"}, "width": "365px", "minWidth": "365px", "maxWidth": "365px", "textAlign": "left"},
                                {"if": {"column_id": "Observações"}, "width": "310px", "minWidth": "310px", "maxWidth": "310px", "textAlign": "left"},
                                {"if": {"column_id": "Valor_fmt"}, "width": "135px", "minWidth": "135px", "maxWidth": "135px"},
                            ],
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
        dcc.Store(id="store_dados_pca_processos"),
        dcc.Store(id="store-reload-pca"),
        dcc.Interval(id="interval-reload-pca", interval=60 * 60 * 1000, n_intervals=0),  # 1h
    ],
)


# --------------------------------------------------
# Callback: abrir página / interval / botão (recarrega cache + popula opções)
# --------------------------------------------------
@dash.callback(
    Output("store-reload-pca", "data"),
    Output("info-atualizacao-pca", "children"),
    Output("filtro_ano_pca", "options"),
    Output("filtro_tipo_pca", "options"),
    Output("filtro_area_pca", "options"),
    Input("url", "pathname"),
    Input("interval-reload-pca", "n_intervals"),
    Input("btn_reload_pca", "n_clicks"),
)
def carregar_ao_abrir_interval_ou_recarregar(pathname, _n_intervals, n_clicks):
    if pathname != "/pca":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    cache, status = get_pca_cache(force=force)
    df_base = cache["base"] if cache else pd.DataFrame()

    anos = _opcoes_unicas(df_base, "Ano")
    # Mantém TODOS os anos disponíveis, mas deixa 2026 como padrão na abertura.
    # Normaliza para inteiros e ordena; preserva apenas valores numéricos.
    anos_norm = []
    for o in anos:
        v = o.get("value")
        try:
            ano_int = int(float(str(v).strip()))
        except Exception:
            continue
        anos_norm.append(ano_int)
    anos_norm = sorted(set(anos_norm))
    if get_default_year() not in anos_norm:
        anos_norm = [get_default_year()] + anos_norm
    anos = [{"label": str(a), "value": str(a)} for a in anos_norm]
    if not anos:
        anos = [{"label": ANO_PADRAO_PCA, "value": ANO_PADRAO_PCA}]

    tipos = _opcoes_unicas(df_base, "Material ou Serviço")
    areas = _opcoes_unicas(df_base, "Área requisitante")

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    return {"ts": now_sp().isoformat()}, msg, anos, tipos, areas


# --------------------------------------------------
# Callbacks de dados + cartões (agora reagem ao reload)
# --------------------------------------------------
@dash.callback(
    Output("tabela_pca_planejamento", "data"),
    Output("tabela_pca_processos", "data"),
    Output("store_dados_pca_processos", "data"),
    Output("card_planejado_pca", "children"),
    Output("card_executado_pca", "children"),
    Output("card_saldo_pca", "children"),
    Input("store-reload-pca", "data"),
    Input("filtro_ano_pca", "value"),
    Input("filtro_classe_texto_pca", "value"),
    Input("filtro_dfd_texto_pca", "value"),
    Input("filtro_area_pca", "value"),
    Input("filtro_tipo_pca", "value"),
    Input("filtro_saldo_pca", "value"),
)
def atualizar_tabelas_pca(_reload, ano, classe_texto, dfd_texto, area, tipo, filtro_saldo):
    cache, _ = get_pca_cache(force=False)
    if not cache:
        return [], [], [], html.Div(), html.Div(), html.Div()

    dff_plan = cache["plan"].copy()
    dff_proc = cache["proc"].copy()

    # FILTRAR FORA DFD "*"
    dff_plan = dff_plan[dff_plan["DFD"] != "*"]
    dff_proc = dff_proc[dff_proc["DFD"] != "*"]

    # Se o dropdown vier vazio na carga inicial, assume o ano padrão configurado.
    ano = str(ano).strip() if ano is not None else ""
    if not ano:
        ano = ANO_PADRAO_PCA

    dff_plan = dff_plan[dff_plan["Ano"] == str(ano)]
    dff_proc = dff_proc[dff_proc["Ano"] == str(ano)]
    if classe_texto and str(classe_texto).strip():
        termo = str(classe_texto).strip().lower()
        if "Nome Classe/Grupo" in dff_plan.columns:
            dff_plan = dff_plan[
                dff_plan["Nome Classe/Grupo"]
                .astype(str)
                .str.lower()
                .str.contains(termo, na=False)
            ]
        if "Nome Classe/Grupo" in dff_proc.columns:
            dff_proc = dff_proc[
                dff_proc["Nome Classe/Grupo"]
                .astype(str)
                .str.lower()
                .str.contains(termo, na=False)
            ]

    if dfd_texto and str(dfd_texto).strip():
        termo = str(dfd_texto).strip().lower()
        dff_plan = dff_plan[
            dff_plan["DFD"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        ]
        dff_proc = dff_proc[
            dff_proc["DFD"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        ]

    if area:
        dff_plan = dff_plan[dff_plan["Área requisitante"] == area]
        dff_proc = dff_proc[dff_proc["Área requisitante"] == area]

    if tipo:
        dff_plan = dff_plan[dff_plan["Material ou Serviço"] == tipo]
        dff_proc = dff_proc[dff_proc["Material ou Serviço"] == tipo]

    dff_plan = _aplicar_filtro_saldo(dff_plan, filtro_saldo)
    if filtro_saldo in {"positivo", "negativo"}:
        chaves = set(
            zip(
                dff_plan["DFD"].astype(str),
                dff_plan["Item"].astype(str),
            )
        )
        if chaves:
            dff_proc = dff_proc[
                dff_proc.apply(lambda r: (str(r.get("DFD", "")), str(r.get("Item", ""))) in chaves, axis=1)
            ]
        else:
            dff_proc = dff_proc.iloc[0:0]

    # remove linhas sem processo
    dff_proc = dff_proc[
        (dff_proc["Processo"].astype(str).str.strip() != "")
        & (dff_proc["Processo"].astype(str).str.strip().str.lower() != "nan")
        & (dff_proc["Processo"].notna())
    ]

    # Item inteiro (robusto: não quebra em valores inesperados)
    dff_plan["Item"] = dff_plan["Item"].apply(normalizar_item)
    dff_proc["Item"] = dff_proc["Item"].apply(normalizar_item)

    dff_plan["Saldo_num"] = dff_plan["Saldo"]
    dff_plan["Planejado_num"] = dff_plan["Planejado"]

    if "Código PDM material" in dff_plan.columns:
        dff_plan["Código PDM material"] = dff_plan["Código PDM material"].apply(
            lambda x: "" if pd.isna(x) else int(x)
        )

    def marca_executado(v):
        if v is None or pd.isna(v):
            return ""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return ""
        marcador = " ✔" if v > 0 else ""
        return formatar_moeda(v) + marcador

    dff_plan["Planejado_fmt"] = dff_plan["Planejado"].apply(formatar_moeda)
    dff_plan["Executado_fmt"] = dff_plan["Executado"].apply(marca_executado)
    dff_plan["Saldo_fmt"] = dff_plan["Saldo"].apply(formatar_moeda)

    dff_proc["Valor_fmt"] = dff_proc["Valor"].apply(formatar_moeda)

    cols_planejamento = [
        "DFD",
        "Área requisitante",
        "Material ou Serviço",
        "Item",
        "Nome Classe/Grupo",
        "Código PDM material",
        "Nome do PDM material",
        "Planejado_fmt",
        "Executado_fmt",
        "Saldo_fmt",
        "Saldo_num",
        "Planejado_num",
    ]

    dados_planejamento = dff_plan[cols_planejamento].fillna("").to_dict("records")

    cols_processos = [
        "DFD",
        "Área requisitante",
        "Material ou Serviço",
        "Item",
        "Processo",
        "Objeto",
        "Observações",
        "Valor_fmt",
    ]

    dados_processos_df = dff_proc[cols_processos].fillna("")
    dados_processos = dados_processos_df.to_dict("records")

    total_planejado = dff_plan["Planejado"].sum()
    total_executado = dff_plan["Executado"].sum()
    total_saldo = dff_plan["Saldo"].sum()

    card_planejado = html.Div(
        [
            html.Div(
                formatar_moeda(total_planejado),
                style={"color": "#c0392b", "fontSize": "20px", "fontWeight": "bold"},
            ),
            html.Div("Planejado"),
        ]
    )
    card_executado = html.Div(
        [
            html.Div(
                formatar_moeda(total_executado),
                style={"color": "#0b2b57", "fontSize": "20px", "fontWeight": "bold"},
            ),
            html.Div("Executado"),
        ]
    )
    card_saldo = html.Div(
        [
            html.Div(
                formatar_moeda(total_saldo),
                style={"color": "#2c3e50", "fontSize": "20px", "fontWeight": "bold"},
            ),
            html.Div("Saldo"),
        ]
    )

    return (
        dados_planejamento,
        dados_processos,
        dados_processos_df.to_dict("records"),
        card_planejado,
        card_executado,
        card_saldo,
    )


@dash.callback(
    Output("filtro_ano_pca", "value"),
    Output("filtro_classe_texto_pca", "value"),
    Output("filtro_dfd_texto_pca", "value"),
    Output("filtro_area_pca", "value"),
    Output("filtro_tipo_pca", "value"),
    Output("filtro_saldo_pca", "value"),
    Input("btn_limpar_filtros_pca", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_pca(_n):
    return ANO_PADRAO_PCA, None, None, None, None, "todos"


# --------------------------------------------------
# PDF - estilos para PCA
# --------------------------------------------------
wrap_style_pca = ParagraphStyle(
    name="wrap_pca_pdf",
    fontSize=7,
    leading=8,
    spaceAfter=2,
    wordWrap="CJK",
)

simple_style_pca = ParagraphStyle(
    name="simple_pca_pdf",
    fontSize=7,
    leading=8,
    alignment=TA_CENTER,
)


def wrap_pdf(text):
    return Paragraph(str(text), wrap_style_pca)


def simple_pdf(text):
    return Paragraph(str(text), simple_style_pca)


# --------------------------------------------------
# Callback: gerar PDF do PCA
# --------------------------------------------------
@dash.callback(
    Output("download_relatorio_pca", "data"),
    Input("btn_download_relatorio_pca", "n_clicks"),
    State("store_dados_pca_processos", "data"),
    State("tabela_pca_planejamento", "data"),
    State("filtro_ano_pca", "value"),
    prevent_initial_call=True,
)
def gerar_pdf_pca(n, dados_processos, dados_planejamento, ano_selecionado):
    if not n or (not dados_processos and not dados_planejamento):
        return None

    buffer = BytesIO()
    pagesize = portrait(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.15 * inch,
        leftMargin=0.15 * inch,
        topMargin=0.2 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    tz_brasilia = timezone("America/Sao_Paulo")
    data_hora_brasilia = datetime.now(tz_brasilia).strftime("%d/%m/%Y %H:%M:%S")
    data_top_table = Table(
        [[
            Paragraph(
                data_hora_brasilia,
                ParagraphStyle(
                    "data_topo_pca",
                    fontSize=9,
                    alignment=TA_RIGHT,
                    textColor="#333333",
                ),
            )
        ]],
        colWidths=[pagesize[0] - 0.3 * inch],
    )
    data_top_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT")]))

    story.append(data_top_table)
    story.append(Spacer(1, 0.1 * inch))

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
        ParagraphStyle("instituicao_pca", alignment=TA_CENTER, leading=16),
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
        "RELATÓRIO DE PLANEJAMENTO DE CONTRATAÇÃO ANUAL (PCA) 2026<br/>",
        ParagraphStyle(
            "titulo_pca",
            alignment=TA_CENTER,
            fontSize=10,
            leading=14,
            textColor=colors.black,
        ),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))

    # PLANEJAMENTO
    if dados_planejamento:
        df_plan = pd.DataFrame(dados_planejamento)
        story.append(
            Paragraph(
                "PLANEJAMENTO (PCA)",
                ParagraphStyle(
                    "subtitulo_plan",
                    fontSize=9,
                    alignment=TA_LEFT,
                    textColor="#0b2b57",
                    fontName="Helvetica-Bold",
                    spaceAfter=6,
                ),
            )
        )
        story.append(Paragraph(f"Total de registros: {len(df_plan)}", styles["Normal"]))
        story.append(Spacer(1, 0.08 * inch))

        cols_plan = [
            "DFD",
            "Área requisitante",
            "Material ou Serviço",
            "Item",
            "Nome Classe/Grupo",
            "Planejado_fmt",
            "Executado_fmt",
            "Saldo_fmt",
        ]
        cols_plan = [c for c in cols_plan if c in df_plan.columns]
        df_plan_filtered = df_plan[cols_plan].copy()

        label_plan = {
            "DFD": "DFD",
            "Área requisitante": "Área requisitante",
            "Material ou Serviço": "Material ou Serviço",
            "Item": "Item",
            "Nome Classe/Grupo": "Nome Classe/Grupo",
            "Planejado_fmt": "Planejado",
            "Executado_fmt": "Executado",
            "Saldo_fmt": "Saldo",
        }
        width_plan = {
            "DFD": 0.9 * inch,
            "Área requisitante": 1.1 * inch,
            "Material ou Serviço": 1.2 * inch,
            "Item": 0.45 * inch,
            "Nome Classe/Grupo": 1.6 * inch,
            "Planejado_fmt": 0.9 * inch,
            "Executado_fmt": 0.9 * inch,
            "Saldo_fmt": 0.9 * inch,
        }

        header_plan = [label_plan.get(c, c) for c in cols_plan]
        table_data_plan = [header_plan]

        for _, row in df_plan_filtered.iterrows():
            linha = []
            for c in cols_plan:
                valor = str(row[c]).strip()
                if c in ["Nome Classe/Grupo"]:
                    linha.append(wrap_pdf(valor))
                else:
                    linha.append(simple_pdf(valor))
            table_data_plan.append(linha)

        col_widths_plan = [width_plan.get(c, 1.0 * inch) for c in cols_plan]
        avail_w = pagesize[0] - doc.leftMargin - doc.rightMargin
        total_w = sum(col_widths_plan) if col_widths_plan else 1.0
        scale = min(1.0, avail_w / total_w)
        col_widths_plan = [w * scale for w in col_widths_plan]

        tbl_plan = Table(table_data_plan, colWidths=col_widths_plan, repeatRows=1)

        style_list_plan = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ]
        tbl_plan.setStyle(TableStyle(style_list_plan))
        story.append(tbl_plan)
        story.append(Spacer(1, 0.2 * inch))

    # PROCESSOS
    if dados_processos:
        df_proc = pd.DataFrame(dados_processos)
        story.append(
            Paragraph(
                "PROCESSOS VINCULADOS AO PCA",
                ParagraphStyle(
                    "subtitulo_proc",
                    fontSize=9,
                    alignment=TA_LEFT,
                    textColor="#0b2b57",
                    fontName="Helvetica-Bold",
                    spaceAfter=6,
                ),
            )
        )
        story.append(Paragraph(f"Total de registros: {len(df_proc)}", styles["Normal"]))
        story.append(Spacer(1, 0.08 * inch))

        cols_proc = ["DFD", "Área requisitante", "Material ou Serviço", "Item", "Processo", "Objeto", "Observações", "Valor_fmt"]
        cols_proc = [c for c in cols_proc if c in df_proc.columns]
        df_proc_filtered = df_proc[cols_proc].copy()

        label_proc = {
            "DFD": "DFD",
            "Área requisitante": "Área requisitante",
            "Material ou Serviço": "Material ou Serviço",
            "Item": "Item",
            "Processo": "Processo",
            "Objeto": "Objeto",
            "Observações": "Observações",
            "Valor_fmt": "Valor",
        }
        width_proc = {
            "DFD": 0.85 * inch,
            "Área requisitante": 1.0 * inch,
            "Material ou Serviço": 1.1 * inch,
            "Item": 0.5 * inch,
            "Processo": 1.05 * inch,
            "Objeto": 1.4 * inch,
            "Observações": 1.4 * inch,
            "Valor_fmt": 0.9 * inch,
        }

        header_proc = [label_proc.get(c, c) for c in cols_proc]
        table_data_proc = [header_proc]

        for _, row in df_proc_filtered.iterrows():
            linha = []
            for c in cols_proc:
                valor = str(row[c]).strip()
                if c in ["Objeto", "Observações"]:
                    linha.append(wrap_pdf(valor))
                else:
                    linha.append(simple_pdf(valor))
            table_data_proc.append(linha)

        col_widths_proc = [width_proc.get(c, 1.0 * inch) for c in cols_proc]
        avail_w = pagesize[0] - doc.leftMargin - doc.rightMargin
        total_w = sum(col_widths_proc) if col_widths_proc else 1.0
        scale = min(1.0, avail_w / total_w)
        col_widths_proc = [w * scale for w in col_widths_proc]

        tbl_proc = Table(table_data_proc, colWidths=col_widths_proc, repeatRows=1)

        style_list_proc = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ]
        tbl_proc.setStyle(TableStyle(style_list_proc))
        story.append(tbl_proc)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"relatorio_pca_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

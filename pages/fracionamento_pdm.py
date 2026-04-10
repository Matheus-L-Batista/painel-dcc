import dash
from dash import html, dcc, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate

import pandas as pd

from datetime import date, datetime, timedelta
from pytz import timezone

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
import os
import threading
import pickle

from utils.runtime import format_datetime_sp, get_cache_dir, now_sp

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/fracionamento_pdm",
    name="Fracionamento de Despesas PDM",
    title="Fracionamento de Despesas PDM",
)

# --------------------------------------------------
# URL da planilha
# --------------------------------------------------
URL_LIMITE_GASTO_ITA = (
    "https://docs.google.com/spreadsheets/d/"
    "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog/"
    "gviz/tq?tqx=out:csv&sheet=Limite%20de%20Gasto%20-%20Itajub%C3%A1"
)

COL_PDM = "PDM"
COL_DESC_ORIG = "Descrição.1"
COL_VALOR_EMPENHADO_ORIG = "Unnamed: 7"

# Limite da dispensa 2026
VALOR_LIMITE_2026 = 65492.11

# --------------------------------------------------
# Carga e tratamento dos dados
# --------------------------------------------------
def carregar_dados_limite_pdm():
    df = pd.read_csv(URL_LIMITE_GASTO_ITA)
    df.columns = [c.strip() for c in df.columns]

    if COL_PDM not in df.columns:
        df[COL_PDM] = ""

    if COL_DESC_ORIG not in df.columns:
        df[COL_DESC_ORIG] = ""

    df[COL_PDM] = (
        df[COL_PDM]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(5)
    )

    if COL_VALOR_EMPENHADO_ORIG in df.columns:
        df["Valor Empenhado"] = (
            df[COL_VALOR_EMPENHADO_ORIG]
            .astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df["Valor Empenhado"] = pd.to_numeric(df["Valor Empenhado"], errors="coerce")
    else:
        df["Valor Empenhado"] = 0.0

    # Usa o limite de 2026
    valor_limite = VALOR_LIMITE_2026
    df["Limite da Dispensa"] = valor_limite
    df["Saldo para contratação"] = df["Limite da Dispensa"] - df["Valor Empenhado"]

    df = df.rename(columns={COL_DESC_ORIG: "Descrição"})

    return df


# --------------------------------------------------
# Cache (memória + disco) + atualização automática
# --------------------------------------------------
CACHE_TTL_MINUTOS = 60  # 1h
_CACHE_LOCK = threading.Lock()
_DF_CACHE = None
_DF_CACHE_AT = None

_CACHE_DIR = os.path.join(
    str(get_cache_dir("fracionamento_pdm"))
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "df_pdm.pkl")
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


def get_df_pdm(force: bool = False):
    """
    Retorna (df, status_msg).
    - Cache em memória (rápido)
    - Se memória vazia, tenta disco
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
                df = carregar_dados_limite_pdm()
                _DF_CACHE = df
                _DF_CACHE_AT = now2
                _save_disk_cache(df, now2)
                return _DF_CACHE, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())})."

    return _DF_CACHE, f"Dados em cache (memória) — verificado em {_fmt_dt(_now_sp())}."


def pdms_unicos(df_base: pd.DataFrame):
    if df_base is None or df_base.empty or COL_PDM not in df_base.columns:
        return []
    return sorted(
        c
        for c in df_base[COL_PDM].dropna().unique()
        if isinstance(c, str)
        and c.strip() != ""
        and c.strip() != "00000"
    )


COLS_TABELA_PDM = [
    COL_PDM,
    "Descrição",
    "Valor Empenhado",
    "Limite da Dispensa",
    "Saldo para contratação",
]


def fmt_moeda(v):
    if pd.isna(v):
        return ""
    return "R$ " + (f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


def filtrar_dados_pdm(df_base: pd.DataFrame, pdm_lista=None):
    dff = df_base.copy() if df_base is not None else pd.DataFrame()

    if dff.empty:
        return dff

    dff = dff[dff[COL_PDM] != "00000"]

    if pdm_lista:
        dff = dff[dff[COL_PDM].isin(pdm_lista)]

    for c in COLS_TABELA_PDM:
        if c not in dff.columns:
            dff[c] = pd.NA

    return dff


def preparar_payload_tabela_pdm(dff: pd.DataFrame):
    dff_display = dff[COLS_TABELA_PDM].copy()
    dff_display["Valor Empenhado_fmt"] = dff_display["Valor Empenhado"].apply(fmt_moeda)
    dff_display["Limite da Dispensa_fmt"] = dff_display["Limite da Dispensa"].apply(fmt_moeda)
    dff_display["Saldo para contratação_fmt"] = dff_display["Saldo para contratação"].apply(fmt_moeda)
    return dff_display


# --------------------------------------------------
# Estilos
# --------------------------------------------------
dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

botao_limpar_style = {
    "backgroundColor": "#9ca3af",
    "color": "white",
    "border": "1px solid #9ca3af",
    "borderRadius": "4px",
    "padding": "6px 12px",
    "cursor": "pointer",
    "fontWeight": "bold",
}

botao_atualizar_style = {
    "backgroundColor": "#0b2b57",
    "color": "white",
    "border": "1px solid #0b2b57",
    "borderRadius": "4px",
    "padding": "6px 12px",
    "cursor": "pointer",
    "fontWeight": "bold",
}

botao_pdf_style = {
    "backgroundColor": "#d92d20",
    "color": "white",
    "border": "1px solid #d92d20",
    "borderRadius": "4px",
    "padding": "6px 12px",
    "cursor": "pointer",
    "fontWeight": "bold",
}

card_padrao_style = {
    "border": "1px solid #e5e7eb",
    "borderRadius": "8px",
    "padding": "8px 12px",
    "backgroundColor": "#ffffff",
    "minWidth": "140px",
    "width": "140px",
    "height": "54px",
    "boxShadow": "0 6px 18px rgba(15, 23, 42, 0.10)",
    "fontSize": "11px",
    "display": "flex",
    "flexDirection": "column",
    "justifyContent": "center",
}

texto_orientacao_style = {
    "flex": "0 0 36%",
    "borderRight": "1px solid #e5e7eb",
    "padding": "12px 18px",
    "minWidth": "380px",
    "maxWidth": "560px",
    "fontSize": "13px",
    "lineHeight": "1.25",
    "textAlign": "left",
    "backgroundColor": "#ffffff",
    "color": "#111827",
    "overflowY": "auto",
    "height": "100vh",
    "boxSizing": "border-box",
}

painel_dados_style = {
    "flex": "1 1 64%",
    "padding": "14px 16px",
    "minWidth": "0",
    "backgroundColor": "#f3f4f6",
    "boxSizing": "border-box",
}

cabecalho_painel_style = {
    "backgroundColor": "#0b2b57",
    "borderRadius": "8px",
    "padding": "16px",
    "marginBottom": "12px",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "gap": "16px",
    "flexWrap": "wrap",
    "boxShadow": "0 8px 22px rgba(15, 23, 42, 0.16)",
}

filtros_fracionamento_style = {
    "backgroundColor": "#ffffff",
    "border": "1px solid #e5e7eb",
    "borderRadius": "8px",
    "padding": "10px 12px",
    "marginBottom": "10px",
    "boxShadow": "0 2px 8px rgba(15, 23, 42, 0.06)",
}

alerta_orientacao_style = {
    "backgroundColor": "#d92d20",
    "color": "#ffffff",
    "borderRadius": "8px",
    "padding": "10px 12px",
    "margin": "10px 0 0 0",
    "fontWeight": "600",
    "lineHeight": "1.35",
    "boxShadow": "0 4px 12px rgba(217, 45, 32, 0.25)",
}

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style={
        "display": "flex",
        "flexDirection": "row",
        "width": "100%",
        "minHeight": "100vh",
        "gap": "0",
        "backgroundColor": "#f3f4f6",
    },
    children=[
        dcc.Location(id="url"),
        # Coluna esquerda (texto)
        html.Div(
            id="coluna_esquerda_pdm",
            style=texto_orientacao_style,
            children=[
                html.Div(
                    "Limite de Gasto – Itajubá por PDM",
                    style={
                        "fontSize": "20px",
                        "fontWeight": "800",
                        "lineHeight": "1.2",
                        "color": "#0b2b57",
                        "marginBottom": "10px",
                    },
                ),
                html.P("Prezado requisitante,"),
                html.P(
                    "Em atenção ao acórdão nº 324/2009 Plenário TCU, "
                    "“Planeje adequadamente as compras e a contratação de "
                    "serviços durante o exercício financeiro, de forma a "
                    "evitar a prática de fracionamento de despesas”."
                ),
                html.P("Assim dispõe a IN SEGES/ME nº 67/2021:"),
                html.P(
                    "Art. 4º Os órgãos e entidades adotarão a dispensa de "
                    "licitação, na forma eletrônica, nas seguintes hipóteses:"
                ),
                html.P(
                    "[...] § 2º Considera-se ramo de atividade a linha de "
                    "fornecimento registrada pelo fornecedor quando do seu "
                    "cadastramento no Sistema de Cadastramento Unificado de "
                    "Fornecedores (Sicaf), vinculada:"
                ),
                html.P(
                    "I - à classe de materiais, utilizando o Padrão "
                    "Descritivo de Materiais (PDM) do Sistema de Catalogação "
                    "de Material do Governo federal; ou"
                ),
                html.P(
                    "II - à descrição dos serviços ou das obras, constante do "
                    "Sistema de Catalogação de Serviços ou de Obras do "
                    "Governo federal. (NR)"
                ),
                html.P("Em resumo: Para materiais - PDM; para serviços - CATSER."),
                html.P(
                    [
                        "Para obtenção do PDM: no catálogo de compras disponível em ",
                        html.A(
                            "https://catalogo.compras.gov.br/cnbs-web/busca",
                            href="https://catalogo.compras.gov.br/cnbs-web/busca",
                            target="_blank",
                            style={"color": "#1d4ed8", "textDecoration": "underline"},
                        ),
                        ", informar o número do CATSER. Exemplo para o CATSER 123456: a consulta "
                        "retornará os dados do serviço. Esse é o número que deverá ser considerado.",
                    ]
                ),
                html.P("Exemplo para a necessidade de contratação de três itens:"),
                html.P(
                    "1) o somatório do valor obtido na pesquisa de mercado para "
                    "cada um dos itens multiplicado por seu quantitativo não "
                    "poderá exceder o limite da dispensa."
                ),
                html.P(
                    "2) O valor por item deverá obrigatoriamente ser igual ou "
                    "inferior ao saldo para contratação (PDM ou CATSER) desse item."
                ),
                html.P(
                    "Os valores informados na tabela são os já empenhados no "
                    "exercício por PDM ou CATSER."
                ),
                html.Div(
                    "O processo de compra deverá vir instruído já na modalidade "
                    "DISPENSA DE LICITAÇÃO. A tela de consulta (Relatório PDF) "
                    "deverá estar apensado ao processo, que será conferido pelo "
                    "Setor de Compras e, somente a partir do resultado dessa "
                    "conferência, o processo prosseguirá.",
                    style=alerta_orientacao_style,
                ),
            ],
        ),
        # Coluna direita (filtros + tabela)
        html.Div(
            id="coluna_direita_pdm",
            style=painel_dados_style,
            children=[
                html.Div(
                    style=cabecalho_painel_style,
                    children=[
                        html.Div(
                            style={
                                "display": "flex",
                                "flexDirection": "column",
                                "gap": "6px",
                                "flex": "1 1 420px",
                                "minWidth": "320px",
                                "maxWidth": "680px",
                            },
                            children=[
                                html.Div(
                                    children=[
                                        html.Span(
                                            "O valor global do processo de compra não poderá exceder esse limite."
                                        ),
                                        html.Br(),
                                        html.Span(
                                            "O valor de cada item não poderá exceder o Saldo para Contratação."
                                        ),
                                    ],
                                    style={
                                        "color": "#ffffff",
                                        "fontSize": "12px",
                                        "lineHeight": "1.25",
                                    },
                                ),
                            ],
                        ),
                        html.Div(
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "gap": "12px",
                                "flexWrap": "wrap",
                            },
                            children=[
                                html.Div(
                                    style=card_padrao_style,
                                    children=[
                                        html.Div(
                                            "Limite da dispensa (2026)",
                                            style={
                                                "fontWeight": "bold",
                                                "color": "#374151",
                                                "marginBottom": "1px",
                                                "textAlign": "center",
                                                "lineHeight": "1.1",
                                            },
                                        ),
                                        html.Div(
                                            "R$ 65.492,11",
                                            style={
                                                "fontSize": "16px",
                                                "fontWeight": "bold",
                                                "color": "#166534",
                                                "textAlign": "center",
                                            },
                                        ),
                                    ],
                                ),
                                html.Div(
                                    style=card_padrao_style,
                                    children=[
                                        html.Div(
                                            "Data da consulta",
                                            style={
                                                "fontWeight": "bold",
                                                "color": "#374151",
                                                "marginBottom": "1px",
                                                "textAlign": "center",
                                                "lineHeight": "1.1",
                                            },
                                        ),
                                        html.Div(
                                            id="card_data_consulta_pdm",
                                            children=date.today().strftime("%d/%m/%Y"),
                                            style={
                                                "fontSize": "16px",
                                                "fontWeight": "bold",
                                                "color": "#111827",
                                                "textAlign": "center",
                                            },
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    id="barra_filtros_limite_itajuba_pdm",
                    className="filtros-sticky",
                    style=filtros_fracionamento_style,
                    children=[
                        # Primeira linha: PDM (digitação)
                        html.Div(
                            style={
                                "display": "flex",
                                "flexWrap": "wrap",
                                "gap": "10px",
                                "alignItems": "flex-start",
                            },
                            children=[
                                html.Div(
                                    style={
                                        "minWidth": "220px",
                                        "flex": "1 1 260px",
                                        "maxHeight": "60px",
                                    },
                                    children=[
                                        html.Label("PDM (digitação)"),
                                        dcc.Input(
                                            id="filtro_pdm_texto_itajuba",
                                            type="text",
                                            placeholder=(
                                                "Digite parte do CATSER, selecione na lista e, "
                                                "após a seleção, apague o texto digitado."
                                            ),
                                            style={
                                                "width": "100%",
                                                "marginBottom": "8px",
                                                "height": "30px",
                                                "border": "1px solid #cbd5e1",
                                                "borderRadius": "4px",
                                                "padding": "4px 8px",
                                                "boxSizing": "border-box",
                                            },
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # Segunda linha: checklist CATSER
                        html.Div(
                            style={
                                "marginTop": "4px",
                                "display": "flex",
                                "flexWrap": "wrap",
                                "gap": "10px",
                                "alignItems": "flex-start",
                            },
                            children=[
                                html.Div(
                                    style={
                                        "minWidth": "220px",
                                        "flex": "1 1 100%",
                                        "maxHeight": "104px",
                                        "overflowY": "auto",
                                        "border": "1px solid #cbd5e1",
                                        "borderRadius": "4px",
                                        "padding": "6px 8px",
                                        "fontSize": "11px",
                                        "backgroundColor": "#f8fafc",
                                    },
                                    children=[
                                        html.Label("PDM (lista)"),
                                        dcc.Checklist(
                                            id="filtro_pdm_lista_itajuba",
                                            options=[],
                                            value=[],
                                            style={
                                                "display": "flex",
                                                "flexWrap": "wrap",
                                                "justifyContent": "center",
                                                "columnGap": "10px",
                                                "rowGap": "2px",
                                            },
                                            inputStyle={"marginRight": "4px"},
                                            labelStyle={
                                                "display": "inline-block",
                                                "width": "14%",
                                                "fontSize": "11px",
                                                "lineHeight": "1.5",
                                            },
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # Terceira linha: botões + status
                        html.Div(
                            style={
                                "marginTop": "10px",
                                "display": "flex",
                                "alignItems": "center",
                                "gap": "10px",
                                "flexWrap": "wrap",
                            },
                            children=[
                                html.Button(
                                    "Limpar filtros",
                                    id="btn_limpar_filtros_limite_itajuba_pdm_pdm",
                                    n_clicks=0,
                                    style=botao_limpar_style,
                                ),
                                html.Button(
                                    "Atualizar Dados",
                                    id="btn_reload_pdm",
                                    n_clicks=0,
                                    style=botao_atualizar_style,
                                ),
                                html.Button(
                                    "Baixar Relatório PDF",
                                    id="btn_download_relatorio_limite_itajuba_pdm_pdm",
                                    n_clicks=0,
                                    style=botao_pdf_style,
                                ),
                                dcc.Download(id="download_relatorio_limite_itajuba_pdm"),
                                html.Div(
                                    id="info-atualizacao-pdm",
                                    style={"fontSize": "12px", "color": "#333"},
                                ),
                            ],
                        ),
                    ],
                ),
                dash_table.DataTable(
                    id="tabela_limite_itajuba_pdm",
                    columns=[
                        {"name": "PDM", "id": COL_PDM},
                        {"name": "Descrição", "id": "Descrição"},
                        {"name": "Valor Empenhado (R$)", "id": "Valor Empenhado_fmt"},
                        {"name": "Limite da Dispensa (R$)", "id": "Limite da Dispensa_fmt"},
                        {"name": "Saldo para contratação (R$)", "id": "Saldo para contratação_fmt"},
                    ],
                    data=[],
                    page_action="custom",
                    page_current=0,
                    page_size=15,
                    row_selectable=False,
                    cell_selectable=False,
                    style_table={
                        "overflowX": "hidden",
                        "overflowY": "auto",
                        "width": "100%",
                        "height": "calc(100vh - 405px)",
                        "minHeight": "260px",
                        "position": "relative",
                        "border": "1px solid #e5e7eb",
                        "borderRadius": "8px",
                        "backgroundColor": "#ffffff",
                    },
                    style_cell={
                        "textAlign": "center",
                        "padding": "7px 8px",
                        "fontSize": "12px",
                        "fontFamily": "Arial, sans-serif",
                        "minWidth": "0",
                        "maxWidth": "none",
                        "whiteSpace": "normal",
                        "height": "auto",
                        "lineHeight": "1.35",
                    },
                    style_cell_conditional=[
                        {"if": {"column_id": COL_PDM}, "width": "10%"},
                        {"if": {"column_id": "Descrição"}, "width": "34%", "textAlign": "left"},
                        {"if": {"column_id": "Valor Empenhado_fmt"}, "width": "18%"},
                        {"if": {"column_id": "Limite da Dispensa_fmt"}, "width": "18%"},
                        {"if": {"column_id": "Saldo para contratação_fmt"}, "width": "20%"},
                    ],
                    css=[
                        {
                            "selector": ".dash-spreadsheet-container .dash-spreadsheet-inner table",
                            "rule": "table-layout: fixed; width: 100%;",
                        },
                    ],
                    style_header={
                        "fontWeight": "bold",
                        "backgroundColor": "#0b2b57",
                        "color": "white",
                        "textAlign": "center",
                        "position": "sticky",
                        "top": 0,
                        "zIndex": 5,
                    },
                    style_data_conditional=[
                        {"if": {"row_index": "odd"}, "backgroundColor": "#f5f5f5"},
                        {
                            "if": {"filter_query": "{Saldo para contratação} < 0"},
                            "backgroundColor": "#ffcccc",
                            "color": "#b42318",
                        },
                        {
                            "if": {"filter_query": "{Saldo para contratação} > 0 && {Saldo para contratação} != {Limite da Dispensa}"},
                            "backgroundColor": "#dcfce7",
                            "color": "#166534",
                        },
                    ],
                ),
                dcc.Store(id="store-reload-pdm"),
                dcc.Interval(id="interval-reload-pdm", interval=60 * 60 * 1000, n_intervals=0),  # 1h
            ],
        ),
    ],
)

# --------------------------------------------------
# Callback: abrir página / interval / botão (recarrega cache + atualiza lista CATSER + status)
# --------------------------------------------------
@dash.callback(
    Output("store-reload-pdm", "data"),
    Output("info-atualizacao-pdm", "children"),
    Output("filtro_pdm_lista_itajuba", "options"),
    Output("card_data_consulta_pdm", "children"),
    Input("url", "pathname"),
    Input("interval-reload-pdm", "n_intervals"),
    Input("btn_reload_pdm", "n_clicks"),
    State("filtro_pdm_lista_itajuba", "value"),
)
def carregar_ao_abrir_interval_ou_recarregar_pdm(pathname, _n_intervals, n_clicks, selecionados):
    if pathname != "/fracionamento_pdm":
        raise PreventUpdate

    force = dash.ctx.triggered_id == "btn_reload_pdm"
    df, status = get_df_pdm(force=force)

    base = pdms_unicos(df)
    # mantém selecionados que ainda existirem
    selecionados = selecionados or []
    selecionados_validos = [v for v in selecionados if v in base]

    opcoes = [{"label": c, "value": c} for c in base]

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status)])
    data_consulta = _now_sp().strftime("%d/%m/%Y")
    return {"ts": datetime.now().isoformat(), "sel": selecionados_validos}, msg, opcoes, data_consulta


# --------------------------------------------------
# Callback: filtra opções da checklist via texto (mantém selecionados)
# --------------------------------------------------
@dash.callback(
    Output("filtro_pdm_lista_itajuba", "options", allow_duplicate=True),
    Input("filtro_pdm_texto_itajuba", "value"),
    Input("store-reload-pdm", "data"),
    State("filtro_pdm_lista_itajuba", "value"),
    prevent_initial_call=True,
)
def atualizar_opcoes_pdm(pdm_texto, _reload, valores_selecionados):
    df, _ = get_df_pdm(force=False)
    base = pdms_unicos(df)

    if not pdm_texto or not str(pdm_texto).strip():
        filtradas = base
    else:
        termo = str(pdm_texto).strip().lower()
        filtradas = [c for c in base if termo in str(c).lower()]

    # garante selecionados na lista de opções
    valores_selecionados = valores_selecionados or []
    for v in valores_selecionados:
        if v in base and v not in filtradas:
            filtradas.append(v)

    return [{"label": c, "value": c} for c in sorted(filtradas)]


# --------------------------------------------------
# Callback: atualiza tabela (agora reage ao reload também)
# --------------------------------------------------
@dash.callback(
    Output("tabela_limite_itajuba_pdm", "data"),
    Output("tabela_limite_itajuba_pdm", "page_count"),
    Input("store-reload-pdm", "data"),
    Input("filtro_pdm_lista_itajuba", "value"),
    Input("tabela_limite_itajuba_pdm", "page_current"),
    Input("tabela_limite_itajuba_pdm", "page_size"),
)
def atualizar_tabela_limite_itajuba_pdm_pdm(_reload, pdm_lista, page_current, page_size):
    df_base, _ = get_df_pdm(force=False)
    dff = filtrar_dados_pdm(df_base, pdm_lista)

    if dff.empty:
        return [], 0

    page_current = page_current or 0
    page_size = page_size or 15
    page_count = max(1, (len(dff) + page_size - 1) // page_size)
    page_current = min(page_current, page_count - 1)
    start = page_current * page_size
    end = start + page_size
    dff_payload = preparar_payload_tabela_pdm(dff.iloc[start:end])

    return dff_payload.to_dict("records"), page_count


@dash.callback(
    Output("filtro_pdm_texto_itajuba", "value"),
    Output("filtro_pdm_lista_itajuba", "value"),
    Input("btn_limpar_filtros_limite_itajuba_pdm_pdm", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_limite_itajuba_pdm(_n):
    return None, []


# --------------------------------------------------
# PDF
# --------------------------------------------------
wrap_style_data = ParagraphStyle(
    name="wrap_limite_itajuba_data",
    fontSize=7,
    leading=9,
    alignment=TA_CENTER,
    textColor=colors.black,
)

wrap_style_header = ParagraphStyle(
    name="wrap_limite_itajuba_header",
    fontSize=7,
    leading=9,
    alignment=TA_CENTER,
    textColor=colors.white,
)

wrap_style_desc = ParagraphStyle(
    name="wrap_limite_itajuba_desc",
    fontSize=7,
    leading=9,
    alignment=TA_LEFT,
    textColor=colors.black,
)


def wrap_data(text):
    return Paragraph(str(text), wrap_style_data)


def wrap_header(text):
    return Paragraph(str(text), wrap_style_header)


def wrap_desc(text):
    return Paragraph(str(text), wrap_style_desc)


@dash.callback(
    Output("download_relatorio_limite_itajuba_pdm", "data"),
    Input("btn_download_relatorio_limite_itajuba_pdm_pdm", "n_clicks"),
    State("filtro_pdm_lista_itajuba", "value"),
    prevent_initial_call=True,
)
def gerar_pdf_limite_itajuba_pdm(n, pdm_lista):
    if not n:
        return None

    df_base, _ = get_df_pdm(force=False)
    df = filtrar_dados_pdm(df_base, pdm_lista)
    if df.empty:
        return None

    buffer = BytesIO()
    pagesize = portrait(A4)
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
                ParagraphStyle("data_topo", fontSize=9, alignment=TA_RIGHT, textColor="#333333"),
            )]],
            colWidths=[pagesize[0] - 0.6 * inch],
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    logo_esq = (
        Image("assets/brasaobrasil.png", 1.0 * inch, 1.0 * inch)
        if os.path.exists("assets/brasaobrasil.png") else ""
    )
    logo_dir = (
        Image("assets/simbolo_RGB.png", 1.0 * inch, 1.0 * inch)
        if os.path.exists("assets/simbolo_RGB.png") else ""
    )

    texto_instituicao = (
        "<b><font color='#0b2b57' size=12>Ministério da Educação</font></b><br/>"
        "<b><font color='#0b2b57' size=12>Universidade Federal de Itajubá</font></b><br/>"
        "<font color='#0b2b57' size=10>Diretoria de Compras e Contratos</font>"
    )

    instituicao = Paragraph(
        texto_instituicao,
        ParagraphStyle("instituicao", alignment=TA_CENTER, leading=14),
    )

    cabecalho = Table(
        [[logo_esq, instituicao, logo_dir]],
        colWidths=[1.2 * inch, 3.5 * inch, 1.2 * inch],
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
        "Consulta ao Fracionamento de Despesa 2026 - PDM (Material): UASG: 153030 - Campus Itajubá",
        ParagraphStyle("titulo", alignment=TA_CENTER, fontSize=10, leading=14, textColor=colors.black),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Total de registros: {len(df)}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    cols = [COL_PDM, "Descrição", "Valor Empenhado", "Limite da Dispensa", "Saldo para contratação"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    def fmt_moeda(v):
        if pd.isna(v):
            return ""
        return "R$ " + (f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    df_pdf = df.copy()
    for c in cols[2:]:
        df_pdf[c] = df_pdf[c].apply(fmt_moeda)

    header = [wrap_header(c) for c in cols]
    table_data = [header]

    saldo_values = df["Saldo para contratação"].fillna(0).tolist() if "Saldo para contratação" in df.columns else [0]*len(df)

    for _, row in df_pdf[cols].iterrows():
        row_data = []
        for i, c in enumerate(cols):
            if i == 1:
                row_data.append(wrap_desc(row[c]))
            else:
                row_data.append(wrap_data(row[c]))
        table_data.append(row_data)

    col_widths = [
        0.8 * inch,  # CATSER
        2.5 * inch,  # Descrição
        1.0 * inch,  # Valor Empenhado
        1.0 * inch,  # Limite da Dispensa
        1.0 * inch,  # Saldo
    ]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
    ]

    for i, saldo in enumerate(saldo_values, 1):
        if saldo <= 0:
            table_styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#ffcccc")))
            table_styles.append(("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#cc0000")))

    tbl.setStyle(TableStyle(table_styles))
    story.append(tbl)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"limite_gasto_itajuba_pdm_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

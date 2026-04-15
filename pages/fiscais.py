
import dash
from dash import html, dcc, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
from datetime import datetime, timedelta
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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib import colors
from pytz import timezone
import os
import threading
import pickle

from utils.runtime import format_datetime_sp, get_cache_dir, now_sp

dash.register_page(
    __name__,
    path="/fiscais",
    name="Fiscais",
    title="Fiscais",
)

URL_FISCAIS = (
    "https://docs.google.com/spreadsheets/d/"
    "17nBhvSoCeK3hNgCj2S57q3pF2Uxj6iBpZDvCX481KcU/"
    "gviz/tq?tqx=out:csv&sheet=Fiscais"
)

COL_SETOR = "Setor"
COL_CONTRATO = "CONTRATO"
COL_OBJETO = "OBJETO"
COL_CONTRATADA = "CONTRATADA"
COL_FINAL_VIG = "Unnamed: 16"
COL_LINK_COMPRASNET = "COMPRASNET Contratos"


def carregar_dados_fiscais():
    df = pd.read_csv(URL_FISCAIS, skiprows=3, header=0)
    df.columns = [c.strip() for c in df.columns]

    col_servidores_raw = [c for c in df.columns if c.startswith("SERVIDOR")]

    cols_keep = [
        COL_SETOR,
        COL_CONTRATO,
        COL_OBJETO,
        COL_CONTRATADA,
        COL_FINAL_VIG,
        COL_LINK_COMPRASNET,
    ] + col_servidores_raw
    cols_keep = [c for c in cols_keep if c in df.columns]
    df = df[cols_keep]

    df = df.rename(
        columns={
            COL_SETOR: "Setor",
            COL_CONTRATO: "Contrato",
            COL_OBJETO: "Objeto",
            COL_CONTRATADA: "Contratada",
            COL_FINAL_VIG: "Final da Vigência",
            COL_LINK_COMPRASNET: "Link Comprasnet",
        }
    )

    if col_servidores_raw:
        todos_serv = pd.Series(df[col_servidores_raw].values.ravel("K"), dtype="object")
        servidores_unicos = sorted(
            s.strip() for s in todos_serv.unique()
            if isinstance(s, str) and s.strip()
        )
    else:
        servidores_unicos = []

    if col_servidores_raw:
        def junta_servidores(row):
            nomes = []
            for c in col_servidores_raw:
                v = row.get(c)
                if isinstance(v, str):
                    v = v.strip()
                else:
                    v = ""
                if v:
                    nomes.append(v)
            return "; ".join(nomes)

        df["Servidores"] = df.apply(junta_servidores, axis=1)
    else:
        df["Servidores"] = ""

    df["_vigencia_dt"] = pd.to_datetime(df["Final da Vigência"], dayfirst=True, errors="coerce")
    hoje = datetime.now().date()

    def calcular_status(data_final):
        if pd.isna(data_final):
            return ""
        dias = (data_final.date() - hoje).days
        if dias > 10:
            return "Vigente"
        if dias < 0:
            return "Vencido"
        return "Próximo do Vencimento"

    df["Status"] = df["_vigencia_dt"].apply(calcular_status)
    df = df[df["Status"].astype(str).str.strip() != ""]
    df = df[df["Status"] != "Vencido"]

    def split_contrato(valor):
        try:
            num, ano = str(valor).strip().split("/")
            return int(ano), int(num)
        except Exception:
            return (0, 0)

    df["_contrato_ano"] = df["Contrato"].apply(lambda x: split_contrato(x)[0])
    df["_contrato_num"] = df["Contrato"].apply(lambda x: split_contrato(x)[1])
    df["Final da Vigência"] = df["_vigencia_dt"].dt.strftime("%d/%m/%Y").fillna("")

    df._lista_servidores_unicos = servidores_unicos
    return df


CACHE_TTL_MINUTOS = 60
_CACHE_LOCK = threading.Lock()
_DF_CACHE = None
_DF_CACHE_AT = None

_CACHE_DIR = os.path.join(
    str(get_cache_dir("fiscais")),
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_FILE = os.path.join(_CACHE_DIR, "df_fiscais.pkl")
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


def get_df_fiscais(force: bool = False):
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
                    serv = getattr(_DF_CACHE, "_lista_servidores_unicos", [])
                    return _DF_CACHE, f"Dados carregados do cache em disco ({_fmt_dt(at_disk)}).", serv

            if force or stale2:
                df = carregar_dados_fiscais()
                _DF_CACHE = df
                _DF_CACHE_AT = now2
                _save_disk_cache(df, now2)
                serv = getattr(_DF_CACHE, "_lista_servidores_unicos", [])
                return _DF_CACHE, f"Dados recarregados da planilha ({_fmt_dt(_now_sp())}).", serv

    serv = getattr(_DF_CACHE, "_lista_servidores_unicos", []) if _DF_CACHE is not None else []
    return _DF_CACHE, f"Dados em cache (memória) — verificado em {_fmt_dt(_now_sp())}.", serv


dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "0px",
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

page_style = {"padding": "14px", "backgroundColor": "#f6f8fb", "minHeight": "100vh"}
card_shell_style = {
    "backgroundColor": "white",
    "border": "1px solid #e6ebf2",
    "borderRadius": "14px",
    "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
}


def filtrar_fiscais(df_base, servidores_drop, contrato_texto, objeto_texto, contratada_drop):
    dff = df_base.copy()

    if servidores_drop:
        termo = str(servidores_drop).strip().lower()
        dff = dff[dff["Servidores"].astype(str).str.lower().str.contains(termo, na=False)]

    if contrato_texto and str(contrato_texto).strip():
        termo = str(contrato_texto).strip().lower()
        dff = dff[dff["Contrato"].astype(str).str.lower().str.contains(termo, na=False)]

    if objeto_texto and str(objeto_texto).strip():
        termo = str(objeto_texto).strip().lower()
        dff = dff[dff["Objeto"].astype(str).str.lower().str.contains(termo, na=False)]

    if contratada_drop:
        dff = dff[dff["Contratada"] == contratada_drop]

    dff = dff[dff["Status"].astype(str).str.strip() != ""]
    dff = dff[dff["Status"] != "Vencido"]

    return dff


layout = html.Div(
    style=page_style,
    children=[
        dcc.Location(id="url"),
        html.Div(
            id="barra_filtros_fiscais",
            className="filtros-sticky",
            style={**card_shell_style, "padding": "14px 16px", "marginBottom": "14px"},
            children=[
                html.Div(
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "2fr 2fr 1fr 1fr",
                        "gap": "12px",
                        "alignItems": "end",
                    },
                    children=[
                        html.Div(
                            children=[
                                html.Label("Servidores"),
                                dcc.Dropdown(
                                    id="filtro_servidores_dropdown_fis",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione um servidor...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            children=[
                                html.Label("Contratada"),
                                dcc.Dropdown(
                                    id="filtro_contratada_dropdown_fis",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione uma contratada...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        html.Div(
                            children=[
                                html.Label("Contrato"),
                                dcc.Input(
                                    id="filtro_contrato_texto_fis",
                                    type="text",
                                    placeholder="Digite parte do contrato",
                                    style={"width": "100%"},
                                ),
                            ],
                        ),
                        html.Div(
                            children=[
                                html.Label("Objeto"),
                                dcc.Input(
                                    id="filtro_objeto_texto",
                                    type="text",
                                    placeholder="Digite parte do objeto",
                                    style={"width": "100%"},
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    style={
                        "display": "flex",
                        "gap": "12px",
                        "alignItems": "center",
                        "marginTop": "12px",
                        "flexWrap": "wrap",
                    },
                    children=[
                        html.Button(
                            "Limpar filtros",
                            id="btn_limpar_filtros_fis",
                            n_clicks=0,
                            style=botao_limpar_style,
                        ),
                        html.Button(
                            "Atualizar Dados",
                            id="btn_reload_fiscais",
                            n_clicks=0,
                            style=botao_style,
                        ),
                        html.Button(
                            "Baixar Relatório PDF",
                            id="btn_download_relatorio_fis",
                            n_clicks=0,
                            style=botao_pdf_style,
                        ),
                        dcc.Download(id="download_relatorio_fis"),
                        html.Div(
                            id="info-atualizacao-fiscais",
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
        html.Div(
            style={**card_shell_style, "padding": "16px"},
            children=[
                dash_table.DataTable(
            id="tabela_fiscais",
            columns=[
                {"name": "Contrato", "id": "Contrato_markdown", "presentation": "markdown"},
                {"name": "Setor", "id": "Setor"},
                {"name": "Objeto", "id": "Objeto"},
                {"name": "Contratada", "id": "Contratada"},
                {"name": "Final da Vigência", "id": "Final da Vigência"},
                {"name": "Servidores", "id": "Servidores"},
            ],
            data=[],
            sort_action="custom",
            sort_mode="single",
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
                "border": "1px solid #e5e7eb",
            },
            style_header={
                "fontWeight": "bold",
                "backgroundColor": "#0b2b57",
                "color": "white",
                "textAlign": "center",
                "position": "sticky",
                "top": 0,
                "zIndex": 5,
                "padding": "12px 8px",
            },
            style_cell_conditional=[
                {"if": {"column_id": "Contrato_markdown"}, "textAlign": "center"},
            ],
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
                {"if": {"row_index": "even"}, "backgroundColor": "white"},
            ],
            css=[{"selector": "p", "rule": "margin: 0; text-align: center;"}],
        ),
            ],
        ),
        dcc.Store(id="store_dados_fis"),
        dcc.Store(id="store-reload-fiscais"),
        dcc.Interval(id="interval-reload-fiscais", interval=60 * 60 * 1000, n_intervals=0),
    ],
)


@dash.callback(
    Output("store-reload-fiscais", "data"),
    Output("info-atualizacao-fiscais", "children"),
    Output("filtro_servidores_dropdown_fis", "options"),
    Output("filtro_contratada_dropdown_fis", "options"),
    Input("url", "pathname"),
    Input("interval-reload-fiscais", "n_intervals"),
    Input("btn_reload_fiscais", "n_clicks"),
)
def carregar_ao_abrir_interval_ou_recarregar(pathname, _n_intervals, n_clicks):
    if pathname != "/fiscais":
        raise PreventUpdate

    force = bool(n_clicks) and n_clicks > 0
    df, status_msg, serv_unicos = get_df_fiscais(force=force)

    op_servidores = [{"label": s, "value": s} for s in (serv_unicos or [])]

    op_contratada = []
    if df is not None and not df.empty and "Contratada" in df.columns:
        op_contratada = [
            {"label": e, "value": e}
            for e in sorted(df["Contratada"].dropna().unique())
            if str(e).strip()
        ]

    msg = html.Div([html.B("Dados disponíveis. "), html.Span(status_msg)])
    return {"ts": datetime.now().isoformat()}, msg, op_servidores, op_contratada


@dash.callback(
    Output("tabela_fiscais", "data"),
    Output("store_dados_fis", "data"),
    Input("store-reload-fiscais", "data"),
    Input("filtro_servidores_dropdown_fis", "value"),
    Input("filtro_contrato_texto_fis", "value"),
    Input("filtro_objeto_texto", "value"),
    Input("filtro_contratada_dropdown_fis", "value"),
    Input("tabela_fiscais", "sort_by"),
)
def atualizar_tabela_fiscais(_reload, servidores_drop, contrato_texto, objeto_texto, contratada_drop, sort_by):
    df_base, _, _ = get_df_fiscais(force=False)
    if df_base is None or df_base.empty:
        return [], []

    dff = filtrar_fiscais(df_base, servidores_drop, contrato_texto, objeto_texto, contratada_drop).copy()

    def mk_link(row):
        url = row.get("Link Comprasnet")
        contrato = row.get("Contrato")
        if isinstance(url, str) and url.strip() and isinstance(contrato, str) and contrato.strip():
            u = url.strip()
            if u.startswith(("http://", "https://")):
                return f"[{contrato.strip()}]({u})"
        return ""

    dff["Contrato_markdown"] = dff.apply(mk_link, axis=1)
    dff = dff[dff["Contrato_markdown"].astype(str).str.strip() != ""]

    if sort_by:
        col = sort_by[0]["column_id"]
        asc = sort_by[0]["direction"] == "asc"

        if col == "Contrato_markdown":
            dff = dff.sort_values(by=["_contrato_ano", "_contrato_num"], ascending=[asc, asc])
        elif col == "Final da Vigência":
            dff = dff.sort_values(by="_vigencia_dt", ascending=asc)
        elif col in dff.columns:
            dff = dff.sort_values(by=col, ascending=asc, na_position="last")
    else:
        dff = dff.sort_values(by="_vigencia_dt", ascending=False, na_position="last")

    cols = [
        "Contrato_markdown",
        "Setor",
        "Objeto",
        "Contratada",
        "Final da Vigência",
        "Servidores",
    ]
    return dff[cols].to_dict("records"), dff.to_dict("records")


@dash.callback(
    Output("filtro_servidores_dropdown_fis", "options", allow_duplicate=True),
    Output("filtro_contratada_dropdown_fis", "options", allow_duplicate=True),
    Input("store-reload-fiscais", "data"),
    Input("filtro_servidores_dropdown_fis", "value"),
    Input("filtro_contrato_texto_fis", "value"),
    Input("filtro_objeto_texto", "value"),
    Input("filtro_contratada_dropdown_fis", "value"),
    prevent_initial_call=True,
)
def atualizar_opcoes_filtros_fis(_reload, servidores_drop, contrato_texto, objeto_texto, contratada_drop):
    df_base, _, serv_unicos = get_df_fiscais(force=False)
    if df_base is None or df_base.empty:
        return [], []

    dff = filtrar_fiscais(df_base, servidores_drop, contrato_texto, objeto_texto, contratada_drop)

    servidores_list = []
    for serv_str in dff["Servidores"].unique():
        if isinstance(serv_str, str) and serv_str.strip():
            for s in serv_str.split(";"):
                s = s.strip()
                if s and s not in servidores_list:
                    servidores_list.append(s)
    servidores_list.sort()

    base = servidores_list if servidores_list else (serv_unicos or [])
    op_servidores = [{"label": s, "value": s} for s in base]

    op_contratada = [
        {"label": e, "value": e}
        for e in sorted(dff["Contratada"].dropna().unique())
        if str(e).strip()
    ]

    return op_servidores, op_contratada


@dash.callback(
    Output("filtro_servidores_dropdown_fis", "value"),
    Output("filtro_contrato_texto_fis", "value"),
    Output("filtro_objeto_texto", "value"),
    Output("filtro_contratada_dropdown_fis", "value"),
    Input("btn_limpar_filtros_fis", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_fis(_n):
    return None, None, None, None


wrap_style_data = ParagraphStyle(
    name="wrap_fiscais_data",
    fontSize=7,
    leading=8,
    alignment=TA_CENTER,
    textColor=colors.black,
)

wrap_style_header = ParagraphStyle(
    name="wrap_fiscais_header",
    fontSize=7,
    leading=8,
    alignment=TA_CENTER,
    textColor=colors.white,
)


def wrap_data(text):
    return Paragraph(str(text), wrap_style_data)


def wrap_header(text):
    return Paragraph(str(text), wrap_style_header)


@dash.callback(
    Output("download_relatorio_fis", "data"),
    Input("btn_download_relatorio_fis", "n_clicks"),
    State("store_dados_fis", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_fiscais(n, dados_fis):
    if not n or not dados_fis:
        return None

    df = pd.DataFrame(dados_fis)

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
            [[
                Paragraph(
                    data_hora,
                    ParagraphStyle(
                        "data_topo_fiscais",
                        fontSize=9,
                        alignment=TA_RIGHT,
                        textColor="#333333",
                    ),
                )
            ]],
            colWidths=[pagesize[0] - 0.6 * inch],
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    logo_esq = (
        Image("assets/brasaobrasil.png", 1.2 * inch, 1.2 * inch)
        if os.path.exists("assets/brasaobrasil.png")
        else ""
    )
    logo_dir = (
        Image("assets/simbolo_RGB.png", 1.2 * inch, 1.2 * inch)
        if os.path.exists("assets/simbolo_RGB.png")
        else ""
    )

    texto_instituicao = (
        "<b><font color='#0b2b57' size='13'>Ministério da Educação</font></b><br/>"
        "<b><font color='#0b2b57' size='13'>Universidade Federal de Itajubá</font></b><br/>"
        "<font color='#0b2b57' size='11'>Diretoria de Compras e Contratos</font>"
    )

    instituicao = Paragraph(
        texto_instituicao,
        ParagraphStyle("instituicao_fiscais", alignment=TA_CENTER, leading=16),
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
        "RELATÓRIO DE FISCAIS DE CONTRATOS",
        ParagraphStyle(
            "titulo_fiscais",
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

    cols = ["Setor", "Contrato", "Objeto", "Contratada", "Final da Vigência", "Servidores"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df_pdf = df.copy()
    header = [wrap_header(c) for c in cols]
    table_data = [header]

    for _, row in df_pdf[cols].iterrows():
        table_data.append([wrap_data(row[c]) for c in cols])

    col_widths = [
        0.75 * inch,
        0.85 * inch,
        2.3 * inch,
        1.9 * inch,
        0.9 * inch,
        1.9 * inch,
    ]

    tbl = Table(table_data, colWidths=col_widths[: len(cols)], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
            ]
        )
    )
    story.append(tbl)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"fiscais_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

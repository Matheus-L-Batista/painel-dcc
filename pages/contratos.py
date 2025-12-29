import dash
from dash import html, dcc, dash_table, Input, Output, State
import pandas as pd
from datetime import datetime

from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/contratos",
    name="Contratos",
    title="Contratos",
)

# --------------------------------------------------
# URL da planilha de Contratos
# --------------------------------------------------
URL_CONTRATOS = (
    "https://docs.google.com/spreadsheets/d/"
    "17nBhvSoCeK3hNgCj2S57q3pF2Uxj6iBpZDvCX481KcU/"
    "gviz/tq?tqx=out:csv&sheet=Grupo%20da%20Cont."
)

# nomes exatos das colunas originais no CSV
COL_CONTRATO = "Contrato"
COL_SETOR = "Setor"
COL_MENU_GRUPO = "MENU Grupo"
COL_OBJETO_ORIG = (
    "UNIVERSIDADE FEDERAL DE ITAJUBÁ Diretoria de Compras e Contratos "
    "Campus Itajubá CONTRATOS ATIVOS - ALIMENTAÇÃO DO BI Objeto"
)
COL_EMPRESA = "Empresa Contratada"
COL_INICIO_VIG = "Início da Vigência"
COL_TERMINO_EXEC = "Término da Execução"
COL_TERMINO_VIG = "Termino da Vigência"  # igual na planilha
COL_LINK_COMPRASNET = "Comprasnet Contratos"

# --------------------------------------------------
# Carga e tratamento dos dados
# --------------------------------------------------
def carregar_dados_contratos():
    df = pd.read_csv(URL_CONTRATOS, header=0)
    df.columns = [c.strip() for c in df.columns]

    if COL_LINK_COMPRASNET not in df.columns:
        df[COL_LINK_COMPRASNET] = ""

    df = df.rename(
        columns={
            COL_CONTRATO: "Contrato",
            COL_SETOR: "Setor",
            COL_MENU_GRUPO: "Grupo",
            COL_OBJETO_ORIG: "Objeto",
            COL_EMPRESA: "Empresa Contratada",
            COL_INICIO_VIG: "Início da Vigência",
            COL_TERMINO_EXEC: "Término da Execução",
            COL_TERMINO_VIG: "Término da Vigência",
            COL_LINK_COMPRASNET: "Link Comprasnet",
        }
    )

    for col in ["Início da Vigência", "Término da Execução", "Término da Vigência"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    hoje = datetime.now().date()

    def calcular_status(data_termino_exec):
        if pd.isna(data_termino_exec):
            return ""
        dias = (data_termino_exec.date() - hoje).days
        if dias > 10:
            return "Vigente"
        if dias < 0:
            return "Vencido"
        return "Próximo do Vencimento"

    df["Status da Vigência"] = df["Término da Execução"].apply(calcular_status)

    for col in ["Início da Vigência", "Término da Execução", "Término da Vigência"]:
        if col in df.columns:
            df[col] = df[col].dt.strftime("%d/%m/%Y").fillna("")

    return df


df_contratos_base = carregar_dados_contratos()

dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    children=[
        html.Div(
            id="barra_filtros_contratos",
            className="filtros-sticky",
            children=[
                # Linha 1: Contrato + Setor (texto e dropdown)
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
                                html.Label("Contrato (digitação)"),
                                dcc.Input(
                                    id="filtro_contrato_texto",
                                    type="text",
                                    placeholder="Digite parte do contrato",
                                    style={"width": "100%", "marginBottom": "6px"},
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Contrato"),
                                dcc.Dropdown(
                                    id="filtro_contrato_dropdown",
                                    options=[
                                        {"label": c, "value": c}
                                        for c in sorted(
                                            df_contratos_base["Contrato"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(c).strip() != ""
                                    ],
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
                                html.Label("Setor (digitação)"),
                                dcc.Input(
                                    id="filtro_setor_texto_ct",
                                    type="text",
                                    placeholder="Digite parte do setor",
                                    style={"width": "100%", "marginBottom": "6px"},
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Setor"),
                                dcc.Dropdown(
                                    id="filtro_setor_dropdown_ct",
                                    options=[
                                        {"label": s, "value": s}
                                        for s in sorted(
                                            df_contratos_base["Setor"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(s).strip() != ""
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
                # Linha 2: Grupo + Empresa (texto e dropdown) + Status + botões
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-end",
                        "marginTop": "4px",
                    },
                    children=[

                        # Empresa (digitação)
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Empresa (digitação)"),
                                dcc.Input(
                                    id="filtro_empresa_texto",
                                    type="text",
                                    placeholder="Digite parte do nome da empresa",
                                    style={"width": "100%", "marginBottom": "6px"},
                                ),
                            ],
                        ),
                        # Empresa (dropdown)
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Empresa Contratada"),
                                dcc.Dropdown(
                                    id="filtro_empresa",
                                    options=[
                                        {"label": e, "value": e}
                                        for e in sorted(
                                            df_contratos_base["Empresa Contratada"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(e).strip() != ""
                                    ],
                                    value=None,
                                    placeholder="Todas",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                                                # Grupo
                        html.Div(
                            style={"minWidth": "200px", "flex": "0 0 220px"},
                            children=[
                                html.Label("Grupo"),
                                dcc.Dropdown(
                                    id="filtro_grupo",
                                    options=[
                                        {"label": g, "value": g}
                                        for g in sorted(
                                            df_contratos_base["Grupo"]
                                            .dropna()
                                            .unique()
                                        )
                                        if str(g).strip() != ""
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Status da Vigência
                        html.Div(
                            style={"minWidth": "200px", "flex": "0 0 220px"},
                            children=[
                                html.Label("Status da Vigência"),
                                dcc.Dropdown(
                                    id="filtro_status_vig",
                                    options=[
                                        {"label": "Vigente", "value": "Vigente"},
                                        {
                                            "label": "Próximo do Vencimento",
                                            "value": "Próximo do Vencimento",
                                        },
                                        {"label": "Vencido", "value": "Vencido"},
                                    ],
                                    value=None,
                                    placeholder="Todos",
                                    clearable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Botões ao lado de Status
                        html.Div(
                            style={
                                "display": "flex",
                                "gap": "10px",
                                "flexShrink": 0,
                            },
                            children=[
                                html.Button(
                                    "Limpar filtros",
                                    id="btn_limpar_filtros_contratos",
                                    n_clicks=0,
                                    className="filtros-button",
                                ),
                                html.Button(
                                    "Baixar Relatório PDF",
                                    id="btn_download_relatorio_contratos",
                                    n_clicks=0,
                                    className="filtros-button",
                                ),
                                dcc.Download(id="download_relatorio_contratos"),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        html.H4("Contratos – Alimentação do BI"),
        dash_table.DataTable(
            id="tabela_contratos",
            columns=[
                {
                    "name": "Contrato",
                    "id": "Contrato_markdown",
                    "presentation": "markdown",
                },
                {"name": "Setor", "id": "Setor"},
                {"name": "Grupo", "id": "Grupo"},
                {"name": "Objeto", "id": "Objeto"},
                {"name": "Empresa Contratada", "id": "Empresa Contratada"},
                {"name": "Início da Vigência", "id": "Início da Vigência"},
                {"name": "Término da Execução", "id": "Término da Execução"},
                {"name": "Término da Vigência", "id": "Término da Vigência"},
                {"name": "Status da Vigência", "id": "Status da Vigência"},
            ],
            data=[],
            row_selectable=False,
            cell_selectable=False,
            style_table={
                "overflowX": "auto",
                "overflowY": "auto",
                "height": "calc(100vh - 200px)",
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
        ),
        dcc.Store(id="store_dados_contratos"),
    ]
)

# --------------------------------------------------
# Callback: filtros
# --------------------------------------------------
@dash.callback(
    Output("tabela_contratos", "data"),
    Output("store_dados_contratos", "data"),
    Input("filtro_contrato_texto", "value"),
    Input("filtro_contrato_dropdown", "value"),
    Input("filtro_setor_texto_ct", "value"),
    Input("filtro_setor_dropdown_ct", "value"),
    Input("filtro_grupo", "value"),
    Input("filtro_empresa_texto", "value"),
    Input("filtro_empresa", "value"),
    Input("filtro_status_vig", "value"),
)
def atualizar_tabela_contratos(
    contrato_texto,
    contrato_drop,
    setor_texto,
    setor_drop,
    grupo,
    empresa_texto,
    empresa_drop,
    status_vig,
):
    dff = df_contratos_base.copy()

    if contrato_texto and str(contrato_texto).strip():
        termo = str(contrato_texto).strip().lower()
        dff = dff[
            dff["Contrato"].astype(str).str.lower().str.contains(termo, na=False)
        ]

    if contrato_drop:
        dff = dff[dff["Contrato"] == contrato_drop]

    if setor_texto and str(setor_texto).strip():
        termo = str(setor_texto).strip().lower()
        dff = dff[
            dff["Setor"].astype(str).str.lower().str.contains(termo, na=False)
        ]

    if setor_drop:
        dff = dff[dff["Setor"] == setor_drop]

    if grupo:
        dff = dff[dff["Grupo"] == grupo]

    if empresa_texto and str(empresa_texto).strip():
        termo = str(empresa_texto).strip().lower()
        dff = dff[
            dff["Empresa Contratada"]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        ]

    if empresa_drop:
        dff = dff[dff["Empresa Contratada"] == empresa_drop]

    if status_vig:
        dff = dff[dff["Status da Vigência"] == status_vig]

    dff = dff.copy()

    def mk_link(row):
        url = row.get("Link Comprasnet")
        contrato = row.get("Contrato")
        if isinstance(url, str) and url.strip() and isinstance(contrato, str):
            return f"[{contrato}]({url.strip()})"
        return str(contrato) if contrato is not None else ""

    dff["Contrato_markdown"] = dff.apply(mk_link, axis=1)

    cols = [
        "Contrato_markdown",
        "Setor",
        "Grupo",
        "Objeto",
        "Empresa Contratada",
        "Início da Vigência",
        "Término da Execução",
        "Término da Vigência",
        "Status da Vigência",
    ]
    cols = [c for c in cols if c in dff.columns]

    return dff[cols].to_dict("records"), dff.to_dict("records")

# --------------------------------------------------
# Callback: limpar filtros
# --------------------------------------------------
@dash.callback(
    Output("filtro_contrato_texto", "value"),
    Output("filtro_contrato_dropdown", "value"),
    Output("filtro_setor_texto_ct", "value"),
    Output("filtro_setor_dropdown_ct", "value"),
    Output("filtro_grupo", "value"),
    Output("filtro_empresa_texto", "value"),
    Output("filtro_empresa", "value"),
    Output("filtro_status_vig", "value"),
    Input("btn_limpar_filtros_contratos", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_contratos(n):
    return None, None, None, None, None, None, None, None

# --------------------------------------------------
# Callback: gerar PDF de contratos
# --------------------------------------------------
wrap_style = ParagraphStyle(
    name="wrap_contratos",
    fontSize=8,
    leading=10,
    spaceAfter=4,
)

def wrap(text):
    return Paragraph(str(text), wrap_style)

@dash.callback(
    Output("download_relatorio_contratos", "data"),
    Input("btn_download_relatorio_contratos", "n_clicks"),
    State("store_dados_contratos", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_contratos(n, dados_contratos):
    if not n or not dados_contratos:
        return None

    df = pd.DataFrame(dados_contratos)

    buffer = BytesIO()
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    titulo = Paragraph(
        "Relatório de Contratos – Alimentação do BI",
        ParagraphStyle(
            "titulo_contratos",
            fontSize=16,
            alignment=TA_CENTER,
            textColor="#0b2b57",
        ),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(f"Total de registros: {len(df)}", styles["Normal"])
    )
    story.append(Spacer(1, 0.15 * inch))

    cols = [
        "Contrato",
        "Setor",
        "Grupo",
        "Objeto",
        "Empresa Contratada",
        "Início da Vigência",
        "Término da Execução",
        "Término da Vigência",
        "Status da Vigência",
    ]
    cols = [c for c in cols if c in df.columns]

    df_pdf = df.copy()

    header = cols
    table_data = [header]
    for _, row in df_pdf[cols].iterrows():
        table_data.append([wrap(row[c]) for c in cols])

    page_width = pagesize[0] - 0.6 * inch
    col_width = page_width / max(1, len(header))
    col_widths = [col_width] * len(header)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (0, 0), (-1, -1), True),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    story.append(tbl)
    doc.build(story)
    buffer.seek(0)

    from dash import dcc

    return dcc.send_bytes(buffer.getvalue(), "contratos_paisagem.pdf")

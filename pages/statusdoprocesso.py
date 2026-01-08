import dash
from dash import html, dcc, dash_table, Input, Output, State
import pandas as pd

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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib import colors
from datetime import datetime
from pytz import timezone
import os


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

    data_cols = [c for c in df.columns if c.startswith("Data Mov")]

    grupos = []

    grupo0 = df[col_fixas + ["Data Mov", "E/S", "Deptº", "Ação"]].copy()
    grupos.append(grupo0)

    for col in data_cols:
        if col == "Data Mov":
            continue

        suf = col[len("Data Mov"):]
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

    t_aux = tabela_unida.replace({None: pd.NA}).fillna("")
    mask_nao_vazia = t_aux.apply(
        lambda row: any(v not in ("", None) for v in row.values), axis=1
    )
    tabela_unida = tabela_unida[mask_nao_vazia].copy()

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


df_status = carregar_dados_status()

dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

df_proc_opts = df_status[["Processo", "Linha"]].copy()
df_proc_opts = df_proc_opts.dropna(subset=["Processo"])
df_proc_opts["Linha_num"] = pd.to_numeric(df_proc_opts["Linha"], errors="coerce")
df_proc_opts = df_proc_opts.sort_values("Linha_num", ascending=False)
df_proc_opts = df_proc_opts.drop_duplicates(subset=["Processo"], keep="first")

processo_options = [
    {"label": row["Processo"], "value": row["Processo"]}
    for _, row in df_proc_opts.iterrows()
]


# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    children=[
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
                        html.Div(
                            style={"minWidth": "220px", "flex": "1 1 260px"},
                            children=[
                                html.Label("Processo (seleção)"),
                                dcc.Dropdown(
                                    id="filtro_processo",
                                    options=processo_options,
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
                html.Div(
                    style={"marginTop": "4px"},
                    children=[
                        html.Button(
                            "Limpar filtros",
                            id="btn_limpar_filtros_status",
                            n_clicks=0,
                            className="filtros-button",
                        ),
                        html.Button(
                            "Baixar Relatório PDF",
                            id="btn_download_relatorio_status",
                            n_clicks=0,
                            className="filtros-button",
                            style={"marginLeft": "10px"},
                        ),
                        dcc.Download(id="download_relatorio_status"),
                    ],
                ),
            ],
        ),
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "10px",
                "marginTop": "10px",
            },
            children=[
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
                            style_cell_conditional=[
                                {"if": {"column_id": "Data Mov"}, "width": "15%"},
                                {"if": {"column_id": "E/S"}, "width": "15%"},
                                {
                                    "if": {"column_id": "Ação"},
                                    "width": "50%",
                                    "textAlign": "center",
                                },
                                {"if": {"column_id": "Deptº"}, "width": "20%"},
                            ],
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": "#0b2b57",
                                "color": "white",
                                "textAlign": "center",
                            },
                            style_data_conditional=[
                                {
                                    "if": {"row_index": 0},
                                    "backgroundColor": "#ff9800",
                                    "fontWeight": "bold",
                                    "color": "white",
                                }
                            ],
                        ),
                    ],
                ),
            ],
        ),
        dcc.Store(id="store_dados_status"),
    ]
)


# --------------------------------------------------
# Callbacks principais
# --------------------------------------------------
@dash.callback(
    Output("tabela_status_esquerda", "data"),
    Output("tabela_status_direita", "data"),
    Output("store_dados_status", "data"),
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

    if proc_texto and str(proc_texto).strip():
        termo = str(proc_texto).strip()
        dff = dff[
            dff["Processo"].astype(str).str.contains(termo, case=False, na=False)
        ]

    if proc_select:
        dff = dff[dff["Processo"] == proc_select]

    if requisitante:
        dff = dff[dff["Requisitante"] == requisitante]

    if objeto:
        dff = dff[dff["Objeto"] == objeto]

    if modalidade:
        dff = dff[dff["Modalidade"] == modalidade]

    try:
        dff["Linha_ordenacao"] = pd.to_numeric(dff["Linha"], errors="coerce")
    except Exception:
        dff["Linha_ordenacao"] = dff["Linha"]
    dff = dff.sort_values("Linha_ordenacao", ascending=False)

    mask_proc_valido = dff["Processo"].astype(str).str.strip().ne("")
    dff_esq = dff[mask_proc_valido].copy()
    dff_esq = dff_esq.drop_duplicates(subset=["Processo"], keep="first")

    dados_esquerda = dff_esq[
        ["Processo", "Requisitante", "Objeto", "Modalidade", "Linha"]
    ].to_dict("records")

    # --------- tabela direita (removendo vazios e <NA>) ----------
    dff_dir = dff.copy()

    for c in ["Data Mov", "E/S", "Ação", "Deptº"]:
        dff_dir[c] = dff_dir[c].astype(str).str.strip()

    mask_acao_valida = (
        dff_dir["Ação"].ne("")
        & dff_dir["Ação"].str.lower().ne("none")
        & dff_dir["Ação"].str.lower().ne("nan")
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

    cols_check = ["Data Mov", "E/S", "Ação", "Deptº"]
    mask_linha_valida = dff_dir[cols_check].apply(
        lambda row: any(
            (v_str := str(v).strip()) not in ("", "none", "nan", "<na>")
            for v in row.values
        ),
        axis=1,
    )
    dff_dir = dff_dir[mask_linha_valida].copy()

    dados_direita = dff_dir[["Data Mov", "E/S", "Ação", "Deptº"]].to_dict("records")

    return dados_esquerda, dados_direita, dff_dir.to_dict("records")


# --------------------------------------------------
# Callback: limpar filtros
# --------------------------------------------------
@dash.callback(
    Output("filtro_processo_texto", "value"),
    Output("filtro_processo", "value"),
    Output("filtro_requisitante", "value"),
    Output("filtro_objeto", "value"),
    Output("filtro_modalidade", "value"),
    Input("btn_limpar_filtros_status", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_status(n):
    return None, None, None, None, None


# --------------------------------------------------
# Estilos de texto para PDF
# --------------------------------------------------
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


# --------------------------------------------------
# Callback: gerar relatório PDF
# --------------------------------------------------
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

    df_dir = df_todos.copy()
    if "Ação" in df_dir.columns:
        df_dir["Ação"] = df_dir["Ação"].astype(str).str.strip()
        df_dir = df_dir[df_dir["Ação"] != ""]
        df_dir = df_dir[df_dir["Ação"].str.lower() != "nan"]
        df_dir = df_dir[df_dir["Ação"].str.lower() != "none"]
        df_dir = df_dir[df_dir["Ação"].str.lower() != "<na>"]
        df_dir = df_dir[df_dir["Ação"].notna()]

    if df_esq.empty and df_dir.empty:
        return None

    buffer = BytesIO()
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    tz_br = timezone("America/Sao_Paulo")
    data_hora = datetime.now(tz_br).strftime("%d/%m/%Y %H:%M:%S")

    header_style = ParagraphStyle(
        "header_status",
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.grey,
    )
    story.append(Paragraph(data_hora, header_style))
    story.append(Spacer(1, 0.1 * inch))

    logos_path = []
    if os.path.exists(os.path.join("assets", "brasaobrasil.png")):
        logos_path.append(os.path.join("assets", "brasaobrasil.png"))
    if os.path.exists(os.path.join("assets", "simbolo_RGB.png")):
        logos_path.append(os.path.join("assets", "simbolo_RGB.png"))

    if logos_path:
        logos = []
        for logo_file in logos_path:
            if os.path.exists(logo_file):
                logo = Image(logo_file, width=1.2 * inch, height=1.2 * inch)
                logos.append(logo)

        if logos:
            if len(logos) == 2:
                logo_table = Table(
                    [[logos[0], logos[1]]],
                    colWidths=[
                        pagesize[0] / 2 - 0.15 * inch,
                        pagesize[0] / 2 - 0.15 * inch,
                    ],
                )
            else:
                logo_table = Table(
                    [[logos[0]]],
                    colWidths=[pagesize[0] - 0.3 * inch],
                )

            logo_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(logo_table)
            story.append(Spacer(1, 0.15 * inch))

    titulo = Paragraph(
        "RELATÓRIO DE STATUS DO PROCESSO",
        ParagraphStyle(
            "titulo_status",
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0b2b57"),
            fontName="Helvetica-Bold",
        ),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.15 * inch))

    # ===== TABELA 1: DADOS DO PROCESSO =====
    if not df_esq.empty:
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
        story.append(
            Paragraph(
                f"Total de registros: {len(df_esq)}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.08 * inch))

        cols_esq = ["Processo", "Requisitante", "Objeto", "Modalidade", "Linha"]
        cols_esq = [c for c in cols_esq if c in df_esq.columns]

        df_esq_filtered = df_esq[cols_esq].copy()

        header_esq = cols_esq
        table_data_esq = [header_esq]

        for _, row in df_esq_filtered.iterrows():
            linha = []
            for c in cols_esq:
                valor = str(row[c]).strip() if pd.notna(row[c]) else ""
                if c in ["Objeto"]:
                    linha.append(wrap_pdf(valor))
                else:
                    linha.append(simple_pdf(valor))
            table_data_esq.append(linha)

        col_widths_esq = [
            2.0 * inch,
            1.2 * inch,
            2.5 * inch,
            1.2 * inch,
            0.6 * inch,
        ]

        tbl_esq = Table(table_data_esq, colWidths=col_widths_esq, repeatRows=1)

        style_list_esq = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("FONTWEIGHT", (0, 0), (-1, 0), "bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("WORDWRAP", (0, 0), (-1, -1), True),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#f0f0f0")],
            ),
        ]

        tbl_esq.setStyle(TableStyle(style_list_esq))
        story.append(tbl_esq)
        story.append(Spacer(1, 0.2 * inch))

    # ===== TABELA 2: MOVIMENTAÇÕES =====
    if not df_dir.empty:
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
        story.append(
            Paragraph(
                f"Total de registros: {len(df_dir)}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.08 * inch))

        cols_dir = ["Data Mov", "E/S", "Ação", "Deptº"]
        cols_dir = [c for c in cols_dir if c in df_dir.columns]

        df_dir_copy = df_dir.copy()
        df_dir_copy["Data Mov_dt"] = pd.to_datetime(
            df_dir_copy["Data Mov"], errors="coerce"
        )
        df_dir_copy["ordem_acao"] = (
            df_dir_copy["Ação"].astype(str).str.strip() != "FIM DCC"
        ).astype(int)

        df_dir_copy = df_dir_copy.sort_values(
            by=["Data Mov_dt", "ordem_acao"],
            ascending=[False, True],
            na_position="last",
        )

        df_dir_copy["Data Mov"] = (
            df_dir_copy["Data Mov_dt"].dt.strftime("%d/%m/%Y").fillna("")
        )

        df_dir_copy["Ação"] = df_dir_copy["Ação"].astype(str).str.strip()
        df_dir_copy = df_dir_copy[
            (df_dir_copy["Ação"] != "")
            & (df_dir_copy["Ação"].str.lower() != "none")
            & (df_dir_copy["Ação"].str.lower() != "nan")
            & (df_dir_copy["Ação"].str.lower() != "<na>")
        ]

        cols_check = ["Data Mov", "E/S", "Ação", "Deptº"]
        df_dir_copy = df_dir_copy[
            df_dir_copy[cols_check].apply(
                lambda row: any(
                    (v_str := str(v).strip()) not in ("", "none", "nan", "<na>")
                    for v in row.values
                ),
                axis=1,
            )
        ]

        df_dir_filtered = df_dir_copy[cols_dir].copy()

        header_dir = cols_dir
        table_data_dir = [header_dir]

        for _, row in df_dir_filtered.iterrows():
            linha = []
            for c in cols_dir:
                valor = str(row[c]).strip() if pd.notna(row[c]) else ""
                if c in ["Ação"]:
                    linha.append(wrap_pdf(valor))
                else:
                    linha.append(simple_pdf(valor))
            table_data_dir.append(linha)

        col_widths_dir = [
            1.0 * inch,
            1.0 * inch,
            3.0 * inch,
            1.0 * inch,
        ]

        tbl_dir = Table(table_data_dir, colWidths=col_widths_dir, repeatRows=1)

        style_list_dir = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("FONTWEIGHT", (0, 0), (-1, 0), "bold"),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ff9800")),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
            ("FONTWEIGHT", (0, 1), (-1, 1), "bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("WORDWRAP", (0, 0), (-1, -1), True),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            (
                "ROWBACKGROUNDS",
                (0, 2),
                (-1, -1),
                [colors.white, colors.HexColor("#f0f0f0")],
            ),
        ]

        tbl_dir.setStyle(TableStyle(style_list_dir))
        story.append(tbl_dir)

    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(buffer.getvalue(), "status_processos_paisagem.pdf")

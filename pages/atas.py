import dash
from dash import html, dcc, dash_table
import pandas as pd
from datetime import datetime

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
# URLs das planilhas
# --------------------------------------------------
URL_ATAS_AND = (
    "https://docs.google.com/spreadsheets/d/"
    "1fEWJL85yZg3y-ea-qY29LjQpCDto1vuRxF6OYODqMNE/"
    "gviz/tq?tqx=out:csv&sheet=ATAS%20EM%20ANDAMENTO"
)

URL_ATAS_VIG = (
    "https://docs.google.com/spreadsheets/d/"
    "1fEWJL85yZg3y-ea-qY29LjQpCDto1vuRxF6OYODqMNE/"
    "gviz/tq?tqx=out:csv&sheet=ATAS%20VIGENTES"
)

# --------------------------------------------------
# Carga dos dados
# --------------------------------------------------
def carregar_atas_andamento():
    df = pd.read_csv(URL_ATAS_AND)
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]
    df.columns = [c.strip() for c in df.columns]

    df = df.rename(
        columns={
            "ATAS EM ANDAMENTO": "Atas em Andamento",
            "Situação ": "Situação",
            "Previsão para estar disponível": "Previsão para estar disponível",
        }
    )

    return df[
        [
            c
            for c in [
                "Atas em Andamento",
                "Situação",
                "Previsão para estar disponível",
            ]
            if c in df.columns
        ]
    ]


def carregar_atas_vigentes():
    df = pd.read_csv(URL_ATAS_VIG)
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]
    df.columns = [c.strip() for c in df.columns]

    df = df.rename(columns={"ATAS VIGENTES": "Ata Vigente"})

    if "Data de Término" in df.columns:
        df["Data de Término_dt"] = pd.to_datetime(
            df["Data de Término"], dayfirst=True, errors="coerce"
        )
        hoje = datetime.now().date()
        df = df[df["Data de Término_dt"].dt.date >= hoje]

    if "Link" in df.columns:
        df["Link_markdown"] = df["Link"].apply(
            lambda url: f"[link]({str(url).strip()})" if str(url).strip() else ""
        )
    else:
        df["Link_markdown"] = ""

    return df


df_and = carregar_atas_andamento()
df_vig = carregar_atas_vigentes()

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
}

zebra_style = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#f5f5f5"}
]

datatable_links_css = [
    {"selector": "p", "rule": "margin: 0; text-align: center;"}
]

# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style={"padding": "10px"},
    children=[
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
            data=df_vig[
                [
                    c
                    for c in [
                        "Número",
                        "Ata Vigente",
                        "Data Inicial",
                        "Data de Término",
                        "Link_markdown",
                    ]
                    if c in df_vig.columns
                ]
            ].to_dict("records"),
            style_table={
                "maxHeight": "450px",
                "overflowY": "auto",
                "overflowX": "auto",
            },
            style_cell=cell_style,
            style_header=header_style,
            style_data_conditional=zebra_style,
            css=datatable_links_css,
        ),

        html.H3(
            "Atas em Andamento",
            style={"marginTop": "20px", "textAlign": "center"},
        ),

        dash_table.DataTable(
            id="tabela_atas_andamento",
            columns=[
                {"name": "Atas em Andamento", "id": "Atas em Andamento"},
                {"name": "Situação", "id": "Situação"},
                {
                    "name": "Previsão para estar disponível",
                    "id": "Previsão para estar disponível",
                },
            ],
            data=df_and.to_dict("records"),
            style_table={
                "maxHeight": "220px",
                "overflowY": "auto",
                "overflowX": "auto",
            },
            style_cell=cell_style,
            style_header=header_style,
            style_data_conditional=zebra_style,
        ),
    ],
)

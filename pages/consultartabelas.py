import dash
from dash import html, dash_table
import pandas as pd


dash.register_page(
    __name__,
    path="/consultartabelas",
    name="consultartabelas",
    title="Consultar Tabelas",
)


URL_BI_EXTRATO = (
    "https://docs.google.com/spreadsheets/d/"
    "17nBhvSoCeK3hNgCj2S57q3pF2Uxj6iBpZDvCX481KcU/"
    "gviz/tq?tqx=out:csv&sheet=Grupo%20da%20Cont."
)


def carregar_dados_portarias():
    df = pd.read_csv(URL_BI_EXTRATO)
    df.columns = [c.strip() for c in df.columns]
    return df


def layout():
    try:
        df_portarias_base = carregar_dados_portarias()
        mensagem_erro_carga = None
    except Exception as exc:
        df_portarias_base = pd.DataFrame()
        mensagem_erro_carga = html.Div(
            f"Nao foi possivel carregar a planilha agora: {type(exc).__name__}",
            style={"color": "#b00020", "fontWeight": "bold", "marginBottom": "12px"},
        )

    df_cols = pd.DataFrame(
        {
            "Indice": range(len(df_portarias_base.columns)),
            "Nome da coluna": list(df_portarias_base.columns),
        }
    )

    return html.Div(
        children=[
            mensagem_erro_carga,
            html.H4("Colunas da planilha de Portarias (indice e nome)"),
            dash_table.DataTable(
                id="tabela_colunas_portarias",
                columns=[
                    {"name": "Indice", "id": "Indice"},
                    {"name": "Nome da coluna", "id": "Nome da coluna"},
                ],
                data=df_cols.to_dict("records"),
                style_table={"maxHeight": "300px", "overflowY": "auto"},
                style_cell={
                    "textAlign": "left",
                    "padding": "4px",
                    "fontSize": "12px",
                    "whiteSpace": "normal",
                },
                style_header={
                    "fontWeight": "bold",
                    "backgroundColor": "#0b2b57",
                    "color": "white",
                },
            ),
            html.H4("Tabela de Portarias (amostra)"),
            dash_table.DataTable(
                id="tabela_portarias",
                columns=[{"name": c, "id": c} for c in df_portarias_base.columns],
                data=df_portarias_base.head(20).to_dict("records"),
                row_selectable=False,
                cell_selectable=False,
                style_table={
                    "overflowX": "auto",
                    "overflowY": "auto",
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
                    "position": "sticky",
                    "top": 0,
                    "zIndex": 10,
                },
            ),
        ]
    )

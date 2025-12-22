import dash
from dash import Dash, html, dcc

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,  # boa prática
)
server = app.server


menu_links = [
    {"label": "Passagens DCF", "href": "/passagens-dcf"},
    {"label": "Pagamentos Efetivados", "href": "/pagamentos"},
    {"label": "Dotação Atualizada", "href": "/dotacao"},
    {"label": "Execução Orçamento UNIFEI", "href": "/execucao-orcamento-unifei"},
    {"label": "Naturezas Despesa", "href": "/natureza-despesa-2024"},
    {"label": "Execução TED", "href": "/execucao-ted"},
]


app.layout = html.Div(
    className="app-root",
    children=[
        dcc.Location(id="url"),

        # 🔁 Atualização automática (1x por hora)
        dcc.Interval(
            id="interval-atualizacao",
            interval=60 * 60 * 1000,
            n_intervals=0,
        ),

        html.Div(
            className="app-container",
            children=[
                # SIDEBAR
                html.Div(
                    className="sidebar",
                    children=[
                        html.Div(
                            className="sidebar-header",
                            children=[
                                html.Img(
                                    src="/assets/logo_unifei.png",
                                    className="sidebar-logo",
                                ),
                                html.H2(
                                    "Painéis",
                                    className="sidebar-title",
                                ),
                            ],
                        ),
                        html.Div(
                            id="sidebar-menu",
                            className="sidebar-menu",
                        ),
                    ],
                ),

                # CONTEÚDO PRINCIPAL
                html.Div(
                    className="main-content",
                    children=html.Div(
                        className="page-wrapper",
                        children=dash.page_container,
                    ),
                ),
            ],
        ),
    ],
)


@app.callback(
    dash.Output("sidebar-menu", "children"),
    dash.Input("url", "pathname"),
)
def atualizar_menu(pathname):
    itens = []
    for m in menu_links:
        class_name = (
            "sidebar-button sidebar-button-active"
            if pathname == m["href"]
            else "sidebar-button"
        )
        itens.append(
            dcc.Link(
                m["label"],
                href=m["href"],
                className=class_name,
            )
        )
    return itens


if __name__ == "__main__":
    app.run(debug=True)

import dash
from dash import Dash, html, dcc, callback, Input, Output, State, no_update

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ],
    title="Painel DCC",
)
server = app.server


# =========================================================
# LINKS NORMAIS DO MENU
# =========================================================
menu_links = [
    {"label": "Fiscais", "href": "/fiscais"},
    {"label": "Plano de Contratação Anual", "href": "/pca"},
    {"label": "Controle de Atas", "href": "/atas"},
    # {"label": "Tabela", "href": "/consultartabelas"},
]


# =========================================================
# LAYOUT PRINCIPAL
# =========================================================
app.layout = html.Div(
    className="app-root",
    children=[
        dcc.Location(id="url"),

        # Intervalo global de atualização (1 hora)
        dcc.Interval(
            id="interval-atualizacao",
            interval=60 * 60 * 1000,
            n_intervals=0,
        ),

        html.Div(
            className="app-container",
            children=[
                # =========================================
                # SIDEBAR
                # =========================================
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

                                html.Div(
                                    [
                                        html.Strong(
                                            [
                                                "PARA MELHOR VISUALIZAÇÃO DO PAINEL,",
                                                html.Br(),
                                                "AJUSTE O ZOOM DO NAVEGADOR!",
                                            ]
                                        )
                                    ],
                                    className="zoom-alert",
                                ),

                                html.H2(
                                    "Painéis",
                                    className="sidebar-title",
                                ),
                            ],
                        ),

                        # Stores para controlar expansão manual dos grupos
                        dcc.Store(id="store-contratos", data=False),
                        dcc.Store(id="store-processos", data=False),
                        dcc.Store(id="store-fracionamento", data=False),
                        dcc.Store(id="store-portarias", data=False),

                        html.Div(
                            id="sidebar-menu",
                            className="sidebar-menu",
                        ),
                    ],
                ),

                # =========================================
                # CONTEÚDO PRINCIPAL
                # =========================================
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


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def grupo_expandido(pathname, paths_do_grupo, estado_store):
    """
    Expande o grupo se:
    - a rota atual pertence ao grupo, OU
    - o usuário abriu manualmente o grupo.
    """
    return (pathname in paths_do_grupo) or bool(estado_store)


def montar_grupo(
    titulo,
    btn_id,
    box_id,
    container_class,
    toggle_class,
    content_class,
    subbutton_class,
    subbutton_active_class,
    pathname,
    expandido,
    links,
):
    btn_classes = toggle_class + (" active" if expandido else "")
    box_classes = content_class + (" expanded" if expandido else "")

    return html.Div(
        className=container_class,
        children=[
            html.Div(
                titulo,
                id=btn_id,
                className=btn_classes,
                n_clicks=0,
            ),
            html.Div(
                id=box_id,
                className=box_classes,
                children=[
                    dcc.Link(
                        item["label"],
                        href=item["href"],
                        className=(
                            f"{subbutton_class} {subbutton_active_class}"
                            if pathname == item["href"]
                            else subbutton_class
                        ),
                    )
                    for item in links
                ],
            ),
        ],
    )


# =========================================================
# MENU LATERAL DINÂMICO
# =========================================================
@callback(
    Output("sidebar-menu", "children"),
    Input("url", "pathname"),
    Input("store-contratos", "data"),
    Input("store-processos", "data"),
    Input("store-fracionamento", "data"),
    Input("store-portarias", "data"),
)
def atualizar_menu(
    pathname,
    contratos_open,
    processos_open,
    fracionamento_open,
    portarias_open,
):
    pathname = pathname or "/"

    itens = []

    # =========================
    # Contratos
    # =========================
    contratos_paths = ["/contratos", "/extrato-contrato"]
    contratos_expandido = grupo_expandido(pathname, contratos_paths, contratos_open)

    itens.append(
        montar_grupo(
            titulo="Contratos",
            btn_id="btn-contratos",
            box_id="box-contratos",
            container_class="contratos-container",
            toggle_class="contratos-toggle",
            content_class="contratos-content",
            subbutton_class="contratos-subbutton",
            subbutton_active_class="contratos-subbutton-active",
            pathname=pathname,
            expandido=contratos_expandido,
            links=[
                {"label": "Contratos Vigentes", "href": "/contratos"},
                {"label": "Detalhes Contratuais", "href": "/extrato-contrato"},
            ],
        )
    )

    # =========================
    # Processos
    # =========================
    processos_paths = ["/processos-de-compras", "/statusdoprocesso"]
    processos_expandido = grupo_expandido(pathname, processos_paths, processos_open)

    itens.append(
        montar_grupo(
            titulo="Processos",
            btn_id="btn-processos",
            box_id="box-processos",
            container_class="processos-container",
            toggle_class="processos-toggle",
            content_class="processos-content",
            subbutton_class="processos-subbutton",
            subbutton_active_class="processos-subbutton-active",
            pathname=pathname,
            expandido=processos_expandido,
            links=[
                {"label": "Detalhes dos Processos de Compras", "href": "/processos-de-compras"},
                {"label": "Andamento dos Processos", "href": "/statusdoprocesso"},
            ],
        )
    )

    # =========================
    # Fracionamento
    # =========================
    fracionamento_paths = ["/fracionamento_pdm", "/fracionamento_catser"]
    fracionamento_expandido = grupo_expandido(
        pathname, fracionamento_paths, fracionamento_open
    )

    itens.append(
        montar_grupo(
            titulo="Fracionamento de Despesas",
            btn_id="btn-fracionamento",
            box_id="box-fracionamento",
            container_class="fracionamento-container",
            toggle_class="fracionamento-toggle",
            content_class="fracionamento-content",
            subbutton_class="fracionamento-subbutton",
            subbutton_active_class="fracionamento-subbutton-active",
            pathname=pathname,
            expandido=fracionamento_expandido,
            links=[
                {
                    "label": "Fracionamento de Despesas PDM (Material)",
                    "href": "/fracionamento_pdm",
                },
                {
                    "label": "Fracionamento de Despesas CATSER (Serviço)",
                    "href": "/fracionamento_catser",
                },
            ],
        )
    )

    # =========================
    # Portarias
    # =========================
    portarias_paths = ["/portarias_agentedecompras", "/portarias_planejamento"]
    portarias_expandido = grupo_expandido(pathname, portarias_paths, portarias_open)

    itens.append(
        montar_grupo(
            titulo="Portarias",
            btn_id="btn-portarias",
            box_id="box-portarias",
            container_class="portarias-container",
            toggle_class="portarias-toggle",
            content_class="portarias-content",
            subbutton_class="portarias-subbutton",
            subbutton_active_class="portarias-subbutton-active",
            pathname=pathname,
            expandido=portarias_expandido,
            links=[
                {
                    "label": "Portarias Agente de Compras/ Contratos Tipo Empenho",
                    "href": "/portarias_agentedecompras",
                },
                {
                    "label": "Portarias de Planejamento da Contratação",
                    "href": "/portarias_planejamento",
                },
            ],
        )
    )

    # =========================
    # Demais itens normais
    # =========================
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


# =========================================================
# CALLBACKS PARA ABRIR/FECHAR GRUPOS
# =========================================================
@callback(
    Output("store-contratos", "data"),
    Input("btn-contratos", "n_clicks"),
    State("store-contratos", "data"),
    prevent_initial_call=True,
)
def toggle_store_contratos(n_clicks, aberto):
    if not n_clicks:
        return no_update
    return not bool(aberto)


@callback(
    Output("store-processos", "data"),
    Input("btn-processos", "n_clicks"),
    State("store-processos", "data"),
    prevent_initial_call=True,
)
def toggle_store_processos(n_clicks, aberto):
    if not n_clicks:
        return no_update
    return not bool(aberto)


@callback(
    Output("store-fracionamento", "data"),
    Input("btn-fracionamento", "n_clicks"),
    State("store-fracionamento", "data"),
    prevent_initial_call=True,
)
def toggle_store_fracionamento(n_clicks, aberto):
    if not n_clicks:
        return no_update
    return not bool(aberto)


@callback(
    Output("store-portarias", "data"),
    Input("btn-portarias", "n_clicks"),
    State("store-portarias", "data"),
    prevent_initial_call=True,
)
def toggle_store_portarias(n_clicks, aberto):
    if not n_clicks:
        return no_update
    return not bool(aberto)


# =========================================================
# EXECUÇÃO
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
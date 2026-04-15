import dash
from dash import html, dcc, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pdf.processos_pdf import gerar_pdf_processos
from services.processos_service import (
    MESES_ORDENADOS,
    formatar_moeda_brl,
    get_df_processos,
)
from utils.runtime import format_datetime_sp, get_default_year, now_sp

# --------------------------------------------------
# Função para verificar se estamos na página de processos de compras
# --------------------------------------------------
def verificar_pagina_processos_compras():
    """Verifica se o callback está sendo executado na página de processos de compras"""
    try:
        if not dash.ctx.triggered:
            # Permite execução inicial
            return True
        
        # Componentes específicos da página de processos de compras
        componentes_processos = {
            'filtro_num_proc', 'filtro_ano_proc', 'filtro_mes_finalizacao',
            'filtro_solicitante_proc', 'filtro_objeto_proc', 'filtro_modalidade_proc',
            'filtro_status_proc', 'filtro_classif_nc_proc',
            'btn_limpar_filtros_proc', 'btn_download_relatorio_proc',
            'btn-reload-proc', 'interval-reload-proc', 'store-reload-proc', 'info-atualizacao-proc'
        }
        
        # Obtém o ID do componente que disparou o callback
        triggered = dash.ctx.triggered[0]
        triggered_id = triggered['prop_id'].split('.')[0]
        
        # Verifica se é um componente da página de processos de compras
        return triggered_id in componentes_processos
    except Exception:
        # Em caso de erro, permite a execução (segurança para inicialização)
        return True

# --------------------------------------------------
# Registro da página
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/processos-de-compras",
    name="Processos de Compras",
    title="Processos de Compras",
)

# df_proc_base é carregado via get_df() (cache)

ANO_PADRAO = get_default_year()
get_df = get_df_processos

dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

# --------------------------------------------------
# Estilo unificado dos botões
# --------------------------------------------------
botao_style = {
    "color": "white",
    "padding": "8px 16px",
    "border": "none",
    "borderRadius": "4px",
    "cursor": "pointer",
    "fontSize": "12px",
    "fontWeight": "bold",
    "marginRight": "6px",
}

botao_limpar_style = {
    **botao_style,
    "backgroundColor": "#9aa0a6",
}

botao_atualizar_style = {
    **botao_style,
    "backgroundColor": "#0b2b57",
}

botao_pdf_style = {
    **botao_style,
    "backgroundColor": "#d93025",
}

page_style = {
    "padding": "14px",
    "backgroundColor": "#f6f8fb",
    "minHeight": "100vh",
}

card_shell_style = {
    "backgroundColor": "white",
    "border": "1px solid #e6ebf2",
    "borderRadius": "14px",
    "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
}


def formatar_moeda(v):
    """
    Formata float em moeda brasileira com prefixo R$.
    """
    return formatar_moeda_brl(v)


def aplicar_filtros_processos(
    df,
    num_proc=None,
    ano=None,
    mes_finalizacao=None,
    solicitante=None,
    objeto=None,
    modalidade=None,
    status=None,
    classif_nc=None,
    num_proc_parcial=True,
):
    dff = df.copy()
    mask = pd.Series(True, index=dff.index)

    if num_proc and str(num_proc).strip():
        termo = str(num_proc).strip()
        if num_proc_parcial:
            mask &= (
                dff["Numero do Processo"]
                .astype(str)
                .str.contains(termo, case=False, na=False)
            )
        else:
            mask &= dff["Numero do Processo"] == num_proc
    if ano:
        mask &= dff["Ano"] == ano
    if mes_finalizacao:
        mask &= dff["Mes_finalizacao"] == mes_finalizacao
    if solicitante:
        mask &= dff["Solicitante"] == solicitante
    if objeto:
        mask &= dff["Objeto"] == objeto
    if modalidade:
        mask &= dff["Modalidade"] == modalidade
    if status:
        mask &= dff["Status"] == status
    if classif_nc:
        mask &= dff["Classificação dos processos não concluídos"] == classif_nc

    return dff[mask]


# --------------------------------------------------
# Layout
# --------------------------------------------------
layout = html.Div(
    style=page_style,
    children=[
        dcc.Location(id="url"),
        dcc.Store(id="store-reload-proc"),
        dcc.Interval(id="interval-reload-proc", interval=60*60*1000, n_intervals=0),
        # Barra de filtros
        html.Div(
            id="barra_filtros_proc",
            className="filtros-sticky",
            style={**card_shell_style, "padding": "14px 16px"},
            children=[
                # Linha 1
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-start",
                    },
                    children=[
                        # Filtro: Número do Processo (dropdown)
                        html.Div(
                            style={
                                "minWidth": "200px",
                                "flex": "1 1 240px",
                            },
                            children=[
                                html.Label("Número do Processo"),
                                dcc.Dropdown(
                                    id="filtro_num_proc",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione um número de processo...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Filtro: Ano (sempre obrigatório, default = 2026)
                        html.Div(
                            style={
                                "minWidth": "120px",
                                "flex": "0 0 140px",
                            },
                            children=[
                                html.Label("Ano"),
                                dcc.Dropdown(
                                    id="filtro_ano_proc",
                                    options=[{"label": str(ANO_PADRAO), "value": ANO_PADRAO}],
                                    value=ANO_PADRAO,
                                    clearable=False,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Filtro: Mês de Finalização
                        html.Div(
                            style={
                                "minWidth": "150px",
                                "flex": "0 0 170px",
                            },
                            children=[
                                html.Label("Mês de Finalização"),
                                dcc.Dropdown(
                                    id="filtro_mes_finalizacao",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione um mês...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Filtro: Solicitante
                        html.Div(
                            style={
                                "minWidth": "200px",
                                "flex": "1 1 240px",
                            },
                            children=[
                                html.Label("Solicitante"),
                                dcc.Dropdown(
                                    id="filtro_solicitante_proc",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione um solicitante...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                        # Filtro: Objeto
                        html.Div(
                            style={
                                "minWidth": "260px",
                                "flex": "2 1 320px",
                            },
                            children=[
                                html.Label("Objeto"),
                                dcc.Dropdown(
                                    id="filtro_objeto_proc",
                                    options=[],
                                    value=None,
                                    placeholder="Selecione um objeto...",
                                    clearable=True,
                                    searchable=True,
                                    style=dropdown_style,
                                ),
                            ],
                        ),
                    ],
                ),
                # Linha 2 + botões à direita
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "alignItems": "flex-start",
                        "marginTop": "4px",
                        "justifyContent": "space-between",
                    },
                    children=[
                        # Coluna esquerda: filtros
                        html.Div(
                            style={
                                "display": "flex",
                                "flexWrap": "wrap",
                                "gap": "10px",
                                "alignItems": "flex-start",
                                "flex": "1 1 auto",
                            },
                            children=[
                                # Filtro: Modalidade
                                html.Div(
                                    style={
                                        "minWidth": "180px",
                                        "flex": "0 1 220px",
                                    },
                                    children=[
                                        html.Label("Modalidade"),
                                        dcc.Dropdown(
                                            id="filtro_modalidade_proc",
                                            options=[],
                                            value=None,
                                            placeholder="Selecione uma modalidade...",
                                            clearable=True,
                                            searchable=True,
                                            style=dropdown_style,
                                        ),
                                    ],
                                ),
                                # Filtro: Status
                                html.Div(
                                    style={
                                        "minWidth": "180px",
                                        "flex": "0 1 220px",
                                    },
                                    children=[
                                        html.Label("Status"),
                                        dcc.Dropdown(
                                            id="filtro_status_proc",
                                            options=[],
                                            value=None,
                                            placeholder="Selecione um status...",
                                            clearable=True,
                                            searchable=True,
                                            style=dropdown_style,
                                        ),
                                    ],
                                ),
                                # Filtro: Classificação (Não Concluídos)
                                html.Div(
                                    style={
                                        "minWidth": "240px",
                                        "flex": "0 1 320px",
                                    },
                                    children=[
                                        html.Label(
                                            "Classificação (Não Concluídos)"
                                        ),
                                        dcc.Dropdown(
                                            id="filtro_classif_nc_proc",
                                            options=[],
                                            value=None,
                                            placeholder="Selecione uma classificação...",
                                            clearable=True,
                                            searchable=True,
                                            style=dropdown_style,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # Coluna direita: informação + botões
                        html.Div(
                            style={
                                "display": "flex",
                                "flexDirection": "column",
                                "gap": "6px",
                                "alignItems": "flex-end",
                                "justifyContent": "flex-start",
                            },
                            children=[
                                html.Div(
                                    id="info-atualizacao-proc",
                                    style={
                                        "fontSize": "12px",
                                        "color": "#334155",
                                        "textAlign": "right",
                                        "backgroundColor": "#f8fafc",
                                        "border": "1px solid #e6ebf2",
                                        "borderRadius": "999px",
                                        "padding": "8px 12px",
                                    },
                                ),
                                html.Div(
                                    style={
                                        "display": "flex",
                                        "flexWrap": "wrap",
                                        "gap": "6px",
                                        "justifyContent": "flex-end",
                                        "alignItems": "center",
                                    },
                                    children=[
                                        html.Button(
                                            "Atualizar Dados",
                                            id="btn-reload-proc",
                                            n_clicks=0,
                                            style=botao_atualizar_style,
                                        ),
                                        html.Button(
                                            "Limpar Filtros",
                                            id="btn_limpar_filtros_proc",
                                            n_clicks=0,
                                            style=botao_limpar_style,
                                        ),
                                        html.Button(
                                            "Baixar Relatório PDF",
                                            id="btn_download_relatorio_proc",
                                            n_clicks=0,
                                            style=botao_pdf_style,
                                        ),
                                        dcc.Download(id="download_relatorio_proc"),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        # Conteúdo principal
        html.Div(
            children=[
                html.Div(
                    id="cards_resumo_proc",
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "marginBottom": "18px",
                        "marginTop": "14px",
                    },
                ),
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "10px",
                        "marginBottom": "15px",
                    },
                    children=[
                        html.Div(
                            style={
                                **card_shell_style,
                                "flex": "1 1 320px",
                                "minWidth": "300px",
                                "padding": "10px",
                            },
                            children=[
                                dcc.Graph(
                                    id="grafico_status_proc",
                                    style={"height": "320px"},
                                ),
                            ],
                        ),
                        html.Div(
                            style={
                                **card_shell_style,
                                "flex": "2 1 420px",
                                "minWidth": "340px",
                                "padding": "10px",
                            },
                            children=[
                                dcc.Graph(
                                    id="grafico_valor_mes_proc",
                                    style={"height": "320px"},
                                ),
                            ],
                        ),
                    ],
                ),
                html.H4("Tabela de Processos de Compras", style={"margin": "0 0 14px 0", "textAlign": "center", "color": "#0b2b57"}),
                dash_table.DataTable(
                    id="tabela_proc",
                    columns=[
                        {"name": "Solicitante", "id": "Solicitante"},
                        {
                            "name": "Número Do Processo",
                            "id": "Numero do Processo",
                        },
                        {"name": "Objeto", "id": "Objeto"},
                        {"name": "Modalidade", "id": "Modalidade"},
                        {
                            "name": "Preço Estimado",
                            "id": "PREÇO ESTIMADO_FMT",
                        },
                        {
                            "name": "Valor Contratado",
                            "id": "Valor Contratado_FMT",
                        },
                        {"name": "Status", "id": "Status"},
                        {
                            "name": "Data De Entrada",
                            "id": "Data de Entrada",
                        },
                        {
                            "name": "Data Finalização",
                            "id": "Data finalização_FMT",
                        },
                        {
                            "name": "Classificação (Não Concluídos)",
                            "id": "Classificação dos processos não concluídos",
                        },
                        {
                            "name": "Contratação Reinstruída Pelo Processo Nº",
                            "id": "CONTRATAÇÃO REINSTRUÍDA PELO PROCESSO Nº (com pontos e traços)",
                        },
                    ],
                    data=[],
                    row_selectable=False,
                    cell_selectable=False,
                    style_table={
                        "overflowX": "auto",
                        "overflowY": "auto",
                        "maxHeight": "500px",
                        "position": "relative",
                    },
                    style_cell={
                        "textAlign": "center",
                        "padding": "10px 8px",
                        "fontSize": "12px",
                        "minWidth": "80px",
                        "maxWidth": "220px",
                        "whiteSpace": "normal",
                        "lineHeight": "1.35",
                        "border": "1px solid #e4e8ef",
                    },
                    style_header={
                        "fontWeight": "bold",
                        "backgroundColor": "#0b2b57",
                        "color": "white",
                        "textAlign": "center",
                        "position": "sticky",
                        "top": 0,
                        "zIndex": 10,
                        "padding": "12px 8px",
                    },
                    style_data_conditional=[
                        {
                            "if": {
                                "filter_query": '{Status} = "Em Andamento"'
                            },
                            "backgroundColor": "#eef2f7",
                        },
                        {
                            "if": {
                                "filter_query": '{Status} = "Não Concluído"'
                            },
                            "backgroundColor": "#fff1f1",
                        },
                    ],
                ),
                # Store com os dados filtrados (base para PDF)
                dcc.Store(id="store_dados_proc"),
            ],
        ),
    ],
)

# ----------------------------------------
# Callback: carregar/atualizar base (ao abrir a página, por intervalo, ou manualmente)
# ----------------------------------------
@dash.callback(
    Output("store-reload-proc", "data"),
    Output("info-atualizacao-proc", "children"),
    Output("filtro_ano_proc", "options"),
    Input("url", "pathname"),
    Input("btn-reload-proc", "n_clicks"),
    Input("interval-reload-proc", "n_intervals"),
)
def carregar_ao_abrir_ou_recarregar(pathname, n_reload, n_intervals):
    if pathname != "/processos-de-compras":
        raise PreventUpdate

    force = dash.ctx.triggered_id == "btn-reload-proc"

    try:
        df, status = get_df(force=force)

        # opções de ano
        anos = sorted([int(a) for a in pd.Series(df.get("Ano", pd.Series([], dtype=int))).dropna().unique().tolist() if str(a) != ""])
        if not anos:
            anos = [ANO_PADRAO]
        ano_opts = [{"label": str(a), "value": a} for a in anos]

        msg = html.Div(
            [
                html.B("Dados prontos. "),
                html.Span(f"({format_datetime_sp(now_sp())}) "),
                html.Span(status),
            ]
        )

        return {"ts": now_sp().isoformat()}, msg, ano_opts
    except Exception as e:
        msg = html.Div([html.B("Falha ao carregar dados: "), html.Span(str(e))])
        return {"ts": now_sp().isoformat(), "erro": str(e)}, msg, [{"label": str(ANO_PADRAO), "value": ANO_PADRAO}]

# ----------------------------------------
# Callback: atualizar tabela + cards + gráficos
# ----------------------------------------
@dash.callback(
    Output("tabela_proc", "data"),
    Output("store_dados_proc", "data"),
    Output("cards_resumo_proc", "children"),
    Output("grafico_status_proc", "figure"),
    Output("grafico_valor_mes_proc", "figure"),
    Input("filtro_num_proc", "value"),
    Input("filtro_ano_proc", "value"),
    Input("filtro_mes_finalizacao", "value"),
    Input("filtro_solicitante_proc", "value"),
    Input("filtro_objeto_proc", "value"),
    Input("filtro_modalidade_proc", "value"),
    Input("filtro_status_proc", "value"),
    Input("filtro_classif_nc_proc", "value"),
    Input("store-reload-proc", "data"),
)
def atualizar_tabela_proc(
    num_proc,
    ano,
    mes_finalizacao,
    solicitante,
    objeto,
    modalidade,
    status,
    classif_nc,
    _reload,
):
    # VERIFICAÇÃO: Só executa se estiver na página de processos de compras
    if not verificar_pagina_processos_compras():
        raise PreventUpdate
    
    # -------------------------
    # Filtro principal
    # -------------------------
    df_base, _status = get_df(force=False)
    dff = aplicar_filtros_processos(
        df_base,
        num_proc=num_proc,
        ano=ano,
        mes_finalizacao=mes_finalizacao,
        solicitante=solicitante,
        objeto=objeto,
        modalidade=modalidade,
        status=status,
        classif_nc=classif_nc,
    )

    # -------------------------
    # Formatação da tabela
    # -------------------------
    dff_display = dff.copy()
    dff_display["PREÇO ESTIMADO_FMT"] = dff_display["PREÇO ESTIMADO"].apply(
        formatar_moeda
    )
    dff_display["Valor Contratado_FMT"] = dff_display[
        "Valor Contratado"
    ].apply(formatar_moeda)

    # Data de Entrada
    dff_display["Data de Entrada"] = pd.to_datetime(
        dff_display["Data de Entrada"],
        format="%d/%m/%Y",
        errors="coerce",
    ).dt.strftime("%d/%m/%Y")

    # Data finalização
    dff_display["Data finalização_FMT"] = dff_display["Data finalização"].dt.strftime(
        "%d/%m/%Y"
    )

    # Campo auxiliar para ordenação
    dff_display["Data_Entrada_dt"] = pd.to_datetime(
        dff_display["Data de Entrada"], format="%d/%m/%Y", errors="coerce"
    )

    dff_display = (
        dff_display.sort_values("Data_Entrada_dt", ascending=False)
        .reset_index(drop=True)
    )

    # -------------------------
    # Cards resumo
    # -------------------------
    total_valor_contratado = dff["Valor Contratado"].sum()
    qtd_processos = len(dff)
    concluidos = (dff["Status"] == "Concluído").sum()
    media_por_processo = (
        total_valor_contratado / concluidos if concluidos > 0 else 0.0
    )

    em_andamento = (dff["Status"] == "Em Andamento").sum()
    nao_concluidos = (dff["Status"] == "Não Concluído").sum()

    card_style = {
        "flex": "1 1 180px",
        "backgroundColor": "#ffffff",
        "padding": "14px",
        "textAlign": "center",
        "minHeight": "20px",
        "minWidth": "170px",
        "maxWidth": "220px",
        "border": "1px solid #e6ebf2",
        "borderRadius": "14px",
        "boxShadow": "0 2px 12px rgba(11, 43, 87, 0.06)",
    }

    cards = [
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    formatar_moeda(total_valor_contratado),
                    style={
                        "color": "#c00000",
                        "margin": "0",
                        "fontSize": "20px",
                    },
                ),
                html.Div("Valor Contratado", style={"fontSize": "15px"}),
            ],
        ),
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    formatar_moeda(media_por_processo),
                    style={
                        "color": "#003A70",
                        "margin": "0",
                        "fontSize": "20px",
                    },
                ),
                html.Div(
                    "Média por Processo Concluído",
                    style={"fontSize": "15px"},
                ),
            ],
        ),
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    qtd_processos,
                    style={"margin": "0", "fontSize": "20px"},
                ),
                html.Div("Número de Processos", style={"fontSize": "13px"}),
            ],
        ),
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    concluidos,
                    style={"margin": "0", "fontSize": "20px"},
                ),
                html.Div("Processos Concluídos", style={"fontSize": "13px"}),
            ],
        ),
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    em_andamento,
                    style={"margin": "0", "fontSize": "20px"},
                ),
                html.Div(
                    "Processos Em Andamento", style={"fontSize": "13px"}
                ),
            ],
        ),
        html.Div(
            className="card-resumo",
            style=card_style,
            children=[
                html.H4(
                    nao_concluidos,
                    style={"margin": "0", "fontSize": "20px"},
                ),
                html.Div(
                    "Processos Não Concluídos", style={"fontSize": "13px"}
                ),
            ],
        ),
    ]

    # -------------------------
    # Gráficos
    # -------------------------
    if dff.empty:
        fig_status = px.pie(title="Porcentagem de Status")
        fig_valor_mes = px.bar(title="Processos Concluídos por Ano")
    else:
        # Gráfico de status (pizza)
        grp_status = (
            dff.groupby("Status", as_index=False)["Numero do Processo"]
            .count()
            .rename(columns={"Numero do Processo": "Qtd"})
        )

        fig_status = px.pie(
            grp_status,
            names="Status",
            values="Qtd",
            hole=0.6,
            title="Porcentagem de Status",
        )

        fig_status.update_traces(
            marker=dict(
                colors=["#003A70", "#DA291C", "#A2AAAD"],
                line=dict(color="#ECEDEF", width=2),
            ),
            textposition="outside",
            texttemplate="%{label} %{value} (%{percent:.2%})",
        )

        fig_status.update_layout(
            title_x=0.5,
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            showlegend=False,
        )

        # --- gráfico anual usa filtros exceto ano ---
        df_base2, _status2 = get_df(force=False)
        dff_global = aplicar_filtros_processos(
            df_base2,
            num_proc=num_proc,
            mes_finalizacao=mes_finalizacao,
            solicitante=solicitante,
            objeto=objeto,
            modalidade=modalidade,
            status=status,
            classif_nc=classif_nc,
        )
        dff_conc_global = dff_global[
            dff_global["Status"] == "Concluído"
        ].copy()

        if dff_conc_global.empty:
            fig_valor_mes = px.bar(
                title="Processos Concluídos por Ano"
            )
        else:
            grp_ano = (
                dff_conc_global.groupby("Ano", as_index=False)
                .agg(
                    Valor_Contratado_Total=("Valor Contratado", "sum"),
                    Qtd_Processos=("Numero do Processo", "count"),
                )
            )

            grp_ano["Media_Por_Processo"] = (
                grp_ano["Valor_Contratado_Total"]
                / grp_ano["Qtd_Processos"]
            )

            grp_ano["Valor_Contratado_Total_FMT"] = grp_ano[
                "Valor_Contratado_Total"
            ].apply(formatar_moeda)
            grp_ano["Media_Por_Processo_FMT"] = grp_ano[
                "Media_Por_Processo"
            ].apply(formatar_moeda)

            hovertemplate_ano = (
                "Ano: %{x}<br>"
                + "Valor Contratado Total: %{customdata[0]}<br>"
                + "Média por Processo: %{customdata[1]}<br>"
                + "Número de Processos Concluídos: %{customdata[2]}<extra></extra>"
            )

            customdata = grp_ano[
                [
                    "Valor_Contratado_Total_FMT",
                    "Media_Por_Processo_FMT",
                    "Qtd_Processos",
                ]
            ].values

            fig_valor_mes = make_subplots(
                specs=[[{"secondary_y": True}]]
            )

            fig_valor_mes.add_trace(
                go.Bar(
                    x=grp_ano["Ano"],
                    y=grp_ano["Valor_Contratado_Total"],
                    name="Valor Contratado Total",
                    marker_color="red",
                    width=0.4,
                    customdata=customdata,
                    hovertemplate=hovertemplate_ano,
                ),
                secondary_y=False,
            )

            fig_valor_mes.add_trace(
                go.Bar(
                    x=grp_ano["Ano"],
                    y=grp_ano["Media_Por_Processo"],
                    name="Média por Processo",
                    marker_color="blue",
                    width=0.4,
                    offset=-0.2,
                    customdata=customdata,
                    hovertemplate=hovertemplate_ano,
                ),
                secondary_y=False,
            )

            fig_valor_mes.add_trace(
                go.Scatter(
                    x=grp_ano["Ano"],
                    y=grp_ano["Qtd_Processos"],
                    name="Número de Processos Concluídos",
                    mode="lines+markers",
                    line=dict(color="green", width=3),
                    customdata=customdata,
                    hovertemplate=hovertemplate_ano,
                ),
                secondary_y=True,
            )

            fig_valor_mes.update_layout(
                barmode="overlay",
                title="Processos Concluídos por Ano",
                title_x=0.5,
                xaxis_title="Ano",
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
                showlegend=False,
            )

            fig_valor_mes.update_yaxes(
                title_text="Valores (R$)", secondary_y=False
            )
            fig_valor_mes.update_yaxes(
                title_text="Número de Processos Concluídos",
                secondary_y=True,
            )

    cols_tabela = [
        "Solicitante",
        "Numero do Processo",
        "Objeto",
        "Modalidade",
        "PREÇO ESTIMADO_FMT",
        "Valor Contratado_FMT",
        "Status",
        "Data de Entrada",
        "Data finalização_FMT",
        "Classificação dos processos não concluídos",
        "CONTRATAÇÃO REINSTRUÍDA PELO PROCESSO Nº (com pontos e traços)",
    ]

    return (
        dff_display[cols_tabela].to_dict("records"),
        dff.to_dict("records"),
        cards,
        fig_status,
        fig_valor_mes,
    )

# ----------------------------------------
# Callback: filtros em cascata
# ----------------------------------------
@dash.callback(
    Output("filtro_num_proc", "options"),
    Output("filtro_mes_finalizacao", "options"),
    Output("filtro_solicitante_proc", "options"),
    Output("filtro_objeto_proc", "options"),
    Output("filtro_modalidade_proc", "options"),
    Output("filtro_status_proc", "options"),
    Output("filtro_classif_nc_proc", "options"),
    Input("filtro_ano_proc", "value"),
    Input("filtro_mes_finalizacao", "value"),
    Input("filtro_solicitante_proc", "value"),
    Input("filtro_objeto_proc", "value"),
    Input("filtro_modalidade_proc", "value"),
    Input("filtro_status_proc", "value"),
    Input("filtro_classif_nc_proc", "value"),
    Input("filtro_num_proc", "value"),
    Input("store-reload-proc", "data"),
)
def atualizar_opcoes_filtros(
    ano,
    mes_finalizacao,
    solicitante,
    objeto,
    modalidade,
    status,
    classif_nc,
    num_proc,
    _reload,
):
    """
    Gera opções de dropdown em cascata a partir de um único filtro global.
    A ordem de seleção dos filtros não importa.
    """
    # VERIFICAÇÃO: Só executa se estiver na página de processos de compras
    if not verificar_pagina_processos_compras():
        raise PreventUpdate
    
    df_base, _status = get_df(force=False)
    dff = aplicar_filtros_processos(
        df_base,
        num_proc=num_proc,
        ano=ano,
        mes_finalizacao=mes_finalizacao,
        solicitante=solicitante,
        objeto=objeto,
        modalidade=modalidade,
        status=status,
        classif_nc=classif_nc,
        num_proc_parcial=False,
    )

    # Opções para Número do Processo
    op_num_proc = [
        {"label": str(p), "value": str(p)}
        for p in sorted(dff["Numero do Processo"].dropna().unique())
        if str(p) != ""
    ]

    # Opções para Mês de Finalização (respeitando a ordem cronológica)
    meses_disponiveis = dff["Mes_finalizacao"].dropna().unique().tolist()
    op_mes_finalizacao = [
        {"label": m.capitalize(), "value": m}
        for m in MESES_ORDENADOS
        if m in meses_disponiveis
    ]

    # Opções para Solicitante
    op_solicitante = [
        {"label": str(s), "value": str(s)}
        for s in sorted(dff["Solicitante"].dropna().unique())
        if str(s) != ""
    ]

    # Opções para Objeto
    op_objeto = [
        {"label": str(o), "value": str(o)}
        for o in sorted(dff["Objeto"].dropna().unique())
        if str(o) != ""
    ]

    # Opções para Modalidade
    op_modalidade = [
        {"label": str(m), "value": str(m)}
        for m in sorted(dff["Modalidade"].dropna().unique())
        if str(m) != ""
    ]

    # Opções para Status
    op_status = [
        {"label": str(s), "value": str(s)}
        for s in sorted(dff["Status"].dropna().unique())
        if str(s) != ""
    ]

    # Opções para Classificação
    op_classif = [
        {"label": str(c), "value": str(c)}
        for c in sorted(
            dff["Classificação dos processos não concluídos"]
            .dropna()
            .unique()
        )
        if str(c) != ""
    ]

    return (
        op_num_proc,
        op_mes_finalizacao,
        op_solicitante,
        op_objeto,
        op_modalidade,
        op_status,
        op_classif,
    )

# ----------------------------------------
# Callback: limpar filtros (volta sempre para ano 2026)
# ----------------------------------------
@dash.callback(
    Output("filtro_num_proc", "value"),
    Output("filtro_ano_proc", "value"),
    Output("filtro_mes_finalizacao", "value"),
    Output("filtro_solicitante_proc", "value"),
    Output("filtro_objeto_proc", "value"),
    Output("filtro_modalidade_proc", "value"),
    Output("filtro_status_proc", "value"),
    Output("filtro_classif_nc_proc", "value"),
    Input("btn_limpar_filtros_proc", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_proc(n):
    """
    Limpa todos os filtros e retorna o ano para ANO_PADRAO (2026).
    """
    # VERIFICAÇÃO: Só executa se estiver na página de processos de compras
    if not verificar_pagina_processos_compras():
        raise PreventUpdate
    
    return None, ANO_PADRAO, None, None, None, None, None, None

# --------------------------------------------------
# CALLBACK: GERAR PDF DE PROCESSOS DE COMPRAS
# --------------------------------------------------
@dash.callback(
    Output("download_relatorio_proc", "data"),
    Input("btn_download_relatorio_proc", "n_clicks"),
    State("store_dados_proc", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_proc(n, dados_proc):
    """
    Gera o relatório em PDF com base nos dados filtrados atualmente na tabela.
    """
    # VERIFICAÇÃO: Só executa se estiver na página de processos de compras
    if not verificar_pagina_processos_compras():
        raise PreventUpdate
    
    if not n or not dados_proc:
        return None

    return gerar_pdf_processos(dados_proc)

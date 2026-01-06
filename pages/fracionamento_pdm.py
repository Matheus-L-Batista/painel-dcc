import dash
from dash import html, dcc, dash_table, Input, Output, State, no_update

import pandas as pd
from datetime import date

from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors


# --------------------------------------------------
# Registro da página no sistema de rotas do Dash
# --------------------------------------------------
dash.register_page(
    __name__,
    path="/fracionamento_pdm",          # URL da página
    name="Fracionamento de Despesas PDM",  # Nome exibido no menu
    title="Fracionamento de Despesas PDM", # Título da aba do navegador
)


# --------------------------------------------------
# URL da planilha (fonte de dados)
# --------------------------------------------------
URL_LIMITE_GASTO_ITA = (
    "https://docs.google.com/spreadsheets/d/"
    "1YNg6WRww19Gf79ISjQtb8tkzjX2lscHirnR_F3wGjog/"
    "gviz/tq?tqx=out:csv&sheet=Limite%20de%20Gasto%20-%20Itajub%C3%A1"
)

COL_PDM = "PDM"              # Nome da coluna de PDM
COL_DESC_ORIG = "Descrição.1"  # Nome original da descrição na planilha


# --------------------------------------------------
# Carga e tratamento dos dados
# --------------------------------------------------
def carregar_dados_limite_pdm():
    # Lê o CSV direto do Google Sheets
    df = pd.read_csv(URL_LIMITE_GASTO_ITA)
    # Remove espaços em branco dos nomes de colunas
    df.columns = [c.strip() for c in df.columns]

    # Renomeia a coluna de descrição para um nome único
    renomeios = {
        COL_DESC_ORIG: "Descrição",
    }
    df = df.rename(columns=renomeios)

    # Garante colunas básicas mesmo se não vierem no CSV
    if COL_PDM not in df.columns:
        df[COL_PDM] = ""
    if "Descrição" not in df.columns:
        df["Descrição"] = ""

    # Normaliza PDM para string com 5 dígitos (zeros à esquerda)
    df[COL_PDM] = (
        df[COL_PDM]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)   # remove .0 de floats
        .str.replace(r"\D", "", regex=True)     # remove não dígitos
        .str.zfill(5)                           # garante 5 dígitos
    )

    # Trata coluna de valor empenhado (se existir "Unnamed: 7")
    if "Unnamed: 7" in df.columns:
        df["Valor Empenhado"] = (
            df["Unnamed: 7"]
            .astype(str)
            .str.replace(".", "", regex=False)   # remove separador de milhar
            .str.replace(",", ".", regex=False)  # converte decimal pt-BR para ponto
        )
        # Converte para número
        df["Valor Empenhado"] = pd.to_numeric(df["Valor Empenhado"], errors="coerce")
    else:
        # Se não houver a coluna, zera o valor empenhado
        df["Valor Empenhado"] = 0.0

    # Define limite fixo da dispensa (R$ 65.492,11)
    valor_limite = 65492.11
    df["Limite da Dispensa"] = valor_limite

    # Calcula saldo = limite - empenhado
    df["Saldo para contratação"] = df["Limite da Dispensa"] - df["Valor Empenhado"]

    # Cria lista de PDMs únicos para o dropdown
    pdms_unicos = sorted(
        [
            c
            for c in df[COL_PDM].dropna().unique()
            if isinstance(c, str) and c.strip() != ""
        ]
    )
    # Armazena lista como atributo do DataFrame
    df._lista_pdms_unicos = pdms_unicos

    return df


# DataFrame base em memória
df_limite_pdm_base = carregar_dados_limite_pdm()
# Lista global de PDMs para popular o dropdown
PDMS_UNICOS = getattr(df_limite_pdm_base, "_lista_pdms_unicos", [])


# Estilo padrão do dropdown (cor, largura etc.)
dropdown_style = {
    "color": "black",
    "width": "100%",
    "marginBottom": "6px",
    "whiteSpace": "normal",
}

# Data atual no formato dd/mm/aaaa para exibir na página
DATA_HOJE = date.today().strftime("%d/%m/%Y")


# --------------------------------------------------
# Layout em duas colunas (1/3 texto, 2/3 tabela)
# --------------------------------------------------
layout = html.Div(
    style={
        "display": "flex",        # layout em flexbox
        "flexDirection": "row",   # colunas lado a lado
        "width": "100%",
        "gap": "10px",            # espaçamento entre colunas
    },
    children=[
        # Coluna esquerda (1/3) – texto explicativo
        html.Div(
            id="coluna_esquerda_pdm",
            style={
                "flex": "1 1 33%",               # ocupa ~1/3 da largura
                "borderRight": "1px solid #ccc", # linha divisória
                "padding": "5px",
                "minWidth": "280px",
                "fontSize": "12px",
                "textAlign": "justify",
            },
            children=[
                # Vários parágrafos de orientação normativa
                html.P("Prezado requisitante,"),
                html.Br(),
                html.P(
                    "Em atenção ao acórdão nº 324/2009 Plenário TCU, "
                    "“Planeje adequadamente as compras e a contratação de serviços durante o "
                    "exercício financeiro, de forma a evitar a prática de fracionamento de despesas”."
                ),
                html.Br(),
                html.P("Assim dispõe a IN SEGES/ME nº 67/2021:"),
                html.Br(),
                html.P(
                    "Art. 4º Os órgãos e entidades adotarão a dispensa de licitação, na forma "
                    "eletrônica, nas seguintes hipóteses:"
                ),
                html.P(
                    "[...] § 2º Considera-se ramo de atividade a linha de fornecimento registrada "
                    "pelo fornecedor quando do seu cadastramento no Sistema de Cadastramento "
                    "Unificado de Fornecedores (Sicaf), vinculada:"
                ),
                html.P(
                    "I - à classe de materiais, utilizando o Padrão Descritivo de Materiais (PDM) do "
                    "Sistema de Catalogação de Material do Governo federal; ou"
                ),
                html.P(
                    "II - à descrição dos serviços ou das obras, constante do Sistema de Catalogação "
                    "de Serviços ou de Obras do Governo federal.\" (NR)"
                ),
                html.Br(),
                html.P("Em resumo: Para materiais - PDM; para serviços - CATSER."),
                html.Br(),
                html.P(
                 [
                    "Para obtenção do PDM: no catálogo de compras disponível em ",
                     html.A(
                        "https://catalogo.compras.gov.br/cnbs-web/busca",
                        href="https://catalogo.compras.gov.br/cnbs-web/busca",
                        target="_blank",          # abre em nova aba
                        style={"color": "#1d4ed8", "textDecoration": "underline"},
                    ),
                    ", informar o número do CATMAT. Exemplo para o CATMAT 605322: a consulta "
                     "retornará PDM: 8320. Esse é o número que deverá ser considerado.",
                 ]
                ),

                html.Br(),
                html.P("Exemplo para a necessidade de contratação de três itens:"),
                html.P(
                    "1) o somatório do valor obtido na pesquisa de mercado para cada um dos itens "
                    "multiplicado por seu quantitativo não poderá exceder o limite da dispensa."
                ),
                html.P(
                    "2) O valor por item deverá obrigatoriamente ser igual ou inferior ao saldo para "
                    "contratação (PDM ou CATSER) desse item."
                ),
                html.Br(),
                html.P(
                    "Os valores informados na tabela são os já empenhados no exercício por PDM ou CATSER."
                ),
                html.Br(),
                html.P(
                    "O processo de compra deverá vir instruído já na modalidade DISPENSA DE LICITAÇÃO. "
                    "A tela de consulta (print da tela) deverá estar apensado ao processo, que será "
                    "conferido pelo Setor de Compras e, somente a partir do resultado dessa conferência, "
                    "o processo prosseguirá.",
                    style={"color": "red"},  # deixa todo o parágrafo em vermelho
                ),

            ],
        ),

        # Coluna direita (2/3) – filtros, cartão de data, tabela e store
        html.Div(
            id="coluna_direita_pdm",
            style={
                "flex": "2 1 67%",  # ocupa ~2/3 da largura
                "padding": "5px",
                "minWidth": "400px",
            },
            children=[
                # Barra de filtros (fica sticky via CSS da classe)
                html.Div(
                    id="barra_filtros_limite_itajuba_pdm",
                    className="filtros-sticky",
                    children=[
                        # Primeira linha: filtros de PDM
                        html.Div(
                            style={
                                "display": "flex",
                                "flexWrap": "wrap",
                                "gap": "10px",
                                "alignItems": "flex-start",
                            },
                            children=[
                                # Filtro PDM por digitação (texto livre)
                                html.Div(
                                    style={"minWidth": "220px", "flex": "1 1 260px"},
                                    children=[
                                        html.Label("PDM (digitação)"),
                                        dcc.Input(
                                            id="filtro_pdm_texto_itajuba",
                                            type="text",
                                            placeholder="Digite parte do PDM",
                                            style={
                                                "width": "100%",
                                                "marginBottom": "6px",
                                            },
                                        ),
                                    ],
                                ),
                                # Filtro PDM por dropdown múltiplo
                                html.Div(
                                    style={"minWidth": "220px", "flex": "1 1 260px"},
                                    children=[
                                        html.Label("PDM"),
                                        dcc.Dropdown(
                                            id="filtro_pdm_dropdown_itajuba",
                                            options=[
                                                {"label": c, "value": c}
                                                for c in PDMS_UNICOS
                                            ],
                                            value=[],  # seleção múltipla
                                            placeholder="Todos",
                                            clearable=True,
                                            multi=True,
                                            style=dropdown_style,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # Segunda linha: botões + data
                        html.Div(
                            style={
                                "marginTop": "4px",
                                "display": "flex",
                                "alignItems": "center",
                                "gap": "10px",
                                "flexWrap": "wrap",
                            },
                            children=[
                                # Botão limpar filtros
                                html.Button(
                                    "Limpar filtros",
                                    id="btn_limpar_filtros_limite_itajuba_pdm",
                                    n_clicks=0,
                                    className="filtros-button",
                                ),
                                # Botão para baixar relatório em PDF
                                html.Button(
                                    "Baixar Relatório PDF",
                                    id="btn_download_relatorio_limite_itajuba_pdm",
                                    n_clicks=0,
                                    className="filtros-button",
                                    style={"marginLeft": "10px"},
                                ),
                                # Cartão com data da consulta
                                html.Div(
                                    style={
                                        "padding": "6px 12px",
                                        "borderRadius": "4px",
                                        "backgroundColor": "#f3f4f6",
                                        "border": "1px solid #d1d5db",
                                        "fontSize": "12px",
                                    },
                                    children=[
                                        html.Span(
                                            f"Data da consulta: {DATA_HOJE}"
                                        ),
                                    ],
                                ),
                                # Componente de download (usado no callback do PDF)
                                dcc.Download(id="download_relatorio_limite_itajuba_pdm"),
                            ],
                        ),
                    ],
                ),
                # Título da tabela
                html.H4("Limite de Gasto – Itajubá por PDM"),
                # DataTable exibida na página
                dash_table.DataTable(
                    id="tabela_limite_itajuba_pdm",
                    columns=[
                        {"name": "PDM", "id": COL_PDM},
                        {"name": "Descrição", "id": "Descrição"},
                        {"name": "Valor Empenhado (R$)", "id": "Valor Empenhado_fmt"},
                        {"name": "Limite da Dispensa (R$)", "id": "Limite da Dispensa_fmt"},
                        {
                            "name": "Saldo para contratação (R$)",
                            "id": "Saldo para contratação_fmt",
                        },
                    ],
                    data=[],                 # dados preenchidos via callback
                    row_selectable=False,    # desabilita seleção de linhas
                    cell_selectable=False,   # desabilita seleção de células

                    # >>> AQUI você controla a ALTURA (comprimento) da tabela na PÁGINA <<<
                    style_table={
                        "overflowX": "auto",          # rolagem horizontal se precisar
                        "overflowY": "auto",          # rolagem vertical
                        # altura relativa à tela; aumente o número subtraído para reduzir a área da tabela
                        "height": "calc(100vh - 350px)",  # era "calc(100vh - 200px)"
                        "minHeight": "300px",         # altura mínima da tabela
                        "position": "relative",
                    },

                    # >>> AQUI você controla a ALTURA DE CADA LINHA (padding + fonte) <<<
                    style_cell={
                        "textAlign": "center",
                        "padding": "4px",    # era 6px; menor padding = linhas mais baixas
                        "fontSize": "11px",  # era 12px; fonte menor = linhas mais baixas
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
                    style_data_conditional=[
                        {
                            "if": {"column_id": "Saldo para contratação_fmt"},
                            "backgroundColor": "#f9f9f9",
                        }
                    ],
                ),
                # Store para guardar os dados filtrados e reutilizar no PDF
                dcc.Store(id="store_dados_limite_itajuba_pdm"),
            ],
        ),
    ],
)


# --------------------------------------------------
# Callback: atualizar opções do dropdown com base no texto digitado
# --------------------------------------------------
@dash.callback(
    Output("filtro_pdm_dropdown_itajuba", "options"),
    Input("filtro_pdm_texto_itajuba", "value"),
    State("filtro_pdm_dropdown_itajuba", "value"),
)
def atualizar_opcoes_pdm(pdm_texto, valores_selecionados):
    base = PDMS_UNICOS  # lista global de PDMs
    if not pdm_texto or not str(pdm_texto).strip():
        # Sem texto: mostra todas as opções
        opcoes = [{"label": c, "value": c} for c in base]
    else:
        termo = str(pdm_texto).strip().lower()
        # Filtra PDMs que contém o termo digitado
        filtradas = [c for c in base if termo in str(c).lower()]
        # Garante que os já selecionados continuem visíveis
        if valores_selecionados:
            for v in valores_selecionados:
                if v in base and v not in filtradas:
                    filtradas.append(v)
        opcoes = [{"label": c, "value": c} for c in sorted(filtradas)]
    return opcoes


# --------------------------------------------------
# Callback: aplicar filtros e atualizar tabela + store
# --------------------------------------------------
@dash.callback(
    Output("tabela_limite_itajuba_pdm", "data"),
    Output("store_dados_limite_itajuba_pdm", "data"),
    Input("filtro_pdm_texto_itajuba", "value"),
    Input("filtro_pdm_dropdown_itajuba", "value"),
)
def atualizar_tabela_limite_itajuba_pdm(pdm_texto, pdm_lista):
    # Copia o DataFrame base
    dff = df_limite_pdm_base.copy()

    # Filtro por PDM (texto) – restringe o universo
    if pdm_texto and str(pdm_texto).strip():
        termo = str(pdm_texto).strip().lower()
        dff = dff[
            dff[COL_PDM]
            .astype(str)
            .str.lower()
            .str.contains(termo, na=False)
        ]

    # Filtro por PDM (dropdown múltiplo)
    if pdm_lista:
        dff = dff[dff[COL_PDM].isin(pdm_lista)]

    # Define colunas que serão exibidas
    cols_tabela = [
        COL_PDM,
        "Descrição",
        "Valor Empenhado",
        "Limite da Dispensa",
        "Saldo para contratação",
    ]

    # Garante que todas as colunas existam
    for c in cols_tabela:
        if c not in dff.columns:
            dff[c] = pd.NA

    # DataFrame usado apenas para exibição (com formatação)
    dff_display = dff[cols_tabela].copy()

    # Função para formatar moeda em pt-BR
    def fmt_moeda(v):
        if pd.isna(v):
            return ""
        return "R$ " + (
            f"{v:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    # Cria colunas formatadas
    dff_display["Valor Empenhado_fmt"] = dff_display["Valor Empenhado"].apply(fmt_moeda)
    dff_display["Limite da Dispensa_fmt"] = dff_display["Limite da Dispensa"].apply(fmt_moeda)
    dff_display["Saldo para contratação_fmt"] = dff_display["Saldo para contratação"].apply(
        fmt_moeda
    )

    # Ordem das colunas exibidas na tabela
    cols_tabela_display = [
        COL_PDM,
        "Descrição",
        "Valor Empenhado_fmt",
        "Limite da Dispensa_fmt",
        "Saldo para contratação_fmt",
    ]

    # Retorna dados para a tabela (formato records) e para o store (dados originais)
    return dff_display[cols_tabela_display].to_dict("records"), dff.to_dict("records")


# --------------------------------------------------
# Callback: limpar filtros (texto + dropdown)
# --------------------------------------------------
@dash.callback(
    Output("filtro_pdm_texto_itajuba", "value"),
    Output("filtro_pdm_dropdown_itajuba", "value"),
    Input("btn_limpar_filtros_limite_itajuba_pdm", "n_clicks"),
    prevent_initial_call=True,
)
def limpar_filtros_limite_itajuba_pdm(n):
    # Reseta texto e seleção do dropdown
    return None, []


# --------------------------------------------------
# Callback: gerar PDF com a tabela filtrada
# --------------------------------------------------

# Estilo de parágrafo usado nas células do PDF
wrap_style = ParagraphStyle(
    name="wrap_limite_itajuba_pdm",
    fontSize=8,
    leading=10,
    spaceAfter=4,
)


def wrap(text):
    # Converte texto em Paragraph para permitir quebra de linha no PDF
    return Paragraph(str(text), wrap_style)


@dash.callback(
    Output("download_relatorio_limite_itajuba_pdm", "data"),
    Input("btn_download_relatorio_limite_itajuba_pdm", "n_clicks"),
    State("store_dados_limite_itajuba_pdm", "data"),
    prevent_initial_call=True,
)
def gerar_pdf_limite_itajuba_pdm(n, dados):
    # Se não há clique ou não há dados, não faz nada
    if not n or not dados:
        return None

    # Converte dados do store em DataFrame
    df = pd.DataFrame(dados)

    # Buffer em memória para o PDF
    buffer = BytesIO()
    pagesize = landscape(A4)  # página A4 horizontal
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []  # lista de elementos do PDF

    # Título do relatório
    titulo = Paragraph(
        "Relatório – Limite de Gasto – Itajubá por PDM",
        ParagraphStyle(
            "titulo_limite_itajuba_pdm",
            fontSize=16,
            alignment=TA_CENTER,
            textColor="#0b2b57",
        ),
    )
    story.append(titulo)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Total de registros: {len(df)}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    # Colunas que irão para o PDF
    cols = [
        COL_PDM,
        "Descrição",
        "Valor Empenhado",
        "Limite da Dispensa",
        "Saldo para contratação",
    ]
    # Garante que existam
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    # Função de formatação de moeda para o PDF
    def fmt_moeda_pdf(v):
        if pd.isna(v):
            return ""
        return "R$ " + (
            f"{v:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    # Copia DF e aplica formatação de moeda
    df_pdf = df.copy()
    for col in ["Valor Empenhado", "Limite da Dispensa", "Saldo para contratação"]:
        if col in df_pdf.columns:
            df_pdf[col] = df_pdf[col].apply(fmt_moeda_pdf)

    # Monta dados da tabela do PDF (cabeçalho + linhas)
    header = cols
    table_data = [header]

    for _, row in df_pdf[cols].iterrows():
        linha = [wrap(row[c]) for c in cols]
        table_data.append(linha)

    # Calcula largura disponível na página e largura de cada coluna
    page_width = pagesize[0] - 0.6 * inch
    col_width = page_width / max(1, len(header))
    col_widths = [col_width] * len(header)

    # Cria tabela do PDF
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
    # Gera o PDF no buffer
    doc.build(story)
    buffer.seek(0)

    from dash import dcc

    # Retorna arquivo PDF para download
    return dcc.send_bytes(buffer.getvalue(), "limite_gasto_itajuba_pdm.pdf")

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from dash import dcc
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.processos_service import (
    COL_CLASSIF_NC,
    COL_CONTR_REINSTR_COM,
    COL_DATA_ENTRADA,
    COL_DATA_FINALIZACAO,
    COL_MODALIDADE,
    COL_NUM_PROC,
    COL_OBJETO,
    COL_PRECO_ESTIMADO,
    COL_SOLICITANTE,
    COL_STATUS,
    COL_VALOR_CONTRATADO,
    formatar_moeda_brl,
)


wrap_style_compras = ParagraphStyle(
    name="wrap_compras",
    fontSize=7,
    leading=9,
    spaceAfter=2,
    wordWrap="CJK",
)

simple_style_compras = ParagraphStyle(
    name="simple_compras",
    fontSize=7,
    alignment=TA_CENTER,
)

header_cell_style_compras = ParagraphStyle(
    name="header_cell_compras",
    fontSize=7,
    alignment=TA_CENTER,
    fontName="Helvetica-Bold",
    textColor=colors.white,
)


def wrap_pdf_compras(text):
    return Paragraph(str(text), wrap_style_compras)


def simple_pdf_compras(text):
    return Paragraph(str(text), simple_style_compras)


def header_pdf_compras(text):
    return Paragraph(str(text), header_cell_style_compras)


def criar_card_elemento(titulo, valor):
    card_content = [
        [Paragraph(f"{valor}", ParagraphStyle("card_valor", alignment=TA_CENTER, spaceAfter=4))],
        [
            Paragraph(
                f"{titulo}",
                ParagraphStyle(
                    "card_titulo",
                    alignment=TA_CENTER,
                    textColor="#666666",
                    spaceAfter=0,
                ),
            )
        ],
    ]

    card_table = Table(card_content, colWidths=[1.5 * inch])
    card_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
                ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#DDDDDD")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return card_table


def criar_cards_resumo_pdf(story, df, pagesize):
    df_num = df.copy()
    df_num[COL_VALOR_CONTRATADO] = pd.to_numeric(
        df_num[COL_VALOR_CONTRATADO], errors="coerce"
    ).fillna(0)

    total_valor_contratado = df_num[COL_VALOR_CONTRATADO].sum()
    qtd_processos = len(df_num)
    media_por_processo = total_valor_contratado / qtd_processos if qtd_processos > 0 else 0.0

    concluidos = (df_num[COL_STATUS] == "Concluído").sum()
    em_andamento = (df_num[COL_STATUS] == "Em Andamento").sum()
    nao_concluidos = (df_num[COL_STATUS] == "Não Concluído").sum()

    story.append(Spacer(1, 0.08 * inch))

    card_data = [[
        criar_card_elemento("Valor Contratado", formatar_moeda_brl(total_valor_contratado)),
        criar_card_elemento("Média por Processo", formatar_moeda_brl(media_por_processo)),
        criar_card_elemento("Número de Processos", str(qtd_processos)),
        criar_card_elemento("Processos Concluídos", str(concluidos)),
        criar_card_elemento("Processos Em Andamento", str(em_andamento)),
        criar_card_elemento("Processos Não Concluídos", str(nao_concluidos)),
    ]]

    card_width = (pagesize[0] - 0.3 * inch) / 6 - 0.05 * inch
    cards_table = Table(card_data, colWidths=[card_width] * 6)
    cards_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("GRID", (0, 0), (-1, -1), 0, colors.transparent),
            ]
        )
    )
    story.append(cards_table)
    story.append(Spacer(1, 0.15 * inch))


def adicionar_cabecalho_compras(story, df, styles):
    assets_dir = Path("assets")
    logo_esq_path = assets_dir / "brasaobrasil.png"
    logo_dir_path = assets_dir / "simbolo_RGB.png"
    logo_esq = Image(str(logo_esq_path), 1.2 * inch, 1.2 * inch) if logo_esq_path.exists() else ""
    logo_dir = Image(str(logo_dir_path), 1.2 * inch, 1.2 * inch) if logo_dir_path.exists() else ""

    texto_instituicao = (
        "<b><font color='#0b2b57' size=13>Ministério da Educação</font></b><br/>"
        "<b><font color='#0b2b57' size=13>Universidade Federal de Itajubá</font></b><br/>"
        "<font color='#0b2b57' size=11>Diretoria de Compras e Contratos</font>"
    )

    instituicao = Paragraph(
        texto_instituicao,
        ParagraphStyle("instituicao", alignment=TA_CENTER, leading=16),
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
    story.append(
        Paragraph(
            "RELATÓRIO DE PROCESSOS DE COMPRAS",
            ParagraphStyle(
                "titulo_compras",
                alignment=TA_CENTER,
                fontSize=10,
                leading=14,
                textColor=colors.black,
            ),
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Total de registros: {len(df)}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))


def criar_tabela_dados_compras(story, df):
    if df.empty:
        return

    story.append(Spacer(1, 0.08 * inch))
    cols = [
        COL_SOLICITANTE,
        COL_NUM_PROC,
        COL_OBJETO,
        COL_MODALIDADE,
        COL_PRECO_ESTIMADO,
        COL_VALOR_CONTRATADO,
        COL_STATUS,
        COL_DATA_ENTRADA,
        COL_DATA_FINALIZACAO,
        COL_CLASSIF_NC,
        COL_CONTR_REINSTR_COM,
    ]
    cols = [c for c in cols if c in df.columns]

    header = [header_pdf_compras(c) for c in cols]
    table_data = [header]

    for _, row in df[cols].iterrows():
        linha = []
        for c in cols:
            valor = "" if pd.isna(row[c]) else str(row[c]).strip()
            linha.append(wrap_pdf_compras(valor) if c == COL_OBJETO else simple_pdf_compras(valor))
        table_data.append(linha)

    col_widths = [
        0.7 * inch,
        1.2 * inch,
        1.2 * inch,
        1.2 * inch,
        1.1 * inch,
        1.1 * inch,
        0.9 * inch,
        0.9 * inch,
        0.9 * inch,
        1.2 * inch,
        1.0 * inch,
    ][: len(cols)]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTWEIGHT", (0, 0), (-1, 0), "bold"),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#0b2b57")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                ("WORDWRAP", (0, 0), (-1, -1), True),
            ]
        )
    )
    story.append(tbl)


def gerar_pdf_processos(dados_proc):
    if not dados_proc:
        return None

    df = pd.DataFrame(dados_proc)
    df_cards = df.copy()
    df_cards[COL_VALOR_CONTRATADO] = pd.to_numeric(
        df_cards[COL_VALOR_CONTRATADO], errors="coerce"
    ).fillna(0)

    df_pdf = df.copy()
    df_pdf[COL_PRECO_ESTIMADO] = df_pdf[COL_PRECO_ESTIMADO].apply(formatar_moeda_brl)
    df_pdf[COL_VALOR_CONTRATADO] = df_pdf[COL_VALOR_CONTRATADO].apply(formatar_moeda_brl)
    df_pdf[COL_DATA_ENTRADA] = pd.to_datetime(
        df_pdf[COL_DATA_ENTRADA], format="%d/%m/%Y", errors="coerce"
    ).dt.strftime("%d/%m/%Y")
    df_pdf[COL_DATA_FINALIZACAO] = pd.to_datetime(
        df_pdf[COL_DATA_FINALIZACAO], errors="coerce"
    ).dt.strftime("%d/%m/%Y")

    buffer = BytesIO()
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=0.15 * inch,
        leftMargin=0.15 * inch,
        topMargin=0.2 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    story = []
    adicionar_cabecalho_compras(story, df_pdf, styles)
    criar_cards_resumo_pdf(story, df_cards, pagesize)
    criar_tabela_dados_compras(story, df_pdf)
    doc.build(story)
    buffer.seek(0)

    return dcc.send_bytes(
        buffer.getvalue(),
        f"processos_compras_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf",
    )

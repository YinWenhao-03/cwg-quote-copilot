from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import get_settings
from .models import QuoteDraft


def generate_quote_pdf(quote: QuoteDraft) -> Path:
    if quote.status != "approved":
        raise ValueError("未审批报价不能生成最终PDF")
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    path = get_settings().quotes_dir / quote.id / f"v{quote.version}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=18,
        alignment=TA_CENTER,
    )
    body = ParagraphStyle(
        "ChineseBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10, leading=16
    )
    public = quote.public_json
    story = [
        Paragraph("CWG 报价单（模拟）", title),
        Spacer(1, 8 * mm),
        Paragraph(f"报价编号：{quote.id}", body),
        Paragraph(f"版本：V{quote.version}", body),
        Paragraph(f"客户：{public.get('customer_name', '')}", body),
        Spacer(1, 5 * mm),
    ]
    table = Table(
        [
            ["产品", "数量", "单价", "币种", "贸易条款", "目的地"],
            [
                public.get("sku", ""),
                str(quote.quantity),
                str(quote.proposed_unit_price),
                quote.currency,
                public.get("incoterm", ""),
                public.get("destination", ""),
            ],
        ],
        colWidths=[34 * mm, 22 * mm, 28 * mm, 18 * mm, 25 * mm, 32 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9AA7B0")),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 7 * mm),
            Paragraph("报价有效期：批准之日起30日。", body),
            Paragraph("交付日期以双方最终订单确认结果为准。", body),
            Paragraph("本文件由CWG Quote Copilot模拟系统生成，不构成真实商业要约。", body),
        ]
    )
    doc.build(story)
    return path

from __future__ import annotations

import csv
import html
import io
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table as PdfTable, TableStyle


def _safe_text(value: Any, max_len: int = 32000) -> str:
    if value is None:
        return ""
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _pdf_text(value: Any, max_len: int = 32000) -> str:
    """Texto seguro para Paragraph de ReportLab.

    ReportLab interpreta <, > y & como markup. Si los datos clínicos o el SQL
    contienen esos caracteres sin escapar, el PDF puede romperse en generación.
    """
    return html.escape(_safe_text(value, max_len), quote=False).replace("\n", "<br/>")


def _report_title(title: str | None) -> str:
    cleaned = (title or "Reporte clínico NL-to-SQL").strip()
    return cleaned[:180] if cleaned else "Reporte clínico NL-to-SQL"


def to_csv_bytes(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)

    for row in rows:
        writer.writerow([_safe_text(row.get(col, ""), 2000) for col in columns])

    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def to_xlsx_bytes(
    columns: list[str],
    rows: list[dict],
    title: str | None = None,
    nl: str | None = None,
    sql: str | None = None,
    generated_at: str | None = None,
    max_rows: int | None = None,
) -> bytes:
    import re

    def clean_excel_text(value: Any, max_len: int = 32000) -> str:
        if value is None:
            return ""
        text = str(value)
        text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    def unique_headers(cols: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        result: list[str] = []

        for idx, col in enumerate(cols, start=1):
            base = clean_excel_text(col, 120).strip() or f"columna_{idx}"
            count = seen.get(base.lower(), 0) + 1
            seen[base.lower()] = count
            result.append(base if count == 1 else f"{base}_{count}")

        return result

    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte"

    generated = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_title = _report_title(title)
    headers = unique_headers(columns)

    title_fill = PatternFill("solid", fgColor="14532D")
    header_fill = PatternFill("solid", fgColor="D9F99D")
    info_fill = PatternFill("solid", fgColor="ECFDF5")
    stripe_fill = PatternFill("solid", fgColor="F8FAFC")

    white_font = Font(color="FFFFFF", bold=True)
    title_font = Font(color="FFFFFF", bold=True, size=16)
    header_font = Font(color="1F2937", bold=True)
    label_font = Font(color="1F2937", bold=True)
    normal_font = Font(color="374151")

    thin_gray = Side(style="thin", color="CBD5E1")
    border = Border(left=thin_gray, right=thin_gray, top=thin_gray, bottom=thin_gray)

    last_col = max(len(headers), 4)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws["A1"] = report_title
    ws["A1"].font = title_font
    ws["A1"].fill = title_fill
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30

    meta = [
        ("Generado", generated),
        ("Filas exportadas", str(len(rows))),
    ]

    if max_rows is not None:
        meta.append(("Límite de exportación", str(max_rows)))
    if nl:
        meta.append(("Consulta en lenguaje natural", nl))
    if sql:
        meta.append(("SQL generado", sql))

    row_idx = 3
    for label, value in meta:
        ws.cell(row=row_idx, column=1, value=label)
        ws.cell(row=row_idx, column=1).font = label_font
        ws.cell(row=row_idx, column=1).fill = info_fill
        ws.cell(row=row_idx, column=1).border = border
        ws.cell(row=row_idx, column=1).alignment = Alignment(vertical="top", wrap_text=True)

        ws.cell(row=row_idx, column=2, value=clean_excel_text(value))
        ws.cell(row=row_idx, column=2).font = normal_font
        ws.cell(row=row_idx, column=2).border = border
        ws.cell(row=row_idx, column=2).alignment = Alignment(vertical="top", wrap_text=True)

        if label in {"Consulta en lenguaje natural", "SQL generado"}:
            ws.row_dimensions[row_idx].height = 45

        row_idx += 1

    table_start = row_idx + 2

    for col_idx, col_name in enumerate(headers, start=1):
        cell = ws.cell(row=table_start, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r_idx, row in enumerate(rows, start=table_start + 1):
        for c_idx, original_col in enumerate(columns, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=clean_excel_text(row.get(original_col, "")))
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

            if (r_idx - table_start) % 2 == 0:
                cell.fill = stripe_fill

    end_row = max(table_start + len(rows), table_start)
    end_col = max(len(headers), 1)

    # Filtro simple de hoja, no tabla formal. Esto evita el error table1.xml.
    ws.auto_filter.ref = f"A{table_start}:{get_column_letter(end_col)}{end_row}"
    ws.freeze_panes = f"A{table_start + 1}"

    for idx, header in enumerate(headers, start=1):
        values = [clean_excel_text(header, 60)]
        values.extend(clean_excel_text(row.get(columns[idx - 1], ""), 60) for row in rows[:100])
        width = min(max(len(v) for v in values) + 3, 48)
        ws.column_dimensions[get_column_letter(idx)].width = width

    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 0, 18)

    info = wb.create_sheet("Información")
    info.append(["Campo", "Valor"])
    info.append(["Título", report_title])
    info.append(["Generado", generated])
    info.append(["Filas exportadas", len(rows)])

    if max_rows is not None:
        info.append(["Límite de exportación", max_rows])
    if nl:
        info.append(["Consulta en lenguaje natural", clean_excel_text(nl)])
    if sql:
        info.append(["SQL generado", clean_excel_text(sql)])

    for row in info.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = border

    info["A1"].font = white_font
    info["B1"].font = white_font
    info["A1"].fill = title_fill
    info["B1"].fill = title_fill
    info.column_dimensions["A"].width = 30
    info.column_dimensions["B"].width = 110

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf_bytes(
    title: str,
    columns: list[str],
    rows: list[dict],
    nl: str | None = None,
    sql: str | None = None,
    generated_at: str | None = None,
    max_rows: int | None = None,
) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=landscape(A4),
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=1.25 * cm,
        bottomMargin=1.15 * cm,
        title=_report_title(title),
        author="Clínica Veltra",
    )

    styles = getSampleStyleSheet()
    generated = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_title = _report_title(title)
    visible_columns = columns[:10]
    visible_rows = rows[:350]

    title_style = ParagraphStyle(
        "VeltraReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#005F80"),
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "VeltraSubtitle",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569"),
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "VeltraSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#005F80"),
        spaceBefore=10,
        spaceAfter=6,
    )
    normal_style = ParagraphStyle(
        "VeltraNormal",
        parent=styles["Normal"],
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
    )
    note_style = ParagraphStyle(
        "VeltraNote",
        parent=normal_style,
        fontSize=7.3,
        leading=9.2,
        textColor=colors.HexColor("#64748B"),
    )
    card_label_style = ParagraphStyle(
        "VeltraCardLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#005F80"),
        alignment=TA_CENTER,
    )
    card_value_style = ParagraphStyle(
        "VeltraCardValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_CENTER,
    )
    cell_style = ParagraphStyle(
        "VeltraCell",
        parent=styles["Normal"],
        fontSize=6.6,
        leading=7.8,
        textColor=colors.HexColor("#334155"),
        wordWrap="CJK",
    )
    header_style = ParagraphStyle(
        "VeltraHeaderCell",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#005F80"),
        alignment=TA_CENTER,
    )
    footer_style = ParagraphStyle(
        "VeltraFooter",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_RIGHT,
    )

    page_width, page_height = landscape(A4)
    available_width = page_width - doc.leftMargin - doc.rightMargin

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#0083B0"))
        canvas.rect(0, page_height - 0.45 * cm, page_width, 0.45 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#C6EB32"))
        canvas.rect(0, page_height - 0.45 * cm, 3.6 * cm, 0.45 * cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(colors.HexColor("#005F80"))
        canvas.drawString(0.35 * cm, page_height - 0.29 * cm, "CLÍNICA VELTRA")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(page_width - doc.rightMargin, 0.45 * cm, f"Página {document.page}")
        footer = Paragraph("Reporte generado automáticamente por la plataforma NL-to-SQL. Revise permisos y contexto clínico antes de tomar decisiones.", footer_style)
        footer.wrapOn(canvas, available_width - 1.5 * cm, 0.4 * cm)
        footer.drawOn(canvas, doc.leftMargin, 0.35 * cm)
        canvas.restoreState()

    story: list[Any] = []

    meta_cards = PdfTable(
        [
            [
                Paragraph("GENERADO", card_label_style),
                Paragraph("FILAS EXPORTADAS", card_label_style),
                Paragraph("COLUMNAS", card_label_style),
                Paragraph("LÍMITE", card_label_style),
            ],
            [
                Paragraph(_pdf_text(generated, 80), card_value_style),
                Paragraph(f"{len(rows):,}".replace(",", "."), card_value_style),
                Paragraph(str(len(columns)), card_value_style),
                Paragraph("Sin límite" if max_rows in (None, 0) else str(max_rows), card_value_style),
            ],
        ],
        colWidths=[available_width / 4] * 4,
        hAlign="LEFT",
    )
    meta_cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BAE6FD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BAE6FD")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.extend(
        [
            Paragraph("Reporte clínico y administrativo", subtitle_style),
            Paragraph(_pdf_text(report_title, 220), title_style),
            meta_cards,
            Spacer(1, 8),
        ]
    )

    if nl:
        story.append(
            KeepTogether(
                [
                    Paragraph("Consulta solicitada", section_style),
                    Paragraph(_pdf_text(nl, 1600), normal_style),
                ]
            )
        )

    if sql:
        story.append(
            KeepTogether(
                [
                    Paragraph("SQL generado", section_style),
                    Paragraph(_pdf_text(sql, 2200), normal_style),
                ]
            )
        )

    story.append(Paragraph("Resultados", section_style))

    if not visible_columns:
        story.append(Paragraph("Sin columnas para mostrar.", normal_style))
    elif not visible_rows:
        story.append(Paragraph("La consulta no devolvió filas.", normal_style))
    else:
        data = [[Paragraph(_pdf_text(c, 90), header_style) for c in visible_columns]]

        for row in visible_rows:
            data.append([Paragraph(_pdf_text(row.get(c, ""), 220), cell_style) for c in visible_columns])

        col_width = available_width / len(visible_columns)
        table = PdfTable(data, colWidths=[col_width] * len(visible_columns), repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9F99D")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#005F80")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

        notes: list[str] = []
        if len(columns) > len(visible_columns):
            notes.append(
                f"El PDF muestra las primeras {len(visible_columns)} columnas por legibilidad. Use Excel para revisar las {len(columns)} columnas completas."
            )
        if len(rows) > len(visible_rows):
            notes.append(
                f"El PDF muestra las primeras {len(visible_rows)} filas. Use Excel/CSV para revisar el total exportado."
            )
        if notes:
            story.append(Spacer(1, 6))
            story.append(Paragraph(" ".join(_pdf_text(note, 500) for note in notes), note_style))

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return out.getvalue()

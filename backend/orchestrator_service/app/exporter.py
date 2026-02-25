import io
import csv
from datetime import datetime

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def to_csv_bytes(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    return buf.getvalue().encode("utf-8")

def to_xlsx_bytes(columns: list[str], rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for r in rows:
        ws.append([r.get(c, "") for c in columns])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def to_pdf_bytes(title: str, columns: list[str], rows: list[dict]) -> bytes:
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, height - 40, title)
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 55, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    y = height - 85
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, " | ".join(columns[:6]) + (" ..." if len(columns) > 6 else ""))
    y -= 15
    c.setFont("Helvetica", 8)

    for r in rows[:60]:
        line = " | ".join(str(r.get(col, ""))[:22] for col in columns[:6])
        c.drawString(40, y, line)
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 40

    c.save()
    return out.getvalue()
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .security import require_user_id
from .models import QueryIn, QueryOut, FeedbackIn
from .orchestrator import run_query_flow, set_feedback, collect_rows_for_export
from .logs_repo import MongoLogsRepo
from .exporter import to_csv_bytes, to_xlsx_bytes, to_pdf_bytes

app = FastAPI(title="Orchestrator NL-to-SQL")

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logs_repo = MongoLogsRepo()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/query", response_model=QueryOut)
async def query(payload: QueryIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    return await run_query_flow(user_id, payload.nl, payload.page, payload.page_size)

@app.post("/reports/{report_id}/feedback")
def feedback(report_id: str, payload: FeedbackIn, authorization: str | None = Header(default=None)):
    _ = require_user_id(authorization)
    set_feedback(report_id, payload.value)
    return {"ok": True}

@app.get("/reports/{report_id}/export")
async def export(report_id: str, format: str, authorization: str | None = Header(default=None)):
    _ = require_user_id(authorization)

    doc = logs_repo.get_log(report_id)
    if not doc:
        raise HTTPException(404, "Reporte no existe")

    sql = doc["sql"]
    columns, rows = await collect_rows_for_export(sql)

    fmt = format.lower()
    if fmt == "csv":
        b = to_csv_bytes(columns, rows)
        return Response(b, media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={report_id}.csv"})

    if fmt == "xlsx":
        b = to_xlsx_bytes(columns, rows)
        return Response(b, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={report_id}.xlsx"})

    if fmt == "pdf":
        b = to_pdf_bytes(f"Reporte {report_id}", columns, rows)
        return Response(b, media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename={report_id}.pdf"})

    raise HTTPException(400, "format debe ser csv|xlsx|pdf")
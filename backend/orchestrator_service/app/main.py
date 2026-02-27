from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .security import require_user_id
from .models import (
    QueryIn, QueryOut, FeedbackIn,
    ConversationCreateIn, ConversationRenameIn, ConversationSelectIn,
    ConversationDetailOut
)
from .orchestrator import run_query_flow
from .logs_repo import MongoRepo
from .exporter import to_csv_bytes, to_xlsx_bytes, to_pdf_bytes
from .sql_client import execute_sql

app = FastAPI(title="Orchestrator NL-to-SQL")

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = MongoRepo()

@app.get("/health")
def health():
    return {"ok": True}

# ---------- Queries (crea reporte dentro de conversación) ----------
@app.post("/query", response_model=QueryOut)
async def query(payload: QueryIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    return await run_query_flow(user_id, payload.nl, payload.conversation_id, payload.page, payload.page_size)

# ---------- Conversations ----------
@app.get("/conversations")
def list_conversations(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    return repo.list_conversations(user_id)

@app.post("/conversations")
def create_conversation(payload: ConversationCreateIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    return repo.create_conversation(user_id, payload.title)

@app.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    conv = repo.get_conversation(user_id, conversation_id)
    if not conv:
        raise HTTPException(404, "Conversación no existe")
    reports = repo.list_reports(user_id, conversation_id)
    return {"conversation": conv, "reports": reports}

@app.post("/conversations/{conversation_id}/rename")
def rename_conversation(conversation_id: str, payload: ConversationRenameIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    ok = repo.rename_conversation(user_id, conversation_id, payload.title)
    if not ok:
        raise HTTPException(404, "No se pudo renombrar")
    return {"ok": True}

@app.post("/conversations/{conversation_id}/delete")
def delete_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    ok = repo.delete_conversation(user_id, conversation_id)
    if not ok:
        raise HTTPException(404, "No se pudo eliminar")
    return {"ok": True}

@app.post("/conversations/{conversation_id}/select")
def select_report(conversation_id: str, payload: ConversationSelectIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    ok = repo.select_report(user_id, conversation_id, payload.report_id)
    if not ok:
        raise HTTPException(400, "No se pudo seleccionar (no pertenece a la conversación)")
    return {"ok": True}

# ---------- Reports ----------
@app.post("/reports/{report_id}/feedback")
def feedback(report_id: str, payload: FeedbackIn, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    ok = repo.set_feedback(user_id, report_id, payload.value)
    if not ok:
        raise HTTPException(400, "No se pudo guardar feedback")
    return {"ok": True}

@app.get("/reports/{report_id}/meta")
def report_meta(report_id: str, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    doc = repo.get_report(user_id, report_id)
    if not doc:
        raise HTTPException(404, "Reporte no existe")
    return doc

@app.get("/reports/{report_id}/data")
async def report_data(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    user_id = require_user_id(authorization)
    doc = repo.get_report(user_id, report_id)
    if not doc:
        raise HTTPException(404, "Reporte no existe")
    sql = doc["sql"]
    return await execute_sql(sql, page=page, page_size=page_size)

@app.get("/reports/{report_id}/export")
async def export(report_id: str, format: str, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    doc = repo.get_report(user_id, report_id)
    if not doc:
        raise HTTPException(404, "Reporte no existe")

    # Export: re-ejecuta SQL por páginas hasta EXPORT_MAX_ROWS
    all_rows: list[dict] = []
    columns: list[str] = []
    p = 1
    size = 200
    while len(all_rows) < settings.EXPORT_MAX_ROWS:
        data = await execute_sql(doc["sql"], page=p, page_size=size)
        if not columns:
            columns = data["columns"]
        rows = data["rows"]
        all_rows.extend(rows)
        if len(rows) < size:
            break
        p += 1
    rows = all_rows[: settings.EXPORT_MAX_ROWS]

    fmt = format.lower()
    if fmt == "csv":
        b = to_csv_bytes(columns, rows)
        return Response(b, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_id}.csv"})
    if fmt == "xlsx":
        b = to_xlsx_bytes(columns, rows)
        return Response(b, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={report_id}.xlsx"})
    if fmt == "pdf":
        b = to_pdf_bytes(f"Reporte {report_id}", columns, rows)
        return Response(b, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={report_id}.pdf"})

    raise HTTPException(400, "format debe ser csv|xlsx|pdf")
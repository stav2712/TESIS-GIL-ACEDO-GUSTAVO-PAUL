from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .emailer import EmailAttachment, email_configured, send_email_with_attachments
from .exporter import to_csv_bytes, to_pdf_bytes, to_xlsx_bytes
from .logs_repo import MongoRepo, default_title
from .models import (
    AuditListOut,
    ConversationCreateIn,
    ConversationDetailOut,
    ConversationRenameIn,
    ConversationSelectIn,
    FeedbackIn,
    QueryIn,
    QueryJobOut,
    QueryJobStartOut,
    QueryOut,
    ReportEmailIn,
    ReportEmailOut,
    SystemConfigUpdateIn,
)
from .orchestrator import run_query_flow
from .policies import (
    apply_column_permissions_to_result,
    ensure_can_export,
    ensure_can_run_query,
    ensure_can_view_audit,
    ensure_can_view_config,
    ensure_sql_allowed_by_profile,
    visible_sql,
)
from .runtime_config import (
    RuntimeConfig,
    get_runtime_config,
    runtime_config_limits,
    runtime_config_warnings,
    update_runtime_config,
)
from .security import require_claims
from .sql_client import execute_sql, get_schema_columns

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


def _display_window_for_user(max_display_rows: int | None = None) -> int:
    # Valor global de plataforma: no depende del perfil del usuario.
    return get_runtime_config().query_display_max_rows


def _safe_filename(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text.strip().lower())
    return cleaned[:80] or "reporte"


def _public_report(doc: dict, can_view_sql: bool) -> dict:
    meta = doc.get("meta") or {}
    return {
        **doc,
        "sql": doc.get("sql", "") if can_view_sql else "",
        "nl_normalized": meta.get("nl_normalized"),
        "schema_profile": meta.get("schema_profile"),
        "resolved_terms": meta.get("resolved_terms", []),
        "resolved_values": meta.get("resolved_values", []),
        "translator_strategy": meta.get("translation_strategy"),
    }


def _allowed_tables() -> list[str]:
    return [x.strip() for x in settings.ALLOWED_TABLES.split(",") if x.strip()]


def _export_meaning(export_max_rows: int) -> str:
    if export_max_rows == 0:
        return "Sin límite duro; la exportación pagina internamente y no usa el límite visual."
    return f"La exportación se detiene al llegar a {export_max_rows} filas como máximo."


def _system_config_response(runtime: RuntimeConfig | None = None) -> dict:
    cfg = runtime or get_runtime_config()
    return {
        "query_display_max_rows": cfg.query_display_max_rows,
        "export_max_rows": cfg.export_max_rows,
        "export_max_rows_meaning": _export_meaning(cfg.export_max_rows),
        "export_page_size": settings.EXPORT_PAGE_SIZE,
        "query_timeout_seconds": cfg.query_timeout_seconds,
        "translator_timeout_seconds": settings.TRANSLATOR_TIMEOUT_SECONDS,
        "schema_profile_path": settings.SCHEMA_PROFILE_PATH,
        "allowed_tables": _allowed_tables(),
        "translator_url_configured": bool(settings.TRANSLATOR_URL),
        "query_url": settings.QUERY_URL,
        "terminology_url": settings.TERMINOLOGY_URL,
        "email_enabled": email_configured(),
        "email_from": settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or None,
        "limits": runtime_config_limits(),
        "warnings": runtime_config_warnings(cfg),
    }


def _ensure_can_manage_system_config(claims) -> None:
    ensure_can_view_config(claims)

    # No agregamos una migración de permisos para no romper perfiles existentes.
    # Solo perfiles con administración de perfiles (admin por defecto) pueden guardar cambios.
    if claims.profile != "admin" and not claims.can("can_manage_profiles"):
        raise HTTPException(403, "Solo un administrador puede modificar la configuración operativa")


def _base_from_endpoint_url(url: str, endpoint: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    endpoint = endpoint.rstrip("/")

    if path.lower().endswith(endpoint.lower()):
        path = path[: -len(endpoint)].rstrip("/")

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


async def _check_service(
    client: httpx.AsyncClient,
    *,
    key: str,
    label: str,
    configured_url: str,
    health_url: str,
) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()

    try:
        response = await client.get(health_url)
        ok = 200 <= response.status_code < 300
        detail = "OK" if ok else f"HTTP {response.status_code}"
        return {
            "key": key,
            "label": label,
            "configured_url": configured_url,
            "health_url": health_url,
            "ok": ok,
            "status_code": response.status_code,
            "detail": detail,
            "checked_at": checked_at,
        }
    except httpx.TimeoutException:
        return {
            "key": key,
            "label": label,
            "configured_url": configured_url,
            "health_url": health_url,
            "ok": False,
            "status_code": None,
            "detail": "Sin respuesta dentro del tiempo de diagnóstico",
            "checked_at": checked_at,
        }
    except httpx.RequestError as exc:
        return {
            "key": key,
            "label": label,
            "configured_url": configured_url,
            "health_url": health_url,
            "ok": False,
            "status_code": None,
            "detail": str(exc),
            "checked_at": checked_at,
        }


def _http_error_to_text(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    return str(detail)


async def _run_query_job(
    *,
    job_id: str,
    claims,
    nl: str,
    conversation_id: str,
    page: int,
    page_size: int,
) -> None:
    repo.mark_query_job_running(claims.user_id, job_id)

    try:
        result = await run_query_flow(claims, nl, conversation_id, page, page_size)
        repo.finish_query_job(claims.user_id, job_id, result)
    except HTTPException as exc:
        repo.fail_query_job(claims.user_id, job_id, _http_error_to_text(exc))
    except Exception as exc:
        repo.fail_query_job(claims.user_id, job_id, str(exc) or "Error al generar reporte")


def _public_query_job(doc: dict) -> dict:
    return {
        "job_id": doc.get("job_id"),
        "conversation_id": doc.get("conversation_id"),
        "nl": doc.get("nl") or "",
        "page": int(doc.get("page") or 1),
        "page_size": int(doc.get("page_size") or 50),
        "status": doc.get("status") or "queued",
        "report_id": doc.get("report_id"),
        "error": doc.get("error"),
        "result": doc.get("result"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "finished_at": doc.get("finished_at"),
    }


# ---------- Queries ----------
@app.post("/query", response_model=QueryOut)
async def query(payload: QueryIn, authorization: str | None = Header(default=None)):
    # Endpoint conservado por compatibilidad con clientes antiguos.
    # El frontend nuevo usa /query-jobs para que una pestaña cerrada no pierda el resultado.
    claims = require_claims(authorization)
    return await run_query_flow(
        claims,
        payload.nl,
        payload.conversation_id,
        payload.page,
        payload.page_size,
    )


@app.post("/query-jobs", response_model=QueryJobStartOut)
async def start_query_job(
    payload: QueryIn,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ensure_can_run_query(claims)

    if payload.conversation_id:
        conv = repo.get_conversation(claims.user_id, payload.conversation_id)
        if not conv:
            raise HTTPException(404, "Conversación no existe")
        conversation_id = payload.conversation_id
    else:
        conv = repo.create_conversation(claims.user_id, default_title(payload.nl))
        conversation_id = conv["conversation_id"]

    job = repo.create_query_job(
        user_id=claims.user_id,
        username=claims.username,
        conversation_id=conversation_id,
        nl=payload.nl,
        page=payload.page,
        page_size=payload.page_size,
    )
    background_tasks.add_task(
        _run_query_job,
        job_id=job["job_id"],
        claims=claims,
        nl=payload.nl,
        conversation_id=conversation_id,
        page=payload.page,
        page_size=payload.page_size,
    )
    return {"job_id": job["job_id"], "conversation_id": conversation_id, "status": job["status"]}


@app.get("/query-jobs", response_model=list[QueryJobOut])
def list_query_jobs(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    return [_public_query_job(job) for job in repo.list_active_query_jobs(claims.user_id)]


@app.get("/query-jobs/{job_id}", response_model=QueryJobOut)
def get_query_job(job_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    job = repo.get_query_job(claims.user_id, job_id, can_access_all=claims.can("can_view_audit"))
    if not job:
        raise HTTPException(404, "Trabajo no existe")
    return _public_query_job(job)


# ---------- Conversations ----------
@app.get("/conversations")
def list_conversations(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    return repo.list_conversations(claims.user_id)


@app.post("/conversations")
def create_conversation(payload: ConversationCreateIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    return repo.create_conversation(claims.user_id, payload.title)


@app.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)

    conv = repo.get_conversation(claims.user_id, conversation_id, can_access_all=claims.can("can_view_audit"))
    if not conv:
        raise HTTPException(404, "Conversación no existe")

    reports = repo.list_reports(claims.user_id, conversation_id, can_access_all=claims.can("can_view_audit"))
    reports = [_public_report(r, claims.can("can_view_sql")) for r in reports]

    return {"conversation": conv, "reports": reports}


@app.post("/conversations/{conversation_id}/rename")
def rename_conversation(
    conversation_id: str,
    payload: ConversationRenameIn,
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ok = repo.rename_conversation(claims.user_id, conversation_id, payload.title)
    if not ok:
        raise HTTPException(404, "No se pudo renombrar")
    return {"ok": True}


@app.post("/conversations/{conversation_id}/delete")
def delete_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ok = repo.delete_conversation(claims.user_id, conversation_id)
    if not ok:
        raise HTTPException(404, "No se pudo eliminar")
    return {"ok": True}


@app.post("/conversations/{conversation_id}/select")
def select_report(
    conversation_id: str,
    payload: ConversationSelectIn,
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ok = repo.select_report(claims.user_id, conversation_id, payload.report_id)
    if not ok:
        raise HTTPException(400, "No se pudo seleccionar (no pertenece a la conversación)")
    return {"ok": True}


# ---------- Reports ----------
@app.post("/reports/{report_id}/feedback")
def feedback(report_id: str, payload: FeedbackIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ok = repo.set_feedback(claims.user_id, report_id, payload.value)
    if not ok:
        raise HTTPException(400, "No se pudo guardar feedback")
    return {"ok": True}


@app.get("/reports/{report_id}/meta")
def report_meta(report_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    doc = repo.get_report(claims.user_id, report_id, can_access_all=claims.can("can_view_audit"))
    if not doc:
        raise HTTPException(404, "Reporte no existe")
    return _public_report(doc, claims.can("can_view_sql"))


@app.get("/reports/{report_id}/data")
async def report_data(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    doc = repo.get_report(claims.user_id, report_id, can_access_all=claims.can("can_view_audit"))
    if not doc:
        raise HTTPException(404, "Reporte no existe")

    sql = doc["sql"]
    ensure_sql_allowed_by_profile(sql, claims)
    data = await execute_sql(
        sql,
        page=page,
        page_size=min(page_size, claims.max_page_size, 50),
        max_result_window=_display_window_for_user(),
    )
    return apply_column_permissions_to_result(data, claims, sql)



EXPORT_FORMATS = {"csv", "xlsx", "pdf"}


def _normalize_export_formats(formats: list[str] | None) -> list[str]:
    requested = [str(fmt or "").strip().lower() for fmt in (formats or [])]
    if "all" in requested or "todos" in requested:
        return ["csv", "xlsx", "pdf"]

    normalized: list[str] = []
    for fmt in requested:
        if fmt == "excel":
            fmt = "xlsx"
        if fmt not in EXPORT_FORMATS:
            raise HTTPException(400, "formatos debe contener solo csv, xlsx/excel, pdf o all")
        if fmt not in normalized:
            normalized.append(fmt)

    if not normalized:
        raise HTTPException(400, "Selecciona al menos un formato")

    return normalized


async def _collect_report_rows_for_export(doc: dict, claims) -> tuple[list[str], list[dict], list[str], int | None]:
    sql = doc["sql"]
    ensure_sql_allowed_by_profile(sql, claims)

    all_rows: list[dict] = []
    columns: list[str] = []
    suppressed_columns: list[str] = []
    p = 1
    size = max(min(settings.EXPORT_PAGE_SIZE, 1000), 1)
    export_limit = max(get_runtime_config().export_max_rows, 0)

    while True:
        data = await execute_sql(sql, page=p, page_size=size, max_result_window=None)
        data = apply_column_permissions_to_result(data, claims, sql)

        if not columns:
            columns = data["columns"]
        if data.get("suppressed_columns"):
            suppressed_columns = data["suppressed_columns"]

        rows = data["rows"]
        all_rows.extend(rows)

        if export_limit and len(all_rows) >= export_limit:
            all_rows = all_rows[:export_limit]
            break

        total_pages = data.get("total_pages")
        if total_pages is not None and p >= total_pages:
            break

        if len(rows) < size:
            break

        p += 1

    return columns, all_rows, suppressed_columns, (export_limit if export_limit else None)


def _export_metadata(doc: dict, claims, suppressed_columns: list[str]) -> tuple[str, str | None, str, str, str | None]:
    sql = doc["sql"]
    nl = doc.get("nl") or ""
    timestamp = doc.get("timestamp")
    title = f"Reporte clínico NL-to-SQL - {nl[:90]}"
    filename_base = _safe_filename(nl[:50] or doc.get("report_id", "reporte"))

    # El permiso can_view_sql no bloquea la exportación de datos; solo controla
    # si el SQL generado aparece como metadata dentro de Excel/PDF.
    export_sql = sql if claims.can("can_view_sql") else None
    if suppressed_columns and export_sql:
        export_sql = f"{export_sql}\n\n-- Columnas ocultas para este perfil: {', '.join(suppressed_columns)}"

    return nl, timestamp, title, filename_base, export_sql


def _build_export_bytes(
    *,
    fmt: str,
    columns: list[str],
    rows: list[dict],
    title: str,
    nl: str,
    sql: str | None,
    timestamp: str | None,
    filename_base: str,
    max_rows: int | None,
) -> tuple[bytes, str, str, str]:
    if fmt == "csv":
        return (
            to_csv_bytes(columns, rows),
            f"reporte_{filename_base}.csv",
            "text/csv; charset=utf-8",
            "text/csv",
        )

    if fmt == "xlsx":
        return (
            to_xlsx_bytes(
                columns,
                rows,
                title=title,
                nl=nl,
                sql=sql,
                generated_at=timestamp,
                max_rows=max_rows,
            ),
            f"reporte_{filename_base}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if fmt == "pdf":
        return (
            to_pdf_bytes(
                title,
                columns,
                rows,
                nl=nl,
                sql=sql,
                generated_at=timestamp,
                max_rows=max_rows,
            ),
            f"reporte_{filename_base}.pdf",
            "application/pdf",
            "application/pdf",
        )

    raise HTTPException(400, "format debe ser csv|xlsx|pdf")


@app.get("/reports/{report_id}/export")
async def export(
    report_id: str,
    format: str = Query(..., pattern="^(csv|xlsx|pdf)$"),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ensure_can_export(claims)

    doc = repo.get_report(claims.user_id, report_id, can_access_all=claims.can("can_view_audit"))
    if not doc:
        raise HTTPException(404, "Reporte no existe")

    columns, all_rows, suppressed_columns, max_rows_label = await _collect_report_rows_for_export(doc, claims)
    nl, timestamp, title, filename_base, export_sql = _export_metadata(doc, claims, suppressed_columns)

    fmt = format.lower()
    b, filename, media_type, _content_type = _build_export_bytes(
        fmt=fmt,
        columns=columns,
        rows=all_rows,
        title=title,
        nl=nl,
        sql=export_sql,
        timestamp=timestamp,
        filename_base=filename_base,
        max_rows=max_rows_label,
    )
    return Response(
        b,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/reports/{report_id}/email", response_model=ReportEmailOut)
async def email_report(
    report_id: str,
    payload: ReportEmailIn,
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ensure_can_export(claims)

    if not claims.email:
        raise HTTPException(400, "Tu usuario no tiene correo electrónico configurado")

    formats = _normalize_export_formats(payload.formats)
    doc = repo.get_report(claims.user_id, report_id, can_access_all=claims.can("can_view_audit"))
    if not doc:
        raise HTTPException(404, "Reporte no existe")

    columns, all_rows, suppressed_columns, max_rows_label = await _collect_report_rows_for_export(doc, claims)
    nl, timestamp, title, filename_base, export_sql = _export_metadata(doc, claims, suppressed_columns)

    attachments: list[EmailAttachment] = []
    filenames: list[str] = []

    for fmt in formats:
        content, filename, _media_type, content_type = _build_export_bytes(
            fmt=fmt,
            columns=columns,
            rows=all_rows,
            title=title,
            nl=nl,
            sql=export_sql,
            timestamp=timestamp,
            filename_base=filename_base,
            max_rows=max_rows_label,
        )
        maintype, subtype = content_type.split("/", 1)
        attachments.append(
            EmailAttachment(
                filename=filename,
                content=content,
                maintype=maintype,
                subtype=subtype,
            )
        )
        filenames.append(filename)

    display_name = claims.full_name or claims.username or "usuario"
    formats_label = ", ".join(fmt.upper() if fmt != "xlsx" else "Excel" for fmt in formats)
    body = (
        f"Hola {display_name},\n\n"
        "Adjuntamos el reporte solicitado desde empresa REPORTS.\n\n"
        f"Consulta: {nl or 'Reporte clínico'}\n"
        f"Formatos: {formats_label}\n"
        f"Generado: {timestamp or datetime.now(timezone.utc).isoformat()}\n\n"
        "Este correo fue enviado automáticamente."
    )

    await run_in_threadpool(
        send_email_with_attachments,
        to_email=claims.email,
        subject=title[:180],
        body=body,
        attachments=attachments,
    )

    return ReportEmailOut(ok=True, to=claims.email, formats=formats, attachments=filenames)


# ---------- Plataforma / administración ----------
@app.get("/admin/dashboard")
def admin_dashboard(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ensure_can_view_audit(claims)
    return repo.dashboard_summary()


@app.get("/admin/audit/reports", response_model=AuditListOut)
def audit_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    ensure_can_view_audit(claims)

    data = repo.list_audit_reports(page=page, page_size=page_size, user_id=user_id, q=q)
    can_view_sql = claims.can("can_view_sql")
    data["rows"] = [
        {
            **row,
            "sql": visible_sql(row.get("sql", ""), claims) if not can_view_sql else row.get("sql", ""),
        }
        for row in data["rows"]
    ]
    return data


@app.get("/system/config")
def system_config(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ensure_can_view_config(claims)
    return _system_config_response()


@app.patch("/system/config")
def update_system_config(payload: SystemConfigUpdateIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    _ensure_can_manage_system_config(claims)

    cfg = update_runtime_config(payload.model_dump(exclude_unset=True))
    return _system_config_response(cfg)


@app.get("/system/schema")
async def system_schema(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ensure_can_view_config(claims)
    return await get_schema_columns()


@app.get("/system/status")
async def system_status(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ensure_can_view_config(claims)

    query_base = _base_from_endpoint_url(settings.QUERY_URL, "/execute")
    terminology_base = settings.TERMINOLOGY_URL.rstrip("/")
    translator_base = _base_from_endpoint_url(settings.TRANSLATOR_URL, "/translate")

    async with httpx.AsyncClient(timeout=15.0) as client:
        services = [
            await _check_service(
                client,
                key="query",
                label="Query service",
                configured_url=settings.QUERY_URL,
                health_url=_join_url(query_base, "/health"),
            ),
            await _check_service(
                client,
                key="terminology",
                label="Terminology service",
                configured_url=settings.TERMINOLOGY_URL,
                health_url=_join_url(terminology_base, "/health"),
            ),
            await _check_service(
                client,
                key="translator",
                label="Translator service",
                configured_url=settings.TRANSLATOR_URL,
                health_url=_join_url(translator_base, "/healthz"),
            ),
        ]

    return {"services": services}

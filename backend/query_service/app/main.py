from __future__ import annotations

import logging
from math import ceil
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .db import engine, get_db
from .guardrails import extract_tables, is_safe_select
from .sql_repair import repair_sql_for_dialect

app = FastAPI(title="Query Service")
logger = logging.getLogger("query_service")


ALLOWED = {
    t.strip().lower()
    for t in settings.ALLOWED_TABLES.split(",")
    if t.strip()
}


class ExecuteIn(BaseModel):
    sql: str = Field(min_length=1, max_length=50_000)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=1000)
    # Máximo de filas navegables/visibles para UI.
    # None o <=0 = sin límite visual; se usa para exportar todos los datos.
    max_result_window: int | None = Field(default=None, ge=0, le=250_000)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error in %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": _friendly_validation_message(exc.errors()), "error_code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "No se pudo ejecutar la consulta. Inténtalo nuevamente o contacta al administrador.",
            "error_code": "INTERNAL_ERROR",
        },
    )


def _validation_field_label(loc: tuple | list) -> str:
    name = str(loc[-1] if loc else "campo")
    return {
        "sql": "consulta SQL",
        "page": "página",
        "page_size": "tamaño de página",
        "max_result_window": "límite de visualización",
    }.get(name, name)


def _friendly_validation_message(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "Revisa los datos enviados. Hay campos obligatorios o con formato inválido."
    first = errors[0]
    field = _validation_field_label(first.get("loc") or [])
    kind = str(first.get("type") or "")
    if kind == "missing":
        return f"El campo {field} es obligatorio."
    if "string_too_short" in kind:
        return f"El campo {field} no puede estar vacío."
    if "string_too_long" in kind:
        return f"El campo {field} supera el tamaño máximo permitido."
    if "int" in kind or "float" in kind or "greater_than_equal" in kind or "less_than_equal" in kind:
        return f"El campo {field} debe tener un valor numérico válido dentro del rango permitido."
    return "Revisa los datos enviados. Hay campos obligatorios o con formato inválido."


@app.get("/health")
def health():
    return {"ok": True}


def _message(total_count: int, max_window: int | None) -> str | None:
    if max_window and max_window > 0 and total_count > max_window:
        return (
            f"La consulta devolvió {total_count} registros. "
            f"Por rendimiento, la vista se cortó a un máximo de {max_window} registros. "
            "La exportación descarga el conjunto completo permitido."
        )
    return None


def _split_table_name(table: str) -> tuple[str | None, str]:
    cleaned = table.strip().strip('"')
    if "." not in cleaned:
        return None, cleaned

    schema, name = cleaned.split(".", 1)
    return schema.strip().strip('"') or None, name.strip().strip('"')


def _apply_statement_timeout(db: Session) -> None:
    """Evita que una consulta permitida quede colgada indefinidamente en PostgreSQL."""
    if settings.DB_DIALECT.lower() != "postgresql":
        return

    timeout_seconds = max(float(getattr(settings, "QUERY_TIMEOUT_SECONDS", 300.0) or 300.0), 1.0)
    timeout_ms = int(timeout_seconds * 1000)
    # SET LOCAL solo dura la transacción actual y no cambia configuración global.
    db.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))


@app.get("/schema/columns")
def schema_columns():
    """
    Endpoint interno para que el orquestador muestre columnas configurables por vista.
    Solo expone tablas/vistas incluidas en ALLOWED_TABLES.
    """
    inspector = inspect(engine)
    tables: dict[str, list[str]] = {}
    errors: dict[str, str] = {}

    for table in sorted(ALLOWED):
        schema, name = _split_table_name(table)
        try:
            cols = inspector.get_columns(name, schema=schema)
            tables[table] = [str(col["name"]) for col in cols]
        except Exception as exc:
            # No rompemos toda la respuesta si una vista no existe o no es introspectable.
            tables[table] = []
            errors[table] = str(exc)

    return {"tables": tables, "errors": errors}


@app.post("/execute")
def execute(payload: ExecuteIn, db: Session = Depends(get_db)):
    original_sql = payload.sql.strip().rstrip(";")
    sql = repair_sql_for_dialect(original_sql, settings.DB_DIALECT).strip().rstrip(";")

    if not is_safe_select(sql):
        raise HTTPException(400, "Solo SELECT seguro permitido")

    used = extract_tables(sql)

    if used and not used.issubset(ALLOWED):
        raise HTTPException(
            400,
            {
                "error": "Tablas no permitidas",
                "tables": sorted(used - ALLOWED),
                "used_tables": sorted(used),
                "allowed_tables": sorted(ALLOWED),
            },
        )

    page = max(payload.page, 1)
    size = min(max(payload.page_size, 1), 1000)
    offset = (page - 1) * size

    max_window = payload.max_result_window
    if max_window is None:
        max_window = settings.QUERY_DISPLAY_MAX_ROWS
    if max_window is not None and max_window <= 0:
        max_window = None

    sql_for_count = sql
    count_sql = f"SELECT COUNT(*) AS total_count FROM ({sql_for_count}) AS __nl2sql_count"

    try:
        _apply_statement_timeout(db)

        count_res = db.execute(text(count_sql))
        total_count = int(count_res.scalar() or 0)

        display_total_count = min(total_count, max_window) if max_window else total_count
        total_pages = max(ceil(display_total_count / size), 1)

        if max_window and offset >= max_window:
            effective_size = 0
        elif max_window:
            effective_size = min(size, max_window - offset)
        else:
            effective_size = size

        if settings.DB_DIALECT.lower() == "mssql":
            sql_base = sql_for_count
            if " order by " not in sql_base.lower():
                sql_base += " ORDER BY 1"

            if effective_size <= 0:
                # Página fuera de la ventana visual. Devolvemos columnas sin filas.
                sql_paged = f"SELECT TOP 0 * FROM ({sql_for_count}) AS __nl2sql_empty"
            else:
                sql_paged = f"{sql_base} OFFSET {offset} ROWS FETCH NEXT {effective_size} ROWS ONLY"
        else:
            if effective_size <= 0:
                sql_paged = f"""
                SELECT *
                FROM ({sql_for_count}) AS __nl2sql_empty
                LIMIT 0
                """
            else:
                # En PostgreSQL paginamos envolviendo el SQL original.
                # Si el modelo generó un LIMIT explícito, se respeta dentro del subquery.
                sql_paged = f"""
                SELECT *
                FROM ({sql_for_count}) AS __nl2sql_page
                LIMIT {effective_size} OFFSET {offset}
                """

        res = db.execute(text(sql_paged))
        rows = [dict(r._mapping) for r in res.fetchall()]
        cols = list(res.keys())

        return {
            "columns": cols,
            "rows": rows,
            "page": page,
            "page_size": size,
            "row_count": len(rows),
            "total_count": total_count,
            "display_total_count": display_total_count,
            "total_pages": total_pages,
            "max_result_window": max_window,
            "max_result_window_exceeded": bool(max_window and total_count > max_window),
            "result_message": _message(total_count, max_window),
        }

    except SQLAlchemyError as e:
        db.rollback()

        original = getattr(e, "orig", None)
        detail = str(original) if original else str(e)
        logger.warning(
            "SQL execution failed. detail=%s sql_original=%s sql_repaired=%s sql_paged=%s",
            detail,
            original_sql,
            sql_for_count,
            locals().get("sql_paged"),
        )

        raise HTTPException(
            422,
            "La consulta generada no pudo ejecutarse correctamente. Reformula la pregunta o contacta al administrador.",
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Unexpected SQL execution error. sql_original=%s sql_repaired=%s sql_paged=%s",
            original_sql,
            sql_for_count,
            locals().get("sql_paged"),
        )

        raise HTTPException(
            500,
            "No se pudo ejecutar la consulta por un error interno. Inténtalo nuevamente o contacta al administrador.",
        )

from math import ceil

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .guardrails import extract_tables, is_safe_select

app = FastAPI(title="Query Service")

ALLOWED = {
    t.strip().lower()
    for t in settings.ALLOWED_TABLES.split(",")
    if t.strip()
}


class ExecuteIn(BaseModel):
    sql: str
    page: int = 1
    page_size: int = 50
    # Máximo de filas navegables/visibles para UI.
    # None o <=0 = sin límite visual; se usa para exportar todos los datos.
    max_result_window: int | None = None


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


@app.post("/execute")
def execute(payload: ExecuteIn, db: Session = Depends(get_db)):
    sql = payload.sql.strip().rstrip(";")

    if not is_safe_select(sql):
        raise HTTPException(400, "Solo SELECT permitido")

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

        raise HTTPException(
            422,
            {
                "error": "SQL falló al ejecutarse en la base de datos",
                "detail": detail,
                "sql_original": sql_for_count,
                "sql_paginado": locals().get("sql_paged"),
            },
        )

    except Exception as e:
        db.rollback()

        raise HTTPException(
            500,
            {
                "error": "Error interno ejecutando SQL",
                "detail": str(e),
                "sql_original": sql_for_count,
                "sql_paginado": locals().get("sql_paged"),
            },
        )

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .db import get_db
from .config import settings
from .guardrails import is_safe_select, extract_tables

app = FastAPI(title="Query Service")

ALLOWED = {t.strip().lower() for t in settings.ALLOWED_TABLES.split(",") if t.strip()}

class ExecuteIn(BaseModel):
    sql: str
    page: int = 1
    page_size: int = 50

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/execute")
def execute(payload: ExecuteIn, db: Session = Depends(get_db)):
    sql = payload.sql.strip().rstrip(";")
    if not is_safe_select(sql):
        raise HTTPException(400, "Solo SELECT permitido")

    used = extract_tables(sql)
    if used and not used.issubset(ALLOWED):
        raise HTTPException(400, f"Tablas no permitidas: {sorted(used - ALLOWED)}")

    page = max(payload.page, 1)
    size = min(max(payload.page_size, 1), 200)
    offset = (page - 1) * size

    # Paginación (para sqlite/postgres/mysql)
    if settings.DB_DIALECT.lower() == "mssql":
        # SQL Server: OFFSET/FETCH requiere ORDER BY; si no hay, agregamos uno simple.
        if " order by " not in sql.lower():
            sql += " ORDER BY 1"
        sql_paged = f"{sql} OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY"
    else:
        if " limit " in sql.lower():
            sql_paged = sql
        else:
            sql_paged = f"{sql} LIMIT {size} OFFSET {offset}"

    res = db.execute(text(sql_paged))
    rows = [dict(r._mapping) for r in res.fetchall()]
    cols = list(res.keys())
    return {"columns": cols, "rows": rows, "page": page, "page_size": size, "row_count": len(rows)}
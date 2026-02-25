from time import perf_counter
from fastapi import HTTPException
from .translator_client import translate_nl_to_sql
from .sql_client import execute_sql
from .logs_repo import MongoLogsRepo
from .config import settings

logs_repo = MongoLogsRepo()

async def run_query_flow(user_id: int, nl: str, page: int, page_size: int) -> dict:
    """
    Orquestador:
    - recibe NL + JWT -> extrae user_id
    - llama /translate -> obtiene SQL
    - envía al gestor SQL /execute -> resultados JSON paginados
    - registra log NoSQL {usuario, NL, SQL, timestamp, latencia, feedback} :contentReference[oaicite:15]{index=15} :contentReference[oaicite:16]{index=16}
    """
    t0 = perf_counter()
    sql = await translate_nl_to_sql(nl)
    data = await execute_sql(sql, page=page, page_size=page_size)
    latency_ms = int((perf_counter() - t0) * 1000)

    report_id = logs_repo.create_log(
        user_id=user_id,
        nl=nl,
        sql=sql,
        latency_ms=latency_ms,
    )

    return {
        "report_id": report_id,
        "sql": sql,
        "latency_ms": latency_ms,
        "columns": data["columns"],
        "rows": data["rows"],
        "page": data.get("page", page),
        "page_size": data.get("page_size", page_size),
        "row_count": data.get("row_count", len(data["rows"])),
    }

def set_feedback(report_id: str, value: str) -> None:
    if value not in ("up", "down"):
        raise HTTPException(400, "value debe ser 'up' o 'down'")
    ok = logs_repo.set_feedback(report_id, value)
    if not ok:
        raise HTTPException(404, "Reporte no existe")

async def collect_rows_for_export(sql: str) -> tuple[list[str], list[dict]]:
    """
    Exportación: trae páginas hasta EXPORT_MAX_ROWS.
    (Tu UI permite exportar CSV/Excel/PDF). :contentReference[oaicite:17]{index=17}
    """
    all_rows: list[dict] = []
    columns: list[str] = []
    page = 1
    page_size = 200

    while len(all_rows) < settings.EXPORT_MAX_ROWS:
        data = await execute_sql(sql, page=page, page_size=page_size)
        if not columns:
            columns = data["columns"]
        rows = data["rows"]
        all_rows.extend(rows)

        if len(rows) < page_size:
            break
        page += 1

    return columns, all_rows[: settings.EXPORT_MAX_ROWS]
from time import perf_counter
from fastapi import HTTPException
from .translator_client import translate_nl_to_sql
from .sql_client import execute_sql
from .logs_repo import MongoRepo, default_title

repo = MongoRepo()

async def run_query_flow(user_id: int, nl: str, conversation_id: str | None, page: int, page_size: int) -> dict:
    # si no viene conversation_id, crea conversación nueva con título basado en NL
    if conversation_id:
        conv = repo.get_conversation(user_id, conversation_id)
        if not conv:
            raise HTTPException(404, "Conversación no existe")
    else:
        conv = repo.create_conversation(user_id, default_title(nl))
        conversation_id = conv["conversation_id"]

    t0 = perf_counter()
    sql = await translate_nl_to_sql(nl)
    data = await execute_sql(sql, page=page, page_size=page_size)
    latency_ms = int((perf_counter() - t0) * 1000)

    report_doc = repo.add_report(user_id, conversation_id, nl, sql, latency_ms)
    conv2 = repo.get_conversation(user_id, conversation_id)

    return {
        "conversation_id": conversation_id,
        "report_id": report_doc["report_id"],
        "sql": sql,
        "timestamp": report_doc["timestamp"],
        "latency_ms": latency_ms,
        "columns": data["columns"],
        "rows": data["rows"],
        "page": data.get("page", page),
        "page_size": data.get("page_size", page_size),
        "row_count": data.get("row_count", len(data["rows"])),
        "selected_report_id": conv2.get("selected_report_id") if conv2 else None,
    }
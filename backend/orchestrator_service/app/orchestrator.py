from __future__ import annotations

from time import perf_counter

from fastapi import HTTPException

from .config import settings
from .logs_repo import MongoRepo, default_title
from .schema_loader import load_schema_profile
from .sql_client import execute_sql
from .translator_client import translate_nl_to_sql

repo = MongoRepo()

async def run_query_flow(user_id: int, nl: str, conversation_id: str | None, page: int, page_size: int) -> dict:
    if conversation_id:
        conv = repo.get_conversation(user_id, conversation_id)
        if not conv:
            raise HTTPException(404, "Conversación no existe")
    else:
        conv = repo.create_conversation(user_id, default_title(nl))
        conversation_id = conv["conversation_id"]

    schema = load_schema_profile(settings.SCHEMA_PROFILE_PATH)

    t0 = perf_counter()
    tr = await translate_nl_to_sql(
        nl=nl,
        schema_profile=schema.get("profile_name"),
        schema_context=schema,
    )
    sql = tr["sql"]
    data = await execute_sql(sql, page=page, page_size=page_size)
    latency_ms = int((perf_counter() - t0) * 1000)

    report_doc = repo.add_report(
        user_id,
        conversation_id,
        nl=nl,
        sql=sql,
        latency_ms=latency_ms,
        meta={
            "nl_normalized": tr.get("normalized"),
            "resolved_terms": tr.get("resolved_terms", []),
            "resolved_values": tr.get("resolved_values", []),
            "schema_profile": tr.get("schema_profile"),
            "translation_strategy": tr.get("strategy"),
        },
    )

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
        "translation_strategy": tr.get("strategy"),
    }
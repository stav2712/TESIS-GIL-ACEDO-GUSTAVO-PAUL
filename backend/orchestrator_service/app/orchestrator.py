from time import perf_counter

from fastapi import HTTPException

from .logs_repo import MongoRepo, default_title
from .schema_registry import load_schema_profile
from .sql_client import execute_sql
from .terminology_client import normalize_nl
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

    schema_profile = load_schema_profile()
    normalization = await normalize_nl(nl)

    translate_payload = {
        "nl": nl,
        "nl_original": nl,
        "nl_normalized": normalization.get("normalized") or nl,
        "resolved_terms": normalization.get("resolved_terms", []),
        "resolved_values": normalization.get("resolved_values", []),
        "schema_profile": schema_profile.get("profile_name"),
        "schema_context": schema_profile,
    }

    t0 = perf_counter()
    translation = await translate_nl_to_sql(translate_payload)
    sql = translation["sql"]
    data = await execute_sql(sql, page=page, page_size=page_size)
    latency_ms = int((perf_counter() - t0) * 1000)

    report_doc = repo.add_report(
        user_id,
        conversation_id,
        nl,
        sql,
        latency_ms,
        nl_normalized=translation.get("normalized") or normalization.get("normalized"),
        schema_profile=schema_profile.get("profile_name"),
        resolved_terms=translation.get("resolved_terms") or normalization.get("resolved_terms", []),
        resolved_values=translation.get("resolved_values") or normalization.get("resolved_values", []),
        translator_strategy=translation.get("strategy"),
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
        "nl_normalized": report_doc.get("nl_normalized"),
        "schema_profile": report_doc.get("schema_profile"),
        "resolved_terms": report_doc.get("resolved_terms", []),
        "resolved_values": report_doc.get("resolved_values", []),
        "translator_strategy": report_doc.get("translator_strategy"),
    }
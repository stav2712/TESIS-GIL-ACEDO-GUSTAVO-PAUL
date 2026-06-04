from __future__ import annotations

from time import perf_counter

from fastapi import HTTPException

from .config import settings
from .logs_repo import MongoRepo
from .nl_guard import NLGuardResult, ensure_valid_nl_query
from .policies import (
    apply_column_permissions_to_result,
    ensure_can_run_query,
    ensure_sql_allowed_by_profile,
    visible_sql,
)
from .report_title import generate_report_title
from .runtime_config import get_runtime_config
from .schema_loader import load_schema_profile
from .security import UserClaims
from .sql_client import execute_sql
from .translator_client import translate_nl_to_sql

repo = MongoRepo()


def _display_window_for_user(claims: UserClaims) -> int:
    # Valor global de plataforma: no depende del perfil del usuario.
    return get_runtime_config().query_display_max_rows


def _page_size_for_user(page_size: int, claims: UserClaims) -> int:
    return min(max(page_size, 1), max(int(claims.max_page_size or 50), 1), 50)


def _guard_meta(guard_result: NLGuardResult | None) -> dict:
    if guard_result is None:
        return {}
    return guard_result.to_meta()


async def run_query_flow(
    claims: UserClaims,
    nl: str,
    conversation_id: str | None,
    page: int,
    page_size: int,
    report_title: str | None = None,
) -> dict:
    ensure_can_run_query(claims)

    schema = load_schema_profile(settings.SCHEMA_PROFILE_PATH)

    # Validación previa al traductor. Si falla, no se llama a Modal ni se ejecuta SQL.
    # Se ejecuta antes de crear una conversación cuando se usa /query directo.
    guard_result = await ensure_valid_nl_query(nl, schema_context=schema)

    clean_report_title = report_title or await generate_report_title(nl)

    if conversation_id:
        conv = repo.get_conversation(claims.user_id, conversation_id)
        if not conv:
            raise HTTPException(404, "Conversación no existe")
    else:
        conv = repo.create_conversation(claims.user_id, clean_report_title)
        conversation_id = conv["conversation_id"]

    t0 = perf_counter()

    tr = await translate_nl_to_sql(
        nl=nl,
        user_id=claims.user_id,
        lang="es",
        schema_profile=schema.get("profile_name"),
        schema_context=schema,
    )

    sql = tr["sql"]
    ensure_sql_allowed_by_profile(sql, claims)

    data = await execute_sql(
        sql,
        page=page,
        page_size=_page_size_for_user(page_size, claims),
        max_result_window=_display_window_for_user(claims),
    )
    data = apply_column_permissions_to_result(data, claims, sql)

    latency_ms = int((perf_counter() - t0) * 1000)

    translator_response = tr.get("translator_response", {}) or {}

    report_doc = repo.add_report(
        user_id=claims.user_id,
        conversation_id=conversation_id,
        nl=nl,
        sql=sql,
        latency_ms=latency_ms,
        meta={
            "nl_normalized": tr.get("normalized"),
            "resolved_terms": tr.get("resolved_terms", []),
            "resolved_values": tr.get("resolved_values", []),
            "schema_profile": tr.get("schema_profile"),
            "translation_strategy": tr.get("strategy"),
            "translator_latency_ms": translator_response.get("latency_ms"),
            "translator_input_tokens": translator_response.get("input_tokens"),
            "translator_output_tokens": translator_response.get("output_tokens"),
            "translator_lang": translator_response.get("lang"),
            "translator_model_version": translator_response.get("model_version"),
            "translator_provider": "modal",
            "nl_guard": _guard_meta(guard_result),
            "max_result_window": data.get("max_result_window"),
            "max_result_window_exceeded": data.get("max_result_window_exceeded", False),
            "suppressed_columns": data.get("suppressed_columns", []),
        },
        user_snapshot={
            "username": claims.username,
            "full_name": claims.full_name,
            "profile": claims.profile,
        },
        report_title=clean_report_title,
    )

    conv2 = repo.get_conversation(claims.user_id, conversation_id)

    return {
        "conversation_id": conversation_id,
        "report_id": report_doc["report_id"],
        "report_title": report_doc.get("report_title") or clean_report_title,
        "sql": visible_sql(sql, claims),
        "timestamp": report_doc["timestamp"],
        "latency_ms": latency_ms,
        "columns": data.get("columns", []),
        "rows": data.get("rows", []),
        "page": data.get("page", page),
        "page_size": data.get("page_size", page_size),
        "row_count": data.get("row_count", 0),
        "total_count": data.get("total_count"),
        "display_total_count": data.get("display_total_count"),
        "total_pages": data.get("total_pages"),
        "max_result_window": data.get("max_result_window"),
        "max_result_window_exceeded": data.get("max_result_window_exceeded", False),
        "result_message": data.get("result_message"),
        "suppressed_columns": data.get("suppressed_columns", []),
        "selected_report_id": conv2.get("selected_report_id") if conv2 else None,
        "nl_normalized": tr.get("normalized"),
        "schema_profile": tr.get("schema_profile"),
        "resolved_terms": tr.get("resolved_terms", []),
        "resolved_values": tr.get("resolved_values", []),
        "translator_strategy": tr.get("strategy"),
        "can_view_sql": claims.can("can_view_sql"),
    }

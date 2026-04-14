from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from .config import settings

async def translate_nl_to_sql(
    nl: str,
    schema_profile: str | None = None,
    schema_context: dict[str, Any] | None = None,
    nl_normalized: str | None = None,
    resolved_terms: list[dict[str, Any]] | None = None,
    resolved_values: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "nl": nl,
        "nl_original": nl,
        "nl_normalized": nl_normalized,
        "schema_profile": schema_profile,
        "schema_context": schema_context or {},
        "resolved_terms": resolved_terms or [],
        "resolved_values": resolved_values or [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(settings.TRANSLATOR_URL, json=payload)
    if r.status_code != 200:
        raise HTTPException(502, f"Translator error: {r.text}")

    data = r.json()
    sql = data.get("sql")
    if not sql:
        raise HTTPException(502, "Translator no devolvió SQL")
    return data
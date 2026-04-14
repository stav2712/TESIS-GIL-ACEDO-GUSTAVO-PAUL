from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from translator_service.baseline_rules import generate_sql_from_rules
from translator_service.model_runtime import NL2SQLModelRuntime
from translator_service.sql_utils import ensure_select_only, extract_sql_from_text

app = FastAPI(title="Translator Service (NL-to-SQL)")

TERMINOLOGY_URL = os.getenv("TERMINOLOGY_URL", "http://127.0.0.1:8004/normalize")
USE_RULE_FALLBACK = os.getenv("USE_RULE_FALLBACK", "true").lower() == "true"
RETURN_PROMPT_PREVIEW = os.getenv("RETURN_PROMPT_PREVIEW", "false").lower() == "true"

runtime = NL2SQLModelRuntime()

class TranslateIn(BaseModel):
    nl: str | None = None
    nl_original: str | None = None
    nl_normalized: str | None = None
    schema_profile: str | None = None
    schema_context: dict[str, Any] | None = None
    resolved_terms: list[dict[str, Any]] = Field(default_factory=list)
    resolved_values: list[dict[str, Any]] = Field(default_factory=list)

@app.get("/health")
def health():
    return {
        "ok": True,
        "model_backend": runtime.backend,
        "model_source": runtime.source,
        "model_loaded": runtime.loaded,
        "model_device": runtime.device,
        "rule_fallback": USE_RULE_FALLBACK,
        "load_error": runtime.load_error,
    }

async def normalize_if_needed(payload: TranslateIn) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    nl_original = (payload.nl_original or payload.nl or "").strip()
    normalized = payload.nl_normalized
    resolved_terms = payload.resolved_terms
    resolved_values = payload.resolved_values

    if normalized:
        return normalized, resolved_terms, resolved_values

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(TERMINOLOGY_URL, json={"text": nl_original})
    if r.status_code != 200:
        raise HTTPException(502, "Terminology service no disponible")

    data = r.json()
    return (
        data.get("normalized") or nl_original,
        data.get("resolved_terms", []),
        data.get("resolved_values", []),
    )

@app.post("/translate")
async def translate(payload: TranslateIn):
    nl_original = (payload.nl_original or payload.nl or "").strip()
    if not nl_original:
        raise HTTPException(400, "Falta texto de entrada")

    normalized, resolved_terms, resolved_values = await normalize_if_needed(payload)

    try:
        result = runtime.generate(
            nl_original=nl_original,
            nl_normalized=normalized,
            schema_profile=payload.schema_profile,
            schema_context=payload.schema_context,
            resolved_terms=resolved_terms,
            resolved_values=resolved_values,
        )
        sql = ensure_select_only(extract_sql_from_text(result.sql))
        response = {
            "sql": sql,
            "normalized": normalized,
            "resolved_terms": resolved_terms,
            "resolved_values": resolved_values,
            "strategy": result.strategy,
            "schema_profile": payload.schema_profile,
        }
        if RETURN_PROMPT_PREVIEW:
            response["prompt_preview"] = result.prompt_preview
        return response
    except Exception as e:
        if not USE_RULE_FALLBACK:
            raise HTTPException(500, f"Model generation failed: {e}")

        fallback = generate_sql_from_rules(
            text=normalized or nl_original,
            resolved_terms=resolved_terms,
            resolved_values=resolved_values,
        )
        return {
            "sql": fallback.sql,
            "normalized": normalized,
            "resolved_terms": resolved_terms,
            "resolved_values": resolved_values,
            "strategy": fallback.strategy,
            "schema_profile": payload.schema_profile,
            "fallback_reason": str(e),
        }
from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from translator_service.baseline_rules import generate_sql_from_rules
from translator_service.model_runtime import NL2SQLModelRuntime

app = FastAPI(title="Translator Service (NL-to-SQL)")

TERMINOLOGY_URL = os.getenv("TERMINOLOGY_URL", "http://127.0.0.1:8004/normalize")
USE_RULE_FALLBACK = os.getenv("USE_RULE_FALLBACK", "true").lower() == "true"

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
        "model_name": runtime.model_name,
        "device": runtime.device,
        "rule_fallback": USE_RULE_FALLBACK,
    }


@app.post("/translate")
async def translate(payload: TranslateIn):
    nl_original = (payload.nl_original or payload.nl or "").strip()
    if not nl_original:
        raise HTTPException(400, "Falta texto de entrada")

    nl_normalized = payload.nl_normalized
    resolved_terms = payload.resolved_terms
    resolved_values = payload.resolved_values

    if not nl_normalized:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(TERMINOLOGY_URL, json={"text": nl_original})
        if r.status_code != 200:
            raise HTTPException(502, "Terminology service no disponible")
        data = r.json()
        nl_normalized = data.get("normalized")
        resolved_terms = data.get("resolved_terms", [])
        resolved_values = data.get("resolved_values", [])

    try:
        result = runtime.generate(
            nl_original=nl_original,
            nl_normalized=nl_normalized,
            schema_profile=payload.schema_profile,
            schema_context=payload.schema_context,
            resolved_terms=resolved_terms,
            resolved_values=resolved_values,
        )
        return {
            "sql": result.sql,
            "normalized": nl_normalized,
            "resolved_terms": resolved_terms,
            "resolved_values": resolved_values,
            "strategy": result.strategy,
            "schema_profile": payload.schema_profile,
        }
    except Exception as e:
        if not USE_RULE_FALLBACK:
            raise HTTPException(500, f"Model generation failed: {e}")

        rule_result = generate_sql_from_rules(
            text=nl_normalized or nl_original,
            resolved_terms=resolved_terms,
            resolved_values=resolved_values,
        )
        return {
            "sql": rule_result.sql,
            "normalized": nl_normalized,
            "resolved_terms": resolved_terms,
            "resolved_values": resolved_values,
            "strategy": rule_result.strategy,
            "schema_profile": payload.schema_profile,
        }
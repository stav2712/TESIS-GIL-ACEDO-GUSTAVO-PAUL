from __future__ import annotations

from typing import Any
import httpx
from fastapi import HTTPException

from .config import settings


def _translate_url() -> str:
    """
    Permite configurar TRANSLATOR_URL como:
    - https://...modal.run
    - https://...modal.run/translate
    """
    url = settings.TRANSLATOR_URL.rstrip("/")
    if not url.endswith("/translate"):
        url = f"{url}/translate"
    return url


async def translate_nl_to_sql(
    nl: str,
    user_id: int,
    lang: str = "es",
    schema_profile: str | None = None,
    schema_context: dict[str, Any] | None = None,
    nl_normalized: str | None = None,
    resolved_terms: list[dict[str, Any]] | None = None,
    resolved_values: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Llama al endpoint real de Modal:

    POST /translate
    {
      "question": "...",
      "lang": "es",
      "user_id": "..."
    }

    La API de Modal devuelve:
    {
      "sql": "...",
      "latency_ms": ...,
      "input_tokens": ...,
      "output_tokens": ...,
      "lang": "es",
      "model_version": "..."
    }
    """

    payload = {
        "question": nl,
        "lang": lang,
        "user_id": str(user_id),
    }

    url = _translate_url()

    try:
        async with httpx.AsyncClient(timeout=settings.TRANSLATOR_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Timeout llamando al motor NL-to-SQL en Modal: {exc}",
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar al motor NL-to-SQL en Modal: {exc}",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Translator error {response.status_code}: {response.text}",
        )

    try:
        data = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"El traductor no devolvió JSON válido: {exc}",
        )

    sql = (data.get("sql") or "").strip()

    if not sql:
        raise HTTPException(
            status_code=502,
            detail=f"El traductor no devolvió SQL. Respuesta: {data}",
        )

    # Normalizamos la respuesta para que el resto del sistema no dependa
    # directamente del formato específico de Modal.
    return {
        "sql": sql,
        "normalized": nl_normalized,
        "resolved_terms": resolved_terms or [],
        "resolved_values": resolved_values or [],
        "schema_profile": schema_profile,
        "strategy": "modal_qwen25_7b_instruct_qlora",
        "translator_payload": payload,
        "translator_response": {
            "latency_ms": data.get("latency_ms"),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "lang": data.get("lang"),
            "model_version": data.get("model_version"),
        },
    }
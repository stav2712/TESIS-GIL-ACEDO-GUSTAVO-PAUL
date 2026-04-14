import httpx
from fastapi import HTTPException

from .config import settings

async def translate_nl_to_sql(payload: dict) -> dict:
    """
    Llama a /translate del Motor NL-to-SQL con contexto enriquecido:
    NL original/normalizado, términos resueltos y schema-linking.
    """
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.post(settings.TRANSLATOR_URL, json=payload)
    if r.status_code != 200:
        raise HTTPException(502, f"Translator error: {r.text}")
    data = r.json()
    if not data.get("sql"):
        raise HTTPException(502, "Translator no devolvió SQL")
    return data
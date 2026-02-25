import httpx
from fastapi import HTTPException
from .config import settings

async def translate_nl_to_sql(nl: str) -> str:
    """
    Llama a /translate del Motor NL-to-SQL. :contentReference[oaicite:10]{index=10}
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(settings.TRANSLATOR_URL, json={"nl": nl})
    if r.status_code != 200:
        raise HTTPException(502, f"Translator error: {r.text}")
    data = r.json()
    sql = data.get("sql")
    if not sql:
        raise HTTPException(502, "Translator no devolvió SQL")
    return sql
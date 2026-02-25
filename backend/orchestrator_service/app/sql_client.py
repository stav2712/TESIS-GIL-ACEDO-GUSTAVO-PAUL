import httpx
from fastapi import HTTPException
from .config import settings

async def execute_sql(sql: str, page: int, page_size: int) -> dict:
    """
    Envía SQL al Gestor de Consultas (ejecuta y devuelve JSON paginado). :contentReference[oaicite:11]{index=11}
    """
    payload = {"sql": sql, "page": page, "page_size": page_size}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(settings.QUERY_URL, json=payload)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()
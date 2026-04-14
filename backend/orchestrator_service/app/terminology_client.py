import httpx
from fastapi import HTTPException

from .config import settings


async def normalize_nl(text: str) -> dict:
    url = settings.TERMINOLOGY_URL.rstrip("/") + "/normalize"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json={"text": text})
    if r.status_code != 200:
        raise HTTPException(502, f"Terminology error: {r.text}")
    return r.json()
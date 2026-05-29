from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException

from .config import settings
from .runtime_config import get_runtime_config


def _query_service_base_url() -> str:
    parsed = urlsplit(settings.QUERY_URL)
    path = parsed.path.rstrip("/")
    if path.lower().endswith("/execute"):
        path = path[: -len("/execute")].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


async def execute_sql(
    sql: str,
    page: int,
    page_size: int,
    max_result_window: int | None = None,
) -> dict:
    payload = {
        "sql": sql,
        "page": page,
        "page_size": page_size,
        "max_result_window": max_result_window,
    }

    timeout_seconds = get_runtime_config().query_timeout_seconds

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            r = await client.post(settings.QUERY_URL, json=payload)
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Timeout ejecutando SQL en query_service",
                "detail": str(e),
                "timeout_seconds": timeout_seconds,
                "sql": sql,
            },
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "No se pudo conectar con query_service",
                "detail": str(e),
            },
        )

    if r.status_code != 200:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)

    return r.json()


async def get_schema_columns() -> dict:
    """Devuelve las columnas de las vistas permitidas globalmente desde query_service."""
    url = _join_url(_query_service_base_url(), "/schema/columns")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Timeout consultando el esquema en query_service",
                "detail": str(e),
            },
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "No se pudo conectar con query_service para leer el esquema",
                "detail": str(e),
            },
        )

    if r.status_code != 200:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)

    return r.json()

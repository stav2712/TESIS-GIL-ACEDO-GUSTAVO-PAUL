import httpx
from fastapi import HTTPException

from .config import settings
from .runtime_config import get_runtime_config


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

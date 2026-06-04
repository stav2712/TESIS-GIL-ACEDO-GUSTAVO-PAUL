from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .emailer import email_configured
from .policies import ensure_can_view_config
from .runtime_config import (
    RuntimeConfig,
    get_runtime_config,
    runtime_config_limits,
    runtime_config_options,
    runtime_config_warnings,
    update_runtime_config,
)
from .security import require_claims

router = APIRouter(tags=["system-config"])


class SystemConfigUpdateIn(BaseModel):
    # Operativo existente: se mantiene igual y todos son opcionales para guardado parcial.
    query_display_max_rows: int | None = Field(default=None, ge=50, le=100_000)
    export_max_rows: int | None = Field(default=None, ge=0, le=250_000)
    query_timeout_seconds: float | None = Field(default=None, ge=30.0, le=900.0)

    # Solo las tres nuevas opciones solicitadas.
    ui_language: Literal["es", "en"] | None = None
    default_theme: Literal["system", "light", "dark"] | None = None
    institutional_notice: str | None = Field(default=None, max_length=280)


def _allowed_tables() -> list[str]:
    return [x.strip() for x in settings.ALLOWED_TABLES.split(",") if x.strip()]


def _export_meaning(export_max_rows: int) -> str:
    if export_max_rows == 0:
        return "Sin límite duro; la exportación pagina internamente y no usa el límite visual."
    return f"La exportación se detiene al llegar a {export_max_rows} filas como máximo."


def _system_config_response(runtime: RuntimeConfig | None = None) -> dict:
    cfg = runtime or get_runtime_config()
    return {
        # Campos operativos existentes.
        "query_display_max_rows": cfg.query_display_max_rows,
        "export_max_rows": cfg.export_max_rows,
        "export_max_rows_meaning": _export_meaning(cfg.export_max_rows),
        "export_page_size": settings.EXPORT_PAGE_SIZE,
        "query_timeout_seconds": cfg.query_timeout_seconds,
        "translator_timeout_seconds": settings.TRANSLATOR_TIMEOUT_SECONDS,
        "schema_profile_path": settings.SCHEMA_PROFILE_PATH,
        "allowed_tables": _allowed_tables(),
        "translator_url_configured": bool(settings.TRANSLATOR_URL),
        "query_url": settings.QUERY_URL,
        "terminology_url": settings.TERMINOLOGY_URL,
        "email_enabled": email_configured(),
        "email_from": settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or None,
        "limits": runtime_config_limits(),
        "warnings": runtime_config_warnings(cfg),
        # Nuevos campos configurables visibles en UI.
        "ui_language": cfg.ui_language,
        "default_theme": cfg.default_theme,
        "institutional_notice": cfg.institutional_notice,
        "options": runtime_config_options(),
    }


def _public_config_response(runtime: RuntimeConfig | None = None) -> dict:
    cfg = runtime or get_runtime_config()
    return {
        "ui_language": cfg.ui_language,
        "default_theme": cfg.default_theme,
        "institutional_notice": cfg.institutional_notice,
    }


def _ensure_can_manage_system_config(claims) -> None:
    ensure_can_view_config(claims)
    # Conserva la regla anterior: solo admin o quien pueda gestionar perfiles modifica config.
    if claims.profile != "admin" and not claims.can("can_manage_profiles"):
        raise HTTPException(403, "Solo un administrador puede modificar la configuración del sistema")


@router.get("/system/config")
def system_config(authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    ensure_can_view_config(claims)
    return _system_config_response()


@router.patch("/system/config")
def update_system_config(payload: SystemConfigUpdateIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    _ensure_can_manage_system_config(claims)
    cfg = update_runtime_config(payload.model_dump(exclude_unset=True))
    return _system_config_response(cfg)


@router.get("/system/public-config")
def public_system_config(authorization: str | None = Header(default=None)):
    # No devuelve secretos, pero exige sesión para que el aviso no sea público anónimo.
    require_claims(authorization)
    return _public_config_response()

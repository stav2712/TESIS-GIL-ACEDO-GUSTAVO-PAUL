from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import settings


MIN_DISPLAY_ROWS = 50
MAX_DISPLAY_ROWS = 100_000

# 0 conserva el significado actual: sin límite duro de exportación.
# Si se define un límite, evitamos valores demasiado bajos que confundan al usuario.
MIN_EXPORT_ROWS_WHEN_ENABLED = 100
MAX_EXPORT_ROWS = 250_000

MIN_QUERY_TIMEOUT_SECONDS = 30.0
MAX_QUERY_TIMEOUT_SECONDS = 900.0
LOW_QUERY_TIMEOUT_WARNING_SECONDS = 60.0

_RUNTIME_KEYS = {
    "query_display_max_rows",
    "export_max_rows",
    "query_timeout_seconds",
}


class RuntimeConfig(BaseModel):
    query_display_max_rows: int = Field(ge=MIN_DISPLAY_ROWS, le=MAX_DISPLAY_ROWS)
    export_max_rows: int = Field(ge=0, le=MAX_EXPORT_ROWS)
    query_timeout_seconds: float = Field(ge=MIN_QUERY_TIMEOUT_SECONDS, le=MAX_QUERY_TIMEOUT_SECONDS)

    @field_validator("export_max_rows")
    @classmethod
    def validate_export_limit(cls, value: int) -> int:
        if value != 0 and value < MIN_EXPORT_ROWS_WHEN_ENABLED:
            raise ValueError(
                f"Usa 0 para exportación sin límite o un valor >= {MIN_EXPORT_ROWS_WHEN_ENABLED}."
            )
        return value


def _settings_default_config() -> RuntimeConfig:
    display_rows = max(int(settings.QUERY_DISPLAY_MAX_ROWS or MIN_DISPLAY_ROWS), MIN_DISPLAY_ROWS)
    display_rows = min(display_rows, MAX_DISPLAY_ROWS)

    export_rows = max(int(settings.EXPORT_MAX_ROWS or 0), 0)
    if 0 < export_rows < MIN_EXPORT_ROWS_WHEN_ENABLED:
        export_rows = MIN_EXPORT_ROWS_WHEN_ENABLED
    export_rows = min(export_rows, MAX_EXPORT_ROWS)

    timeout_seconds = float(settings.QUERY_TIMEOUT_SECONDS or 300.0)
    timeout_seconds = min(max(timeout_seconds, MIN_QUERY_TIMEOUT_SECONDS), MAX_QUERY_TIMEOUT_SECONDS)

    raw = {
        "query_display_max_rows": display_rows,
        "export_max_rows": export_rows,
        "query_timeout_seconds": timeout_seconds,
    }

    return _validate_runtime_config(raw)


def _config_path() -> Path:
    return Path(settings.SYSTEM_RUNTIME_CONFIG_PATH)


def _validate_runtime_config(raw: dict[str, Any]) -> RuntimeConfig:
    try:
        return RuntimeConfig.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Configuración operativa inválida",
                "detail": exc.errors(),
                "limits": runtime_config_limits(),
            },
        )


def _read_saved_overrides() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Si el archivo fue editado manualmente y quedó inválido, no rompemos el arranque.
        # El panel volverá a guardar un JSON correcto.
        return {}

    if not isinstance(raw, dict):
        return {}

    return {key: raw[key] for key in _RUNTIME_KEYS if key in raw}


def _load_runtime_config() -> RuntimeConfig:
    defaults = _settings_default_config()
    overrides = _read_saved_overrides()

    if not overrides:
        return defaults

    raw = defaults.model_dump()
    raw.update(overrides)

    try:
        return _validate_runtime_config(raw)
    except HTTPException:
        # No dejamos que una edición manual inválida del JSON impida arrancar el sistema.
        return defaults


def _persist_runtime_config(config: RuntimeConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


_lock = RLock()
_runtime_config = _load_runtime_config()


def get_runtime_config() -> RuntimeConfig:
    with _lock:
        return _runtime_config.model_copy()


def update_runtime_config(patch: dict[str, Any]) -> RuntimeConfig:
    global _runtime_config

    clean_patch = {key: value for key, value in patch.items() if key in _RUNTIME_KEYS and value is not None}

    with _lock:
        raw = _runtime_config.model_dump()
        raw.update(clean_patch)
        next_config = _validate_runtime_config(raw)
        _persist_runtime_config(next_config)

        _runtime_config = next_config
        return _runtime_config.model_copy()


def runtime_config_limits() -> dict[str, dict[str, float | int]]:
    return {
        "query_display_max_rows": {
            "min": MIN_DISPLAY_ROWS,
            "max": MAX_DISPLAY_ROWS,
        },
        "export_max_rows": {
            "min": 0,
            "min_when_enabled": MIN_EXPORT_ROWS_WHEN_ENABLED,
            "max": MAX_EXPORT_ROWS,
            "unlimited_value": 0,
        },
        "query_timeout_seconds": {
            "min": MIN_QUERY_TIMEOUT_SECONDS,
            "max": MAX_QUERY_TIMEOUT_SECONDS,
            "warning_below": LOW_QUERY_TIMEOUT_WARNING_SECONDS,
        },
    }


def runtime_config_warnings(config: RuntimeConfig | None = None) -> list[str]:
    cfg = config or get_runtime_config()
    warnings: list[str] = []

    if cfg.query_timeout_seconds < LOW_QUERY_TIMEOUT_WARNING_SECONDS:
        warnings.append(
            "Timeout SQL bajo: algunas consultas pueden cortarse antes de que PostgreSQL responda."
        )

    if cfg.export_max_rows == 0:
        warnings.append(
            "La exportación está sin límite duro; úsalo solo si el volumen de datos está controlado."
        )

    return warnings

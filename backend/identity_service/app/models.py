from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


TABLE_ACCESS_MODES = {"all", "custom"}


def normalize_table_access_mode(value: Any) -> str:
    mode = str(value or "all").strip().lower()
    return mode if mode in TABLE_ACCESS_MODES else "all"


DEFAULT_PERMISSIONS: dict[str, bool] = {
    "can_query": False,
    "can_export": False,
    "can_view_sql": False,
    "can_manage_users": False,
    "can_manage_profiles": False,
    "can_view_audit": False,
    "can_view_system_config": False,
}


def _normalize_column_permissions(value: Any) -> dict[str, dict[str, list[str]]]:
    """
    Estructura persistida:
    {
      "reporting.vw_pacientes": {
        "hidden": ["nombre_completo"],
        "forbidden": ["direccion"]
      }
    }

    - hidden: la consulta puede ejecutarse, pero esas columnas se eliminan del resultado/exportación/correo.
    - forbidden: el perfil no puede usar ni devolver esas columnas.
    """
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, list[str]]] = {}

    for raw_table, raw_rules in value.items():
        table = str(raw_table or "").strip().lower()
        if not table or not isinstance(raw_rules, dict):
            continue

        hidden = {
            str(col).strip().lower()
            for col in (raw_rules.get("hidden") or [])
            if str(col).strip()
        }
        forbidden = {
            str(col).strip().lower()
            for col in (raw_rules.get("forbidden") or [])
            if str(col).strip()
        }

        # Si una columna se marca como prohibida, no la duplicamos como oculta.
        hidden -= forbidden

        if hidden or forbidden:
            normalized[table] = {
                "hidden": sorted(hidden),
                "forbidden": sorted(forbidden),
            }

    return normalized


class UserProfile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions_json: Mapped[str] = mapped_column(Text, default="{}")

    # Modo de acceso a vistas:
    # - all: puede consultar todas las vistas permitidas globalmente.
    # - custom: solo puede consultar exactamente las vistas listadas en allowed_tables.
    #   Si allowed_tables está vacío en custom, no puede consultar ninguna vista.
    table_access_mode: Mapped[str] = mapped_column(String(20), default="all")

    # CSV con vistas permitidas cuando table_access_mode = custom.
    allowed_tables: Mapped[str] = mapped_column(Text, default="")

    # JSON por vista. Se mantiene separado de allowed_tables para no romper la lógica actual.
    column_permissions_json: Mapped[str] = mapped_column(Text, default="{}")

    max_display_rows: Mapped[int] = mapped_column(Integer, default=5000)
    max_page_size: Mapped[int] = mapped_column(Integer, default=50)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(back_populates="profile_obj")

    @property
    def permissions(self) -> dict[str, bool]:
        try:
            raw = json.loads(self.permissions_json or "{}")
        except Exception:
            raw = {}

        merged = DEFAULT_PERMISSIONS.copy()
        for key, value in raw.items():
            if key in merged:
                merged[key] = bool(value)
        return merged

    @permissions.setter
    def permissions(self, value: dict[str, Any]) -> None:
        merged = DEFAULT_PERMISSIONS.copy()
        for key, enabled in (value or {}).items():
            if key in merged:
                merged[key] = bool(enabled)
        self.permissions_json = json.dumps(merged, ensure_ascii=False)

    @property
    def table_mode(self) -> str:
        return normalize_table_access_mode(self.table_access_mode)

    @table_mode.setter
    def table_mode(self, value: str) -> None:
        self.table_access_mode = normalize_table_access_mode(value)

    @property
    def allowed_tables_list(self) -> list[str]:
        return [x.strip().lower() for x in (self.allowed_tables or "").split(",") if x.strip()]

    @property
    def column_permissions(self) -> dict[str, dict[str, list[str]]]:
        try:
            raw = json.loads(self.column_permissions_json or "{}")
        except Exception:
            raw = {}
        return _normalize_column_permissions(raw)

    @column_permissions.setter
    def column_permissions(self, value: dict[str, Any]) -> None:
        self.column_permissions_json = json.dumps(
            _normalize_column_permissions(value),
            ensure_ascii=False,
            sort_keys=True,
        )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    # Desde la versión sin roles, el acceso se controla solo mediante profile_id.
    # Si tu SQLite antiguo aún tiene columna `role`, no se elimina; simplemente ya no se usa.
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    profile_obj: Mapped[UserProfile | None] = relationship(back_populates="users")

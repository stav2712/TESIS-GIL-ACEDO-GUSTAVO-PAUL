from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


DEFAULT_PERMISSIONS: dict[str, bool] = {
    "can_query": False,
    "can_export": False,
    "can_view_sql": False,
    "can_manage_users": False,
    "can_manage_profiles": False,
    "can_view_audit": False,
    "can_view_system_config": False,
}


class UserProfile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions_json: Mapped[str] = mapped_column(Text, default="{}")
    # CSV. Vacío = puede consultar todas las vistas permitidas globalmente.
    allowed_tables: Mapped[str] = mapped_column(Text, default="")
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
    def allowed_tables_list(self) -> list[str]:
        return [x.strip().lower() for x in (self.allowed_tables or "").split(",") if x.strip()]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
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

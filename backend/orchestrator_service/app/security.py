from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from jose import JWTError, jwt

from .config import settings


@dataclass(frozen=True)
class UserClaims:
    user_id: int
    username: str | None
    full_name: str | None
    profile: str | None
    profile_id: int | None
    permissions: dict[str, bool]
    allowed_tables: list[str]
    max_display_rows: int
    max_page_size: int

    def can(self, permission: str) -> bool:
        return bool(self.permissions.get(permission, False))


def require_claims(auth_header: str | None) -> UserClaims:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token Bearer")

    token = auth_header.split(" ", 1)[1]
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALG],
        )
    except JWTError:
        raise HTTPException(401, "Token inválido o expirado")

    if payload.get("is_active") is False:
        raise HTTPException(403, "Usuario inactivo")

    try:
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Token inválido: falta sub")

    if int(payload.get("acl_version") or 0) < 3:
        raise HTTPException(401, "Token desactualizado. Vuelve a iniciar sesión")

    permissions = payload.get("permissions") or {}
    allowed_tables = payload.get("allowed_tables") or []

    return UserClaims(
        user_id=user_id,
        username=payload.get("username"),
        full_name=payload.get("full_name"),
        profile=payload.get("profile"),
        profile_id=payload.get("profile_id"),
        permissions={str(k): bool(v) for k, v in permissions.items()},
        allowed_tables=[str(x).strip().lower() for x in allowed_tables if str(x).strip()],
        # Política global: el máximo visualizable no se lee del perfil ni del token.
        max_display_rows=settings.QUERY_DISPLAY_MAX_ROWS,
        max_page_size=min(int(payload.get("max_page_size") or 50), 50),
    )


def require_user_id(auth_header: str | None) -> int:
    return require_claims(auth_header).user_id


def require_permission(claims: UserClaims, permission: str) -> None:
    if not claims.can(permission):
        raise HTTPException(403, "No tienes permisos para esta operación")

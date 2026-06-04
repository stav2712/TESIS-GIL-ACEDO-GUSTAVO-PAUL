from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from jose import JWTError, jwt

from .config import settings

# v7: permisos separados para Plantillas e Historias Clinicas.
ACL_VERSION = 7


@dataclass(frozen=True)
class UserClaims:
    user_id: int
    username: str | None
    full_name: str | None
    email: str | None
    profile: str | None
    profile_id: int | None
    permissions: dict[str, bool]

    def can(self, permission: str) -> bool:
        return bool(self.permissions.get(permission, False))

    @property
    def is_adminish(self) -> bool:
        return self.profile == "admin" or self.can("can_manage_profiles") or self.can("can_view_audit")


def require_claims(auth_header: str | None) -> UserClaims:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token Bearer")

    token = auth_header.split(" ", 1)[1]
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Token inválido o expirado")

    if payload.get("is_active") is False:
        raise HTTPException(403, "Usuario inactivo")

    try:
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Token inválido: falta sub")

    if int(payload.get("acl_version") or 0) < ACL_VERSION:
        raise HTTPException(401, "Token desactualizado. Vuelve a iniciar sesión")

    permissions = payload.get("permissions") or {}
    email = str(payload.get("email") or "").strip().lower() or None

    return UserClaims(
        user_id=user_id,
        username=payload.get("username"),
        full_name=payload.get("full_name"),
        email=email,
        profile=payload.get("profile"),
        profile_id=payload.get("profile_id"),
        permissions={str(k): bool(v) for k, v in permissions.items()},
    )


def require_permission(claims: UserClaims, permission: str) -> None:
    if not claims.can(permission):
        raise HTTPException(403, "No tienes permisos para esta operación")

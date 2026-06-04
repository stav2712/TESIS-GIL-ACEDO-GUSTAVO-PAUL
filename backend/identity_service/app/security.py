from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from .models import DEFAULT_PERMISSIONS, User, UserProfile

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# v7: agrega permisos separados para Plantillas e Historias Clinicas.
ACL_VERSION = 7


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def profile_payload(profile: UserProfile | None) -> dict[str, Any]:
    if not profile:
        return {
            "profile": None,
            "profile_id": None,
            "permissions": DEFAULT_PERMISSIONS.copy(),
            "allowed_tables": [],
            "table_access_mode": "all",
            "column_permissions": {},
            "max_page_size": 50,
        }

    return {
        "profile": profile.name,
        "profile_id": profile.id,
        "permissions": profile.permissions,
        "allowed_tables": profile.allowed_tables_list,
        "table_access_mode": profile.table_mode,
        "column_permissions": profile.column_permissions,
        "max_page_size": min(profile.max_page_size or 50, 50),
    }


def create_jwt(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    profile_data = profile_payload(user.profile_obj)
    # El token ya no incluye `role`. El perfil es la unica fuente de permisos.
    # El maximo visualizable ya no viaja por perfil: es una politica global del orquestador.
    # acl_version=7 fuerza re-login para que viajen los permisos separados nuevos.
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "is_active": user.is_active,
        "acl_version": ACL_VERSION,
        "exp": exp,
        **profile_data,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_jwt(auth_header: str | None) -> dict[str, Any]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token Bearer")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Token inválido o expirado")

    if int(payload.get("acl_version") or 0) < ACL_VERSION:
        raise HTTPException(401, "Token desactualizado. Vuelve a iniciar sesión")

    return payload

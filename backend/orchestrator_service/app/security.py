from fastapi import HTTPException
from jose import jwt
from .config import settings

def require_user_id(auth_header: str | None) -> int:
    """
    Orquestador recibe JWT, valida y extrae ID de usuario. :contentReference[oaicite:8]{index=8}
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token Bearer")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        return int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Token inválido o expirado")
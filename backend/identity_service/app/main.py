from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import DEFAULT_PERMISSIONS, User, UserProfile, normalize_table_access_mode
from .security import create_jwt, decode_jwt, hash_password, verify_password

app = FastAPI(title="Identity Service")
logger = logging.getLogger("identity_service")

ADMIN_DEFAULT_EMAIL = "gilgustavo062@gmail.com"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]+$")
SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


def _validation_field_label(loc: tuple | list) -> str:
    name = str(loc[-1] if loc else "campo")
    return {
        "username": "usuario",
        "password": "contraseña",
        "full_name": "nombre completo",
        "email": "correo electrónico",
        "profile_id": "perfil",
        "name": "nombre",
        "description": "descripción",
        "max_page_size": "tamaño de página",
        "allowed_tables": "vistas permitidas",
        "column_permissions": "permisos por columna",
        "q": "búsqueda",
    }.get(name, name)


def _friendly_validation_message(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "Revisa los campos ingresados. Hay datos obligatorios o con formato inválido."

    first = errors[0]
    field = _validation_field_label(first.get("loc") or [])
    kind = str(first.get("type") or "")
    ctx = first.get("ctx") or {}

    if kind == "missing":
        return f"El campo {field} es obligatorio."
    if "string_too_short" in kind:
        min_len = ctx.get("min_length")
        if field == "contraseña":
            return "La contraseña debe tener al menos 6 caracteres."
        if min_len:
            return f"El campo {field} debe tener al menos {min_len} caracteres."
        return f"El campo {field} es demasiado corto."
    if "string_too_long" in kind:
        max_len = ctx.get("max_length")
        return f"El campo {field} supera el tamaño máximo permitido" + (f" de {max_len} caracteres." if max_len else ".")
    if "greater_than_equal" in kind or "less_than_equal" in kind or "int_parsing" in kind or "float_parsing" in kind:
        return f"El campo {field} debe tener un valor numérico válido dentro del rango permitido."
    if "bool" in kind:
        return f"El campo {field} debe tener un valor válido."

    return "Revisa los campos ingresados. Hay datos obligatorios o con formato inválido."


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error in %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": _friendly_validation_message(exc.errors()),
            "error_code": "VALIDATION_ERROR",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "No se pudo completar la operación. Inténtalo nuevamente o contacta al administrador.",
            "error_code": "INTERNAL_ERROR",
        },
    )


# ---------- DTOs ----------
class AuthIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ColumnPermissionRule(BaseModel):
    hidden: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class ProfileOut(BaseModel):
    id: int
    name: str
    description: str = ""
    permissions: dict[str, bool]
    allowed_tables: list[str] = Field(default_factory=list)
    table_access_mode: str = "all"
    column_permissions: dict[str, ColumnPermissionRule] = Field(default_factory=dict)
    max_display_rows: int
    max_page_size: int
    is_system: bool = False


class ProfileCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = Field(default="", max_length=255)
    permissions: dict[str, bool] = Field(default_factory=dict)
    allowed_tables: list[str] = Field(default_factory=list)
    table_access_mode: str | None = None
    column_permissions: dict[str, ColumnPermissionRule] = Field(default_factory=dict)
    max_page_size: int = Field(default=50, ge=1, le=50)


class ProfileUpdateIn(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    permissions: dict[str, bool] | None = None
    allowed_tables: list[str] | None = None
    table_access_mode: str | None = None
    column_permissions: dict[str, ColumnPermissionRule] | None = None
    max_page_size: int | None = Field(default=None, ge=1, le=50)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    profile: str | None = None
    profile_id: int | None = None
    is_active: bool
    created_at: str | None = None


class CreateUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    # El acceso ya no usa roles. Para volver administrador a alguien,
    # asígnale el perfil "admin" o un perfil con permisos equivalentes.
    profile_id: int | None = Field(default=None, ge=1)


class UpdateUserIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    profile_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


# ---------- Validaciones ----------
def _reject_control_chars(value: str, field: str) -> None:
    if CONTROL_CHARS_RE.search(value):
        raise HTTPException(400, f"{field} contiene caracteres no permitidos")


def _normalize_email(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    _reject_control_chars(cleaned, "Correo electrónico")
    if len(cleaned) > 254 or not EMAIL_RE.match(cleaned):
        raise HTTPException(400, "Correo electrónico inválido")
    return cleaned


def _normalize_username(value: str, *, current: str | None = None) -> str:
    cleaned = (value or "").strip()
    _reject_control_chars(cleaned, "Usuario")
    if not (3 <= len(cleaned) <= 50):
        raise HTTPException(400, "El usuario debe tener entre 3 y 50 caracteres")
    if not USERNAME_RE.match(cleaned):
        raise HTTPException(400, "El usuario solo puede contener letras, números, punto, guion y guion bajo")
    if current is not None and cleaned == current:
        return current
    return cleaned


def _normalize_profile_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    _reject_control_chars(cleaned, "Nombre del perfil")
    if not (2 <= len(cleaned) <= 40):
        raise HTTPException(400, "El perfil debe tener entre 2 y 40 caracteres")
    if not PROFILE_NAME_RE.match(cleaned):
        raise HTTPException(400, "El perfil contiene caracteres no permitidos")
    return cleaned


def _normalize_password(value: str) -> str:
    raw = value or ""
    _reject_control_chars(raw, "Contraseña")
    if not raw.strip() or len(raw) < 6:
        raise HTTPException(400, "La contraseña debe tener al menos 6 caracteres")
    if len(raw) > 128:
        raise HTTPException(400, "La contraseña supera el tamaño máximo de 128 caracteres")
    return raw


def _normalize_text(value: str | None, *, max_len: int, field: str, empty_as_none: bool) -> str | None:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if not cleaned:
        return None if empty_as_none else ""
    _reject_control_chars(cleaned, field)
    if len(cleaned) > max_len:
        raise HTTPException(400, f"{field} supera el tamaño máximo de {max_len} caracteres")
    return cleaned


def _normalize_table_name(value: str) -> str:
    table = (value or "").strip().lower()
    if not table:
        raise HTTPException(400, "La vista permitida no puede estar vacía")
    if len(table) > 120 or not TABLE_NAME_RE.match(table):
        raise HTTPException(400, f"Vista inválida: {value}")
    return table


def _normalize_column_name(value: str) -> str:
    column = (value or "").strip().lower()
    if not column:
        raise HTTPException(400, "La columna no puede estar vacía")
    if len(column) > 120 or not SQL_IDENTIFIER_RE.match(column):
        raise HTTPException(400, f"Columna inválida: {value}")
    return column


def _normalize_allowed_tables(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values or []:
        table = _normalize_table_name(str(raw))
        if table not in seen:
            seen.add(table)
            result.append(table)
    return result


def _column_rules_payload(rules: dict[str, ColumnPermissionRule] | None) -> dict[str, dict[str, list[str]]]:
    if not rules:
        return {}

    normalized: dict[str, dict[str, list[str]]] = {}
    for raw_table, rule in rules.items():
        table = _normalize_table_name(str(raw_table))
        forbidden = {_normalize_column_name(col) for col in (rule.forbidden or [])}
        hidden = {_normalize_column_name(col) for col in (rule.hidden or [])}
        hidden -= forbidden
        if hidden or forbidden:
            normalized[table] = {
                "hidden": sorted(hidden),
                "forbidden": sorted(forbidden),
            }
    return normalized


def _user_exists_case_insensitive(db: Session, username: str, exclude_id: int | None = None) -> bool:
    query = db.query(User).filter(func.lower(User.username) == username.lower())
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return db.query(query.exists()).scalar()


def _profile_exists_case_insensitive(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(UserProfile).filter(func.lower(UserProfile.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(UserProfile.id != exclude_id)
    return db.query(query.exists()).scalar()


ADMIN_SAFETY_PERMISSIONS = ("can_manage_users", "can_manage_profiles")


def _merged_permissions(value: dict[str, Any] | None) -> dict[str, bool]:
    merged = DEFAULT_PERMISSIONS.copy()
    for key, enabled in (value or {}).items():
        if key in merged:
            merged[key] = bool(enabled)
    return merged


def _permissions_keep_admin_access(permissions: dict[str, bool] | None) -> bool:
    permissions = permissions or {}
    return all(bool(permissions.get(key, False)) for key in ADMIN_SAFETY_PERMISSIONS)


def _profile_keeps_admin_access(profile: UserProfile | None) -> bool:
    return bool(profile and _permissions_keep_admin_access(profile.permissions))


def _assert_self_keeps_admin_access(actor: User, target_user: User, next_profile: UserProfile | None) -> None:
    if actor.id != target_user.id:
        return
    if not _profile_keeps_admin_access(next_profile):
        raise HTTPException(
            400,
            "No puedes quitarte tus propios permisos administrativos. "
            "Pide a otro administrador que cambie tu perfil si realmente lo necesitas.",
        )


def _assert_profile_change_safe_for_actor(actor: User, profile: UserProfile, next_permissions: dict[str, bool]) -> None:
    if actor.profile_id == profile.id and not _permissions_keep_admin_access(next_permissions):
        raise HTTPException(
            400,
            "No puedes modificar tu propio perfil para quitar permisos administrativos.",
        )
    if profile.name.strip().lower() == "admin" and not _permissions_keep_admin_access(next_permissions):
        raise HTTPException(
            400,
            "El perfil administrador principal debe conservar permisos de administración.",
        )


# ---------- Migración simple SQLite ----------
def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _legacy_roles_by_user_id() -> dict[int, str]:
    """Lee la columna legacy `role` si existe, sin depender del modelo ORM."""
    with engine.begin() as conn:
        user_cols = _table_columns(conn, "users")
        if "role" not in user_cols:
            return {}
        rows = conn.execute(text("SELECT id, role FROM users")).fetchall()
        return {int(row[0]): str(row[1] or "") for row in rows}


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        user_cols = _table_columns(conn, "users")
        user_alter_columns = {
            "full_name": "ALTER TABLE users ADD COLUMN full_name VARCHAR(120)",
            "email": "ALTER TABLE users ADD COLUMN email VARCHAR(254)",
            "profile_id": "ALTER TABLE users ADD COLUMN profile_id INTEGER",
            "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "updated_at": "ALTER TABLE users ADD COLUMN updated_at DATETIME",
        }
        for col, sql in user_alter_columns.items():
            if col not in user_cols:
                conn.execute(text(sql))

        # Admin por defecto: solo se llena si está vacío para no pisar cambios manuales futuros.
        conn.execute(
            text(
                "UPDATE users SET email = :email "
                "WHERE username = 'admin' AND TRIM(COALESCE(email, '')) = ''"
            ),
            {"email": ADMIN_DEFAULT_EMAIL},
        )

        profile_cols = _table_columns(conn, "profiles")
        if "table_access_mode" not in profile_cols:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN table_access_mode VARCHAR(20) DEFAULT 'all'"))
            conn.execute(
                text(
                    "UPDATE profiles "
                    "SET table_access_mode = CASE "
                    "WHEN TRIM(COALESCE(allowed_tables, '')) = '' THEN 'all' "
                    "ELSE 'custom' END"
                )
            )
        else:
            conn.execute(
                text(
                    "UPDATE profiles SET table_access_mode = 'all' "
                    "WHERE table_access_mode IS NULL OR LOWER(table_access_mode) NOT IN ('all', 'custom')"
                )
            )

        if "column_permissions_json" not in profile_cols:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN column_permissions_json TEXT DEFAULT '{}'"))


def _seed_profiles(db: Session) -> None:
    defaults = [
        {
            "name": "admin",
            "description": "Administrador total de la plataforma.",
            "permissions": {k: True for k in DEFAULT_PERMISSIONS},
            "allowed_tables": "",
            "table_access_mode": "all",
            "column_permissions": {},
            "max_display_rows": 5000,
            "max_page_size": 50,
        },
        {
            "name": "analista",
            "description": "Puede consultar, exportar y ver SQL generado.",
            "permissions": {
                "can_query": True,
                "can_export": True,
                "can_view_sql": True,
                "can_manage_users": False,
                "can_manage_profiles": False,
                "can_view_audit": False,
                "can_view_system_config": True,
            },
            "allowed_tables": "",
            "table_access_mode": "all",
            "column_permissions": {},
            "max_display_rows": 5000,
            "max_page_size": 50,
        },
        {
            "name": "consulta",
            "description": "Usuario final: consulta resultados, sin SQL ni exportación.",
            "permissions": {
                "can_query": True,
                "can_export": False,
                "can_view_sql": False,
                "can_manage_users": False,
                "can_manage_profiles": False,
                "can_view_audit": False,
                "can_view_system_config": False,
            },
            "allowed_tables": "",
            "table_access_mode": "all",
            "column_permissions": {},
            "max_display_rows": 5000,
            "max_page_size": 50,
        },
        {
            "name": "auditor",
            "description": "Puede revisar auditoría de preguntas y actividad.",
            "permissions": {
                "can_query": False,
                "can_export": True,
                "can_view_sql": True,
                "can_manage_users": False,
                "can_manage_profiles": False,
                "can_view_audit": True,
                "can_view_system_config": True,
            },
            "allowed_tables": "",
            "table_access_mode": "all",
            "column_permissions": {},
            "max_display_rows": 5000,
            "max_page_size": 50,
        },
    ]

    by_name = {p.name: p for p in db.query(UserProfile).all()}
    for item in defaults:
        profile = by_name.get(item["name"])
        if not profile:
            profile = UserProfile(
                name=item["name"],
                description=item["description"],
                is_system=True,
                table_access_mode=item["table_access_mode"],
                allowed_tables=item["allowed_tables"],
                max_display_rows=item["max_display_rows"],
                max_page_size=item["max_page_size"],
            )
            profile.permissions = item["permissions"]
            profile.column_permissions = item["column_permissions"]
            db.add(profile)

    db.commit()

    admin_profile = db.query(UserProfile).filter(UserProfile.name == "admin").first()
    consulta_profile = db.query(UserProfile).filter(UserProfile.name == "consulta").first()
    legacy_roles = _legacy_roles_by_user_id()

    for user in db.query(User).filter(User.profile_id.is_(None)).all():
        legacy_role = legacy_roles.get(user.id, "")
        # Compatibilidad: si vienes de una BD vieja, el usuario con role=admin
        # conserva acceso completo mediante el perfil admin. En adelante ya no
        # se guarda ni se muestra role.
        if legacy_role == "admin" or user.username == "admin":
            user.profile_id = admin_profile.id if admin_profile else None
        else:
            user.profile_id = consulta_profile.id if consulta_profile else None

    admin = db.query(User).filter(User.username == "admin").first()
    if admin and not (admin.email or "").strip():
        admin.email = ADMIN_DEFAULT_EMAIL

    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    _ensure_schema()
    db = next(get_db())
    try:
        _seed_profiles(db)
    finally:
        db.close()


# ---------- Helpers ----------
def _column_rules_to_out(profile: UserProfile) -> dict[str, ColumnPermissionRule]:
    return {
        table: ColumnPermissionRule(**rules)
        for table, rules in profile.column_permissions.items()
    }


def profile_to_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description or "",
        permissions=profile.permissions,
        allowed_tables=profile.allowed_tables_list,
        table_access_mode=profile.table_mode,
        column_permissions=_column_rules_to_out(profile),
        max_display_rows=settings.QUERY_DISPLAY_MAX_ROWS,
        max_page_size=min(profile.max_page_size or 50, 50),
        is_system=profile.is_system,
    )


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        profile=user.profile_obj.name if user.profile_obj else None,
        profile_id=user.profile_id,
        is_active=bool(user.is_active),
        created_at=_iso(user.created_at),
    )


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_jwt(authorization)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(403, "Usuario inactivo o no existe")
    return user


def require_permission(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        perms = user.profile_obj.permissions if user.profile_obj else DEFAULT_PERMISSIONS
        if not perms.get(permission, False):
            raise HTTPException(403, "No tienes permisos para esta operación")
        return user

    return dep


# ---------- Endpoints ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth", response_model=TokenOut)
def auth(payload: AuthIn, db: Session = Depends(get_db)):
    username = (payload.username or "").strip()
    u = db.query(User).filter(User.username == username).first()
    if not u or not u.is_active or not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    return TokenOut(access_token=create_jwt(u))


@app.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_to_out(user)


@app.get("/profiles", response_model=list[ProfileOut])
def list_profiles(
    _: User = Depends(require_permission("can_manage_profiles")),
    db: Session = Depends(get_db),
):
    return [profile_to_out(p) for p in db.query(UserProfile).order_by(UserProfile.name).all()]


@app.post("/profiles", response_model=ProfileOut)
def create_profile(
    payload: ProfileCreateIn,
    _: User = Depends(require_permission("can_manage_profiles")),
    db: Session = Depends(get_db),
):
    name = _normalize_profile_name(payload.name)
    if _profile_exists_case_insensitive(db, name):
        raise HTTPException(400, "El perfil ya existe")

    allowed_tables = _normalize_allowed_tables(payload.allowed_tables)
    table_access_mode = normalize_table_access_mode(
        payload.table_access_mode if payload.table_access_mode is not None else ("custom" if allowed_tables else "all")
    )

    profile = UserProfile(
        name=name,
        description=_normalize_text(payload.description, max_len=255, field="Descripción", empty_as_none=False) or "",
        table_access_mode=table_access_mode,
        allowed_tables=",".join(allowed_tables),
        max_display_rows=settings.QUERY_DISPLAY_MAX_ROWS,
        max_page_size=min(payload.max_page_size, 50),
        is_system=False,
    )
    profile.permissions = _merged_permissions(payload.permissions)
    profile.column_permissions = _column_rules_payload(payload.column_permissions)

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)


@app.patch("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    payload: ProfileUpdateIn,
    actor: User = Depends(require_permission("can_manage_profiles")),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(404, "Perfil no encontrado")

    if payload.description is not None:
        profile.description = _normalize_text(payload.description, max_len=255, field="Descripción", empty_as_none=False) or ""
    if payload.permissions is not None:
        next_permissions = _merged_permissions(payload.permissions)
        _assert_profile_change_safe_for_actor(actor, profile, next_permissions)
        profile.permissions = next_permissions

    allowed_tables: list[str] | None = None
    if payload.allowed_tables is not None:
        allowed_tables = _normalize_allowed_tables(payload.allowed_tables)

    if payload.table_access_mode is not None:
        profile.table_mode = payload.table_access_mode
    elif allowed_tables is not None:
        # Compatibilidad con clientes anteriores: lista vacía = sin restricción;
        # lista con valores = restricción explícita.
        profile.table_mode = "custom" if allowed_tables else "all"

    if allowed_tables is not None:
        profile.allowed_tables = ",".join(allowed_tables)
    if payload.column_permissions is not None:
        profile.column_permissions = _column_rules_payload(payload.column_permissions)
    if payload.max_page_size is not None:
        profile.max_page_size = min(payload.max_page_size, 50)

    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)


@app.get("/users", response_model=list[UserOut])
def list_users(
    q: str | None = Query(default=None, max_length=80),
    _: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if q:
        cleaned_q = q.strip()
        if cleaned_q:
            like = f"%{cleaned_q}%"
            query = query.filter((User.username.like(like)) | (User.full_name.like(like)) | (User.email.like(like)))
    return [user_to_out(u) for u in query.order_by(User.id).all()]


@app.post("/users", response_model=UserOut)
def create_user(
    payload: CreateUserIn,
    _: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    username = _normalize_username(payload.username)
    if _user_exists_case_insensitive(db, username):
        raise HTTPException(400, "Usuario ya existe")

    profile_id = payload.profile_id
    if profile_id is None:
        default_profile = db.query(UserProfile).filter(UserProfile.name == "consulta").first()
        profile_id = default_profile.id if default_profile else None
    elif not db.query(UserProfile).filter(UserProfile.id == profile_id).first():
        raise HTTPException(400, "Perfil inválido")

    u = User(
        username=username,
        full_name=_normalize_text(payload.full_name, max_len=120, field="Nombre completo", empty_as_none=True),
        email=_normalize_email(payload.email),
        password_hash=hash_password(_normalize_password(payload.password)),
        profile_id=profile_id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return user_to_out(u)


@app.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UpdateUserIn,
    actor: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")

    if payload.username is not None:
        username = _normalize_username(payload.username, current=u.username)
        if username != u.username:
            if _user_exists_case_insensitive(db, username, exclude_id=u.id):
                raise HTTPException(400, "Usuario ya existe")
            u.username = username

    if payload.password is not None and payload.password.strip():
        u.password_hash = hash_password(_normalize_password(payload.password))
    if payload.full_name is not None:
        u.full_name = _normalize_text(payload.full_name, max_len=120, field="Nombre completo", empty_as_none=True)
    if "email" in payload.model_fields_set:
        u.email = _normalize_email(payload.email)
    next_profile = u.profile_obj
    if payload.profile_id is not None:
        next_profile = db.query(UserProfile).filter(UserProfile.id == payload.profile_id).first()
        if not next_profile:
            raise HTTPException(400, "Perfil inválido")
        _assert_self_keeps_admin_access(actor, u, next_profile)
        u.profile_id = payload.profile_id
    if payload.is_active is not None:
        if actor.id == u.id and payload.is_active is False:
            raise HTTPException(400, "No puedes desactivar tu propio usuario activo")
        u.is_active = payload.is_active

    db.commit()
    db.refresh(u)
    return user_to_out(u)

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .config import settings
from .models import DEFAULT_PERMISSIONS, User, UserProfile
from .security import create_jwt, decode_jwt, hash_password, verify_password

app = FastAPI(title="Identity Service")


# ---------- DTOs ----------
class AuthIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    id: int
    name: str
    description: str = ""
    permissions: dict[str, bool]
    allowed_tables: list[str] = []
    max_display_rows: int
    max_page_size: int
    is_system: bool = False


class ProfileCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = ""
    permissions: dict[str, bool] = Field(default_factory=dict)
    allowed_tables: list[str] = Field(default_factory=list)
    max_page_size: int = Field(default=50, ge=1, le=50)


class ProfileUpdateIn(BaseModel):
    description: str | None = None
    permissions: dict[str, bool] | None = None
    allowed_tables: list[str] | None = None
    max_page_size: int | None = Field(default=None, ge=1, le=50)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    profile: str | None = None
    profile_id: int | None = None
    is_active: bool
    created_at: str | None = None


class CreateUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    full_name: str | None = Field(default=None, max_length=120)
    # El acceso ya no usa roles. Para volver administrador a alguien,
    # asígnale el perfil "admin" o un perfil con permisos equivalentes.
    profile_id: int | None = None


class UpdateUserIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=6)
    full_name: str | None = Field(default=None, max_length=120)
    profile_id: int | None = None
    is_active: bool | None = None


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
        alter_columns = {
            "full_name": "ALTER TABLE users ADD COLUMN full_name VARCHAR(120)",
            "profile_id": "ALTER TABLE users ADD COLUMN profile_id INTEGER",
            "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "updated_at": "ALTER TABLE users ADD COLUMN updated_at DATETIME",
        }
        for col, sql in alter_columns.items():
            if col not in user_cols:
                conn.execute(text(sql))


def _seed_profiles(db: Session) -> None:
    defaults = [
        {
            "name": "admin",
            "description": "Administrador total de la plataforma.",
            "permissions": {k: True for k in DEFAULT_PERMISSIONS},
            "allowed_tables": "",
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
                allowed_tables=item["allowed_tables"],
                max_display_rows=item["max_display_rows"],
                max_page_size=item["max_page_size"],
            )
            profile.permissions = item["permissions"]
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
def profile_to_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description or "",
        permissions=profile.permissions,
        allowed_tables=profile.allowed_tables_list,
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
    u = db.query(User).filter(User.username == payload.username).first()
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
    if db.query(UserProfile).filter(UserProfile.name == payload.name).first():
        raise HTTPException(400, "El perfil ya existe")

    profile = UserProfile(
        name=payload.name.strip(),
        description=payload.description.strip(),
        allowed_tables=",".join(payload.allowed_tables),
        max_display_rows=settings.QUERY_DISPLAY_MAX_ROWS,
        max_page_size=min(payload.max_page_size, 50),
        is_system=False,
    )
    profile.permissions = payload.permissions
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)


@app.patch("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    payload: ProfileUpdateIn,
    _: User = Depends(require_permission("can_manage_profiles")),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(404, "Perfil no encontrado")

    if payload.description is not None:
        profile.description = payload.description
    if payload.permissions is not None:
        profile.permissions = payload.permissions
    if payload.allowed_tables is not None:
        profile.allowed_tables = ",".join(payload.allowed_tables)
    if payload.max_page_size is not None:
        profile.max_page_size = min(payload.max_page_size, 50)

    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)


@app.get("/users", response_model=list[UserOut])
def list_users(
    q: str | None = Query(default=None),
    _: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(User.username.like(like))
    return [user_to_out(u) for u in query.order_by(User.id).all()]


@app.post("/users", response_model=UserOut)
def create_user(
    payload: CreateUserIn,
    _: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Usuario ya existe")

    profile_id = payload.profile_id
    if profile_id is None:
        default_profile = db.query(UserProfile).filter(UserProfile.name == "consulta").first()
        profile_id = default_profile.id if default_profile else None
    elif not db.query(UserProfile).filter(UserProfile.id == profile_id).first():
        raise HTTPException(400, "Perfil inválido")

    u = User(
        username=payload.username.strip(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
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
    _: User = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")

    if payload.username is not None and payload.username != u.username:
        if db.query(User).filter(User.username == payload.username).first():
            raise HTTPException(400, "Usuario ya existe")
        u.username = payload.username.strip()

    if payload.password:
        u.password_hash = hash_password(payload.password)
    if payload.full_name is not None:
        u.full_name = payload.full_name
    if payload.profile_id is not None:
        if not db.query(UserProfile).filter(UserProfile.id == payload.profile_id).first():
            raise HTTPException(400, "Perfil inválido")
        u.profile_id = payload.profile_id
    if payload.is_active is not None:
        u.is_active = payload.is_active

    db.commit()
    db.refresh(u)
    return user_to_out(u)

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import TemplateCreateIn, TemplateListOut, TemplateOut, TemplateUpdateIn, TemplateUseOut
from .repo import PlatformRepo
from .security import require_claims, require_permission

app = FastAPI(title="Platform Service")

origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = PlatformRepo()

TEMPLATE_PERMISSION = "can_use_templates"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/templates", response_model=TemplateListOut)
def list_templates(
    q: str | None = Query(default=None, max_length=120),
    tag: str | None = Query(default=None, max_length=30),
    mine: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    return repo.list_templates(claims, q=q, tag=tag, mine=mine)


@app.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreateIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    return repo.create_template(claims, payload.model_dump())


@app.get("/templates/{template_id}", response_model=TemplateOut)
def get_template(template_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    doc = repo.get_template(template_id, claims)
    if not doc:
        raise HTTPException(404, "Plantilla no encontrada")
    return doc


@app.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: str, payload: TemplateUpdateIn, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    changes = payload.model_dump(exclude_unset=True)
    doc = repo.update_template(template_id, claims, changes)
    if not doc:
        raise HTTPException(404, "No se pudo actualizar la plantilla")
    return doc


@app.delete("/templates/{template_id}")
def delete_template(template_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    ok = repo.delete_template(template_id, claims)
    if not ok:
        raise HTTPException(404, "No se pudo eliminar la plantilla")
    return {"ok": True}


@app.post("/templates/{template_id}/use", response_model=TemplateUseOut)
def record_template_use(template_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    doc = repo.record_use(template_id, claims)
    if not doc:
        raise HTTPException(404, "Plantilla no encontrada")
    return doc


@app.post("/templates/{template_id}/fork", response_model=TemplateOut)
def fork_template(template_id: str, authorization: str | None = Header(default=None)):
    claims = require_claims(authorization)
    require_permission(claims, TEMPLATE_PERMISSION)
    doc = repo.fork_template(template_id, claims)
    if not doc:
        raise HTTPException(404, "No se pudo copiar la plantilla")
    return doc

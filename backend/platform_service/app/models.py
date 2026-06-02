from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
UUIDISH_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
TAG_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{1,30}$")

Visibility = Literal["private", "shared"]
TemplateStatus = Literal["draft", "published"]


def _clean_text(value: str | None, *, max_len: int, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} es obligatorio")
        return None
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        if required:
            raise ValueError(f"{field} es obligatorio")
        return None
    if CONTROL_CHARS_RE.search(cleaned):
        raise ValueError(f"{field} contiene caracteres no permitidos")
    if len(cleaned) > max_len:
        raise ValueError(f"{field} supera {max_len} caracteres")
    return cleaned


def _validate_id(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or CONTROL_CHARS_RE.search(cleaned) or not UUIDISH_RE.match(cleaned):
        raise ValueError(f"{field} inválido")
    return cleaned


def _normalize_tags(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values or []:
        tag = re.sub(r"\s+", " ", str(raw or "").strip()).lower()
        if not tag:
            continue
        if CONTROL_CHARS_RE.search(tag) or not TAG_RE.match(tag):
            raise ValueError(f"Etiqueta inválida: {raw}")
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
        if len(result) >= 10:
            break
    return result


class TemplateCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=90)
    description: str | None = Field(default=None, max_length=300)
    nl: str = Field(min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    visibility: Visibility = "private"
    status: TemplateStatus = "published"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _clean_text(value, max_len=90, field="Título", required=True) or ""

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_text(value, max_len=300, field="Descripción")

    @field_validator("nl")
    @classmethod
    def normalize_nl(cls, value: str) -> str:
        return _clean_text(value, max_len=2000, field="Consulta", required=True) or ""

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


class TemplateUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=90)
    description: str | None = Field(default=None, max_length=300)
    nl: str | None = Field(default=None, min_length=1, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=10)
    visibility: Visibility | None = None
    status: TemplateStatus | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return _clean_text(value, max_len=90, field="Título", required=value is not None)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _clean_text(value, max_len=300, field="Descripción")

    @field_validator("nl")
    @classmethod
    def normalize_nl(cls, value: str | None) -> str | None:
        return _clean_text(value, max_len=2000, field="Consulta", required=value is not None)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalize_tags(value)


class TemplateUseIn(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=120)

    @field_validator("conversation_id")
    @classmethod
    def normalize_conversation_id(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _validate_id(value, "conversation_id")


class TemplateOut(BaseModel):
    template_id: str
    title: str
    description: str | None = None
    nl: str
    tags: list[str] = Field(default_factory=list)
    visibility: Visibility
    status: TemplateStatus
    owner_user_id: int
    owner_username: str | None = None
    owner_full_name: str | None = None
    owner_profile: str | None = None
    use_count: int = 0
    fork_count: int = 0
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    can_edit: bool = False
    can_delete: bool = False


class TemplateListOut(BaseModel):
    rows: list[TemplateOut]
    total_count: int


class TemplateUseOut(BaseModel):
    ok: bool
    use_count: int
    last_used_at: str

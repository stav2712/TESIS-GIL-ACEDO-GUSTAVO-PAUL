from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
UUIDISH_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _clean_optional_text(value: str | None, *, max_len: int, field: str) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return None
    if CONTROL_CHARS_RE.search(cleaned):
        raise ValueError(f"{field} contiene caracteres no permitidos")
    if len(cleaned) > max_len:
        raise ValueError(f"{field} supera {max_len} caracteres")
    return cleaned


def _validate_public_id(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} es obligatorio")
    if CONTROL_CHARS_RE.search(cleaned) or not UUIDISH_RE.match(cleaned):
        raise ValueError(f"{field} inválido")
    return cleaned


class ResolvedTermOut(BaseModel):
    surface: str
    canonical: str
    category: str | None = None
    codes: list[str] = Field(default_factory=list)
    matched_alias: str | None = None


class ResolvedValueOut(BaseModel):
    field: str
    canonical: str
    matched_alias: str | None = None


class QueryIn(BaseModel):
    nl: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=120)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=200)

    @field_validator("nl")
    @classmethod
    def normalize_nl(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La pregunta no puede estar vacía")
        if CONTROL_CHARS_RE.search(cleaned):
            raise ValueError("La pregunta contiene caracteres no permitidos")

        # Aquí solo hacemos limpieza estructural.
        # La validación semántica del dominio vive en el orquestador/nl_guard
        # para poder devolver errores 400 amigables, no errores 422 genéricos
        # de Pydantic en el frontend.
        return cleaned

    @field_validator("conversation_id")
    @classmethod
    def normalize_conversation_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return _validate_public_id(cleaned, "conversation_id")


class QueryOut(BaseModel):
    conversation_id: str
    report_id: str
    sql: str
    timestamp: str
    latency_ms: int
    columns: list[str]
    rows: list[dict]
    page: int
    page_size: int
    row_count: int
    total_count: int | None = None
    display_total_count: int | None = None
    total_pages: int | None = None
    max_result_window: int | None = None
    max_result_window_exceeded: bool = False
    result_message: str | None = None
    suppressed_columns: list[str] = Field(default_factory=list)
    selected_report_id: str | None = None
    nl_normalized: str | None = None
    schema_profile: str | None = None
    resolved_terms: list[ResolvedTermOut] = Field(default_factory=list)
    resolved_values: list[ResolvedValueOut] = Field(default_factory=list)
    translator_strategy: str | None = None
    can_view_sql: bool = True


class QueryJobStartOut(BaseModel):
    job_id: str
    conversation_id: str
    status: str


class QueryJobOut(BaseModel):
    job_id: str
    conversation_id: str
    nl: str
    page: int = 1
    page_size: int = 50
    status: str
    report_id: str | None = None
    error: str | None = None
    result: QueryOut | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None


class FeedbackIn(BaseModel):
    value: Literal["up", "down"]


class ReportEmailIn(BaseModel):
    formats: list[str] = Field(default_factory=list, min_length=1, max_length=3)

    @field_validator("formats")
    @classmethod
    def normalize_formats(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            fmt = str(item or "").strip().lower()
            if not fmt:
                continue
            if CONTROL_CHARS_RE.search(fmt):
                raise ValueError("Formato inválido")
            cleaned.append(fmt)
        if not cleaned:
            raise ValueError("Selecciona al menos un formato")
        return cleaned


class ReportEmailOut(BaseModel):
    ok: bool
    to: str
    formats: list[str]
    attachments: list[str]


class ConversationCreateIn(BaseModel):
    title: str | None = Field(default=None, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, max_len=80, field="Título")


class ConversationRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = _clean_optional_text(value, max_len=80, field="Título")
        if not cleaned:
            raise ValueError("El título es obligatorio")
        return cleaned


class ConversationSelectIn(BaseModel):
    report_id: str = Field(min_length=1, max_length=120)

    @field_validator("report_id")
    @classmethod
    def normalize_report_id(cls, value: str) -> str:
        return _validate_public_id(value, "report_id")


class ConversationOut(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    deleted: bool = False
    selected_report_id: str | None = None
    last_preview: str | None = None


class ReportMetaOut(BaseModel):
    report_id: str
    conversation_id: str
    nl: str
    sql: str
    timestamp: str
    latency_ms: int
    feedback: str | None = None
    user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    profile: str | None = None
    nl_normalized: str | None = None
    schema_profile: str | None = None
    resolved_terms: list[ResolvedTermOut] = Field(default_factory=list)
    resolved_values: list[ResolvedValueOut] = Field(default_factory=list)
    translator_strategy: str | None = None


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    reports: list[ReportMetaOut]


class AuditReportOut(BaseModel):
    report_id: str
    conversation_id: str
    user_id: int
    username: str | None = None
    full_name: str | None = None
    profile: str | None = None
    nl: str
    sql: str
    timestamp: str
    latency_ms: int
    feedback: str | None = None


class AuditListOut(BaseModel):
    rows: list[AuditReportOut]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class SystemConfigUpdateIn(BaseModel):
    # Todos son opcionales para permitir guardar cambios parciales.
    # La validación fina vive en runtime_config.py para mantener una sola fuente de reglas.
    query_display_max_rows: int | None = Field(default=None, ge=50, le=100_000)
    export_max_rows: int | None = Field(default=None, ge=0, le=250_000)
    query_timeout_seconds: float | None = Field(default=None, ge=30.0, le=900.0)

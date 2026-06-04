from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Path, Query

from .policies import apply_column_permissions_to_result, ensure_sql_allowed_by_profile
from .runtime_config import get_runtime_config
from .security import require_claims, require_permission
from .sql_client import execute_sql

router = APIRouter(prefix="/clinical-history", tags=["clinical-history"])

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
CLINICAL_HISTORY_PERMISSION = "can_view_clinical_history"
PATIENTS_TABLE = "reporting.vw_paciente_360"
EVENTS_TABLE = "reporting.vw_eventos_clinicos"

PATIENT_LIST_COLUMNS = [
    "id_paciente",
    "id_paciente_fuente",
    "nombre_completo",
    "genero_estandar",
    "fecha_nacimiento",
    "edad_actual",
    "fallecido",
    "fecha_fallecimiento",
    "ciudad",
    "estado",
    "total_encuentros",
    "fecha_ultimo_encuentro",
    "total_diagnosticos",
    "total_procedimientos",
    "total_medicamentos",
    "total_mediciones",
    "total_observaciones",
    "total_alergias",
]

PATIENT_DETAIL_COLUMNS = [
    "id_paciente",
    "id_paciente_fuente",
    "nombre_completo",
    "primer_nombre",
    "segundo_nombre",
    "apellido",
    "genero_estandar",
    "raza_estandar",
    "etnia_estandar",
    "estado_civil",
    "fecha_nacimiento",
    "edad_actual",
    "fallecido",
    "fecha_fallecimiento",
    "direccion",
    "ciudad",
    "estado",
    "condado",
    "zip",
    "pais_estandar",
    "gastos_salud_acumulados",
    "cobertura_salud_acumulada",
    "ingreso_anual",
    "total_encuentros",
    "fecha_primer_encuentro",
    "fecha_ultimo_encuentro",
    "total_diagnosticos",
    "total_procedimientos",
    "total_medicamentos",
    "total_mediciones",
    "total_observaciones",
    "total_dispositivos",
    "total_alergias",
    "total_planes_cuidado",
    "total_inmunizaciones",
    "total_estudios_imagen",
    "total_suministros",
    "total_reclamos",
]

EVENT_COLUMNS = [
    "tipo_evento",
    "id_evento",
    "id_paciente",
    "id_paciente_fuente",
    "nombre_paciente",
    "id_encuentro",
    "id_encuentro_fuente",
    "fecha_evento",
    "edad_en_evento",
    "concepto_estandar",
    "codigo_fuente",
    "concepto_fuente",
    "valor_numerico",
    "valor_texto",
    "unidad",
    "detalle_evento",
    "nombre_profesional",
    "centro_atencion",
]


def _clean_search(value: str | None, *, max_len: int = 120) -> str | None:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if not cleaned:
        return None
    if CONTROL_CHARS_RE.search(cleaned):
        raise HTTPException(400, "La búsqueda contiene caracteres no permitidos")
    if len(cleaned) > max_len:
        raise HTTPException(400, f"La búsqueda no puede superar {max_len} caracteres")
    return cleaned


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ilike_any(columns: list[str], query: str) -> str:
    pattern = _sql_literal(f"%{query}%")
    return " OR ".join(f"COALESCE({column}::text, '') ILIKE {pattern}" for column in columns)


def _with_permissions(sql: str, claims, data: dict[str, Any]) -> dict[str, Any]:
    ensure_sql_allowed_by_profile(sql, claims)
    return apply_column_permissions_to_result(data, claims, sql)


async def _execute_for_claims(sql: str, claims, page: int, page_size: int) -> dict[str, Any]:
    ensure_sql_allowed_by_profile(sql, claims)
    data = await execute_sql(
        sql,
        page=page,
        page_size=min(page_size, claims.max_page_size or 50),
        max_result_window=get_runtime_config().query_display_max_rows,
    )
    return apply_column_permissions_to_result(data, claims, sql)


@router.get("/patients")
async def list_patients(
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=20, ge=1, le=50),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    require_permission(claims, CLINICAL_HISTORY_PERMISSION)

    search = _clean_search(q)
    where = ""
    if search:
        where = "WHERE " + _ilike_any(
            ["nombre_completo", "id_paciente_fuente", "id_paciente", "genero_estandar", "ciudad", "estado"],
            search,
        )

    sql = f"""
SELECT {", ".join(PATIENT_LIST_COLUMNS)}
FROM {PATIENTS_TABLE}
{where}
ORDER BY nombre_completo NULLS LAST, id_paciente;
""".strip()
    return await _execute_for_claims(sql, claims, page, page_size)


@router.get("/patients/{patient_id}")
async def get_patient_history(
    patient_id: int = Path(..., ge=1),
    event_q: str | None = Query(default=None, max_length=120),
    events_page: int = Query(default=1, ge=1, le=100_000),
    events_page_size: int = Query(default=25, ge=1, le=50),
    authorization: str | None = Header(default=None),
):
    claims = require_claims(authorization)
    require_permission(claims, CLINICAL_HISTORY_PERMISSION)

    patient_sql = f"""
SELECT {", ".join(PATIENT_DETAIL_COLUMNS)}
FROM {PATIENTS_TABLE}
WHERE id_paciente = {patient_id}
ORDER BY id_paciente;
""".strip()
    patient_data = await _execute_for_claims(patient_sql, claims, page=1, page_size=1)
    if not patient_data.get("rows"):
        raise HTTPException(404, "Paciente no encontrado")

    search = _clean_search(event_q)
    event_where = f"WHERE id_paciente = {patient_id}"
    if search:
        event_where += " AND (" + _ilike_any(
            [
                "tipo_evento",
                "concepto_estandar",
                "codigo_fuente",
                "concepto_fuente",
                "valor_texto",
                "unidad",
                "detalle_evento",
                "nombre_profesional",
                "centro_atencion",
                "id_encuentro_fuente",
            ],
            search,
        ) + ")"

    events_sql = f"""
SELECT {", ".join(EVENT_COLUMNS)}
FROM {EVENTS_TABLE}
{event_where}
ORDER BY fecha_evento DESC NULLS LAST, tipo_evento, id_evento DESC;
""".strip()
    events_data = await _execute_for_claims(events_sql, claims, page=events_page, page_size=events_page_size)

    return {
        "patient": patient_data["rows"][0],
        "patient_suppressed_columns": patient_data.get("suppressed_columns", []),
        "events": events_data,
    }

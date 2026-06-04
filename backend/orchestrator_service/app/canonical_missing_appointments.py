from __future__ import annotations

import re
import unicodedata

from .canonical_reports import CanonicalReport

WORD_RE = re.compile(r"[a-záéíóúüñ0-9_]+", re.IGNORECASE)


def canonical_missing_appointments_sql_for_question(nl: str) -> CanonicalReport | None:
    """
    Reporte canónico para pacientes que faltaron/no asistieron a citas o consultas.

    Esta regla vive en el orquestador, antes del traductor externo, porque usa la
    intención en lenguaje natural. Es más segura que reparar semánticamente SQL
    inválido en query_service: solo se activa para una pregunta clara de
    pacientes + ausencia/no asistencia + cita/consulta/visita/encuentro.
    """
    token_list = _tokens(nl)
    tokens = set(token_list)
    normalized = " ".join(token_list)
    if not tokens:
        return None

    patient_terms = {"paciente", "pacientes", "persona", "personas"}
    appointment_terms = {
        "cita", "citas", "consulta", "consultas", "visita", "visitas",
        "encuentro", "encuentros", "atencion", "atenciones", "medica", "medicas",
        "clinica", "clinicas",
    }
    absence_terms = {
        "falto", "faltaron", "faltado", "falta", "faltas", "ausente", "ausentes",
        "inasistencia", "inasistencias", "missed", "noshow", "no_show",
        "cancelado", "cancelada", "cancelados", "canceladas",
    }
    listing_terms = {
        "que", "quienes", "cuales", "lista", "listar", "listame", "muestra",
        "mostrar", "muestrame", "dame", "ver", "reporte", "informe", "pacientes",
    }
    count_terms = {"cuantos", "cuantas", "cantidad", "total", "conteo", "contar", "numero"}

    has_no_assist_phrase = bool(
        re.search(r"\bno\s+asisti(?:o|eron|do|dos|da|das|r|eron)\b", normalized)
        or re.search(r"\bno\s+acudi(?:o|eron|do|dos|da|das|r)\b", normalized)
        or re.search(r"\bno\s+se\s+present(?:o|aron|ado|ados|ada|adas)\b", normalized)
        or re.search(r"\bno\s+show\b", normalized)
    )

    # Esta regla lista pacientes. Si el usuario pide un conteo explícito, no se
    # intercepta: se deja al traductor para no cambiar el tipo de reporte.
    if tokens & count_terms:
        return None

    if not (tokens & patient_terms and tokens & appointment_terms and tokens & listing_terms):
        return None
    if not (tokens & absence_terms or has_no_assist_phrase):
        return None

    return CanonicalReport(
        report_id="patients_missing_medical_appointments",
        description="Pacientes con citas o consultas sin fecha de servicio registrada",
        sql="""
SELECT DISTINCT
    r.id_paciente,
    r.id_paciente_fuente,
    r.nombre_paciente
FROM reporting.vw_reclamos r
WHERE r.fecha_servicio IS NULL
ORDER BY
    r.nombre_paciente ASC,
    r.id_paciente ASC
""".strip(),
    )


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return [m.group(0) for m in WORD_RE.finditer(no_accents)]

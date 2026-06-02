from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

WORD_RE = re.compile(r"[a-záéíóúüñ0-9_]+", re.IGNORECASE)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CanonicalReport:
    report_id: str
    sql: str
    description: str


def canonical_sql_for_question(nl: str) -> CanonicalReport | None:
    """
    Reportes canónicos para preguntas frecuentes o críticas.

    Esta capa es deliberadamente conservadora: solo cubre intenciones claras y
    frecuentes para evitar depender del modelo externo cuando la consulta SQL es
    estable y conocida. Si no hay coincidencia, el flujo continúa con Modal.
    """
    tokens = set(_tokens(nl))
    if not tokens:
        return None

    report = _patient_medical_attention_summary(nl, tokens)
    if report is not None:
        return report

    report = _patients_most_recorded_diseases(tokens)
    if report is not None:
        return report

    report = _encounters_by_year(tokens)
    if report is not None:
        return report

    report = _patients_by_gender(tokens)
    if report is not None:
        return report

    report = _diagnoses_most_frequent(tokens)
    if report is not None:
        return report

    report = _encounters_by_type(tokens)
    if report is not None:
        return report

    report = _patients_most_encounters(tokens)
    if report is not None:
        return report

    return None


def _patient_medical_attention_summary(nl: str, tokens: set[str]) -> CanonicalReport | None:
    """
    Resumen 360 de un paciente cuando el usuario escribe un identificador fuente
    tipo UUID de Synthea. El modelo tiende a compararlo contra id_paciente
    entero; este canónico usa id_paciente_fuente, que es el identificador
    externo/textual mostrado al usuario.
    """
    match = UUID_RE.search(nl or "")
    if not match:
        return None

    patient_terms = {"paciente", "pacientes"}
    summary_terms = {"resumen", "informe", "reporte", "saca", "dame", "muestra", "mostrar", "ver"}
    attention_terms = {
        "atencion", "atenciones", "medica", "medicas", "clinica", "clinicas",
        "actividad", "encuentro", "encuentros", "consulta", "consultas", "historial",
    }

    if not (tokens & patient_terms and (tokens & summary_terms or tokens & attention_terms)):
        return None

    patient_source_id = match.group(0).lower()
    return CanonicalReport(
        report_id="patient_medical_attention_summary_by_source_id",
        description="Resumen 360 de atención médica por identificador fuente del paciente",
        sql=f"""
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    p.ciudad,
    p.estado,
    p.genero_estandar,
    p.fecha_nacimiento,
    p.fallecido,
    p.total_encuentros,
    p.total_diagnosticos,
    p.total_procedimientos,
    p.total_medicamentos,
    p.total_mediciones,
    p.total_observaciones,
    p.total_dispositivos,
    p.total_alergias,
    p.total_planes_cuidado,
    p.total_inmunizaciones,
    p.total_estudios_imagen,
    p.total_suministros,
    p.total_reclamos
FROM reporting.vw_paciente_360 p
WHERE LOWER(p.id_paciente_fuente) = LOWER('{patient_source_id}')
""".strip(),
    )


def _patients_most_recorded_diseases(tokens: set[str]) -> CanonicalReport | None:
    patient_terms = {"paciente", "pacientes"}
    disease_terms = {
        "enfermedad", "enfermedades", "diagnostico", "diagnosticos",
        "condicion", "condiciones", "patologia", "patologias",
        "afeccion", "afecciones", "morbilidad",
    }
    ranking_terms = {
        "mas", "mayor", "mayores", "top", "ranking", "rank", "informe",
        "reporte", "lista", "listar", "muestra", "mostrar", "hazme", "dame",
    }

    if tokens & patient_terms and tokens & disease_terms and tokens & ranking_terms:
        limit = _extract_limit(tokens, default=20, maximum=100)
        return CanonicalReport(
            report_id="patients_most_recorded_diseases",
            description="Pacientes con más enfermedades/diagnósticos registrados",
            sql=f"""
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    COUNT(DISTINCT d.id_diagnostico) AS total_enfermedades_registradas
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d
    ON d.id_paciente = p.id_paciente
GROUP BY
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo
ORDER BY
    COUNT(DISTINCT d.id_diagnostico) DESC,
    p.nombre_completo ASC,
    p.id_paciente ASC
LIMIT {limit}
""".strip(),
        )
    return None


def _encounters_by_year(tokens: set[str]) -> CanonicalReport | None:
    encounter_terms = {
        "encuentro", "encuentros", "atencion", "atenciones", "visita",
        "visitas", "consulta", "consultas", "cita", "citas",
    }
    year_terms = {"ano", "anos", "anio", "anios", "year", "years"}
    count_terms = {
        "cuantos", "cuantas", "cantidad", "total", "conteo", "contar",
        "hubo", "hay", "numero", "resumen", "reporte", "informe",
    }

    if tokens & encounter_terms and tokens & year_terms and tokens & count_terms:
        return CanonicalReport(
            report_id="encounters_by_year",
            description="Cantidad de encuentros médicos por año",
            sql="""
SELECT
    EXTRACT(YEAR FROM e.fecha_inicio)::int AS anio,
    COUNT(DISTINCT e.id_encuentro) AS total_encuentros
FROM reporting.vw_encuentros e
WHERE e.fecha_inicio IS NOT NULL
GROUP BY
    EXTRACT(YEAR FROM e.fecha_inicio)
ORDER BY
    anio ASC
""".strip(),
        )
    return None


def _patients_by_gender(tokens: set[str]) -> CanonicalReport | None:
    patient_terms = {"paciente", "pacientes"}
    gender_terms = {"genero", "sexo", "hombres", "mujeres", "masculino", "femenino"}
    count_terms = {
        "cuantos", "cuantas", "cantidad", "total", "conteo", "contar",
        "distribucion", "resumen", "reporte", "informe",
    }

    if tokens & patient_terms and tokens & gender_terms and tokens & count_terms:
        return CanonicalReport(
            report_id="patients_by_gender",
            description="Cantidad de pacientes por género",
            sql="""
SELECT
    COALESCE(NULLIF(TRIM(p.genero_estandar), ''), 'No especificado') AS genero,
    COUNT(DISTINCT p.id_paciente) AS total_pacientes
FROM reporting.vw_pacientes p
GROUP BY
    COALESCE(NULLIF(TRIM(p.genero_estandar), ''), 'No especificado')
ORDER BY
    total_pacientes DESC,
    genero ASC
""".strip(),
        )
    return None


def _diagnoses_most_frequent(tokens: set[str]) -> CanonicalReport | None:
    disease_terms = {
        "diagnostico", "diagnosticos", "enfermedad", "enfermedades",
        "condicion", "condiciones", "patologia", "patologias", "morbilidad",
    }
    frequency_terms = {
        "frecuente", "frecuentes", "comun", "comunes", "mas", "top",
        "ranking", "rank", "repetidas", "registradas", "resumen", "reporte",
        "informe", "cuales", "cual",
    }

    # Este canónico es para ranking de enfermedades, no para ranking de pacientes.
    if tokens & disease_terms and tokens & frequency_terms and not ({"paciente", "pacientes"} & tokens):
        limit = _extract_limit(tokens, default=20, maximum=100)
        return CanonicalReport(
            report_id="diagnoses_most_frequent",
            description="Diagnósticos/enfermedades más frecuentes",
            sql=f"""
SELECT
    COALESCE(
        NULLIF(TRIM(d.diagnostico_estandar), ''),
        NULLIF(TRIM(d.diagnostico_fuente_estandar), ''),
        NULLIF(TRIM(d.codigo_fuente), ''),
        'No especificado'
    ) AS diagnostico,
    COUNT(DISTINCT d.id_diagnostico) AS total_registros,
    COUNT(DISTINCT d.id_paciente) AS total_pacientes
FROM reporting.vw_diagnosticos d
GROUP BY
    COALESCE(
        NULLIF(TRIM(d.diagnostico_estandar), ''),
        NULLIF(TRIM(d.diagnostico_fuente_estandar), ''),
        NULLIF(TRIM(d.codigo_fuente), ''),
        'No especificado'
    )
ORDER BY
    total_registros DESC,
    total_pacientes DESC,
    diagnostico ASC
LIMIT {limit}
""".strip(),
        )
    return None


def _encounters_by_type(tokens: set[str]) -> CanonicalReport | None:
    encounter_terms = {
        "encuentro", "encuentros", "atencion", "atenciones", "consulta",
        "consultas", "visita", "visitas", "cita", "citas",
    }
    type_terms = {"tipo", "tipos", "clase", "clases", "categoria", "categorias"}
    count_terms = {
        "cuantos", "cuantas", "cantidad", "total", "conteo", "contar",
        "frecuente", "frecuentes", "resumen", "reporte", "informe",
    }

    if tokens & encounter_terms and tokens & type_terms and tokens & count_terms:
        return CanonicalReport(
            report_id="encounters_by_type",
            description="Cantidad de encuentros médicos por tipo",
            sql="""
SELECT
    COALESCE(
        NULLIF(TRIM(e.tipo_encuentro_estandar), ''),
        NULLIF(TRIM(e.tipo_encuentro_fuente), ''),
        'No especificado'
    ) AS tipo_encuentro,
    COUNT(DISTINCT e.id_encuentro) AS total_encuentros
FROM reporting.vw_encuentros e
GROUP BY
    COALESCE(
        NULLIF(TRIM(e.tipo_encuentro_estandar), ''),
        NULLIF(TRIM(e.tipo_encuentro_fuente), ''),
        'No especificado'
    )
ORDER BY
    total_encuentros DESC,
    tipo_encuentro ASC
""".strip(),
        )
    return None


def _patients_most_encounters(tokens: set[str]) -> CanonicalReport | None:
    patient_terms = {"paciente", "pacientes"}
    encounter_terms = {
        "encuentro", "encuentros", "atencion", "atenciones", "consulta",
        "consultas", "visita", "visitas", "cita", "citas",
    }
    ranking_terms = {
        "mas", "mayor", "mayores", "top", "ranking", "rank", "informe",
        "reporte", "lista", "listar", "muestra", "mostrar", "hazme", "dame",
    }

    if tokens & patient_terms and tokens & encounter_terms and tokens & ranking_terms:
        limit = _extract_limit(tokens, default=20, maximum=100)
        return CanonicalReport(
            report_id="patients_most_encounters",
            description="Pacientes con más encuentros médicos registrados",
            sql=f"""
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    COUNT(DISTINCT e.id_encuentro) AS total_encuentros
FROM reporting.vw_pacientes p
JOIN reporting.vw_encuentros e
    ON e.id_paciente = p.id_paciente
GROUP BY
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo
ORDER BY
    COUNT(DISTINCT e.id_encuentro) DESC,
    p.nombre_completo ASC,
    p.id_paciente ASC
LIMIT {limit}
""".strip(),
        )
    return None


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return [m.group(0) for m in WORD_RE.finditer(no_accents)]


def _extract_limit(tokens: set[str], *, default: int, maximum: int) -> int:
    numbers: list[int] = []
    for token in tokens:
        if token.isdigit():
            try:
                value = int(token)
            except ValueError:
                continue
            if value > 0:
                numbers.append(value)
    if not numbers:
        return default
    return min(maximum, max(1, min(numbers)))

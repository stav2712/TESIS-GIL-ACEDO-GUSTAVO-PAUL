from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .canonical_reports import CanonicalReport

WORD_RE = re.compile(r"[a-záéíóúüñ0-9_]+", re.IGNORECASE)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _AgeFilter:
    sql: str


@dataclass(frozen=True)
class _PeriodFilter:
    sql: str
    description: str


@dataclass(frozen=True)
class _ConditionSpec:
    key: str
    label: str
    token_terms: set[str]
    patterns: tuple[str, ...]


CONDITION_SPECS: tuple[_ConditionSpec, ...] = (
    _ConditionSpec(
        key="diabetes",
        label="diabetes",
        token_terms={"diabetes", "diabetico", "diabetica", "diabeticos", "diabeticas"},
        patterns=("diabetes",),
    ),
    _ConditionSpec(
        key="hypertension",
        label="hipertensión",
        token_terms={"hipertension", "hipertenso", "hipertensa", "hipertensos", "hipertensas", "hypertension"},
        patterns=("hypertension", "hipertension", "hipertensión"),
    ),
    _ConditionSpec(
        key="asthma",
        label="asma",
        token_terms={"asma", "asthma", "asmatico", "asmatica", "asmaticos", "asmaticas"},
        patterns=("asthma", "asma"),
    ),
)

PATIENT_TERMS = {"paciente", "pacientes", "persona", "personas"}
PROFESSIONAL_TERMS = {
    "doctor", "doctores", "doctora", "doctoras", "medico", "medicos",
    "medica", "medicas", "profesional", "profesionales", "proveedor",
    "proveedores", "clinico", "clinicos", "clinica", "clinicas",
}
ATTENTION_TERMS = {
    "atendio", "atendieron", "atendido", "atendida", "atendidos", "atendidas",
    "asistio", "asistieron", "asistido", "asistida", "atiende", "atienden",
    "consulta", "consultas", "encuentro", "encuentros", "visita", "visitas",
    "atencion", "atenciones", "trato", "trataron", "vio", "vieron",
}
ENCOUNTER_TERMS = {
    "consulta", "consultas", "encuentro", "encuentros", "visita", "visitas",
    "cita", "citas", "atencion", "atenciones",
}
RANKING_TERMS = {"mas", "mayor", "mayores", "top", "ranking", "rank", "frecuente", "frecuentes"}
CENTER_TERMS = {"centro", "centros", "hospital", "hospitales", "clinica", "clinicas", "sede", "sedes"}
PROCEDURE_TERMS = {"procedimiento", "procedimientos", "procedure", "procedures"}
CHILD_TERMS = {"nino", "ninos", "niña", "niñas", "nina", "ninas", "menor", "menores", "pediatrico", "pediatricos"}
DISEASE_TERMS = {
    "diagnostico", "diagnosticos", "enfermedad", "enfermedades", "condicion",
    "condiciones", "patologia", "patologias", "afeccion", "afecciones",
}
IMMUNIZATION_TERMS = {
    "vacuna", "vacunas", "vacunado", "vacunada", "vacunados", "vacunadas",
    "inmunizacion", "inmunizaciones", "inmunizado", "inmunizada", "inmunizados",
    "inmunizadas",
}
ALIVE_TERMS = {"vivo", "vivos", "viva", "vivas", "sobreviviente", "sobrevivientes"}
HIGH_TERMS = {"alto", "alta", "altos", "altas", "elevado", "elevada", "elevados", "elevadas", "mayor", "mayores"}
MEASUREMENT_TERMS = {"medicion", "mediciones", "medida", "medidas", "resultado", "resultados", "valor", "valores"}
PRESSURE_TERMS = {"presion", "presión", "pressure", "tension", "tensión"}
GLUCOSE_TERMS = {"glucosa", "glucose", "azucar", "azúcar", "glicemia"}


def canonical_quality_sql_for_question(nl: str) -> CanonicalReport | None:
    """
    Canónicos críticos y deliberadamente estrictos.

    Esta capa se ejecuta antes del traductor externo y antes de los canónicos
    legacy. Solo intercepta preguntas con intención muy clara y con patrones que
    ya demostraron fallos semánticos o de esquema. Si una regla no está segura,
    devuelve None para mantener el flujo normal.
    """
    token_list = _tokens(nl)
    tokens = set(token_list)
    normalized = " ".join(token_list)
    if not tokens:
        return None

    checks = (
        _medications_for_patient_with_prescriber,
        _patients_with_bcg_and_asthma,
        _patients_with_multiple_diagnoses,
        _frequent_diagnoses_in_children_recent,
        _alive_patients_with_more_than_n_encounters_this_year,
        _centers_with_more_hypertensive_patients,
        _professionals_with_respiratory_patients_first_quarter,
        _professionals_with_more_procedures_and_centers,
        _patients_with_high_pressure_or_glucose_recent,
    )
    for check in checks:
        report = check(nl, normalized, tokens)
        if report is not None:
            return report
    return None


def should_skip_legacy_canonical_reports(nl: str) -> bool:
    """
    Evita falsos positivos de canónicos legacy demasiado amplios.

    Motivo: el canónico legacy `patients_most_recorded_diseases` puede atrapar
    frases como "dame pacientes con diagnóstico de diabetes" porque considera
    `dame/lista` como señal de ranking. Si la pregunta pide pacientes con una
    condición clínica específica y NO pide ranking/superlativo, es más seguro
    dejarla al traductor que convertirla en "pacientes con más enfermedades".
    """
    token_list = _tokens(nl)
    tokens = set(token_list)
    if not tokens:
        return False

    has_specific_condition = any(tokens & spec.token_terms for spec in CONDITION_SPECS)
    has_specific_condition = has_specific_condition or bool(tokens & {"bcg", "tuberculosis"})
    asks_patients_with_diagnosis = bool(tokens & PATIENT_TERMS and (tokens & DISEASE_TERMS or has_specific_condition))
    asks_ranking = bool(tokens & {"mas", "mayor", "mayores", "top", "ranking", "rank"})

    return asks_patients_with_diagnosis and has_specific_condition and not asks_ranking


def _medications_for_patient_with_prescriber(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    match = UUID_RE.search(nl or "")
    if not match:
        return None

    medication_terms = {"medicamento", "medicamentos", "medicina", "medicinas", "farmaco", "farmacos", "tratamiento", "tratamientos"}
    prescriber_terms = PROFESSIONAL_TERMS | {"indico", "indicó", "indicaron", "receto", "recetó", "recetaron", "prescribio", "prescribió", "prescribieron"}
    received_terms = {"recibio", "recibió", "recibido", "tomo", "tomó", "tomado", "uso", "usó", "usado", "dame", "lista", "listame", "muestra"}

    if not (tokens & medication_terms and tokens & prescriber_terms and tokens & received_terms):
        return None

    patient_source_id = match.group(0).lower()
    return CanonicalReport(
        report_id="patient_medications_with_prescriber_by_source_id",
        description="Medicamentos de un paciente y profesional registrado en la vista de medicamentos",
        sql=f"""
SELECT
    m.id_paciente,
    m.id_paciente_fuente,
    m.nombre_paciente,
    m.id_medicamento,
    COALESCE(
        NULLIF(TRIM(m.medicamento_estandar), ''),
        NULLIF(TRIM(m.medicamento_fuente_estandar), ''),
        NULLIF(TRIM(m.codigo_fuente), ''),
        'No especificado'
    ) AS medicamento,
    m.fecha_inicio,
    m.fecha_fin,
    m.cantidad,
    m.dias_cobertura,
    m.indicacion_texto,
    m.id_profesional,
    COALESCE(NULLIF(TRIM(m.nombre_profesional), ''), 'No especificado') AS nombre_profesional,
    m.id_centro_atencion,
    m.centro_atencion
FROM reporting.vw_medicamentos m
WHERE LOWER(m.id_paciente_fuente) = LOWER('{patient_source_id}')
ORDER BY
    m.fecha_inicio DESC NULLS LAST,
    m.id_medicamento DESC
""".strip(),
    )


def _patients_with_bcg_and_asthma(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & PATIENT_TERMS and tokens & CHILD_TERMS and tokens & IMMUNIZATION_TERMS):
        return None
    if "bcg" not in tokens:
        return None
    if not (tokens & {"asma", "asthma", "asmatico", "asmatica", "asmaticos", "asmaticas"}):
        return None

    return CanonicalReport(
        report_id="minor_patients_with_bcg_and_asthma",
        description="Pacientes menores de edad vacunados con BCG y con diagnóstico de asma",
        sql="""
SELECT DISTINCT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    i.fecha_inmunizacion,
    i.inmunizacion_descripcion,
    d.fecha_inicio AS fecha_diagnostico,
    COALESCE(
        NULLIF(TRIM(d.diagnostico_estandar), ''),
        NULLIF(TRIM(d.diagnostico_fuente_estandar), ''),
        NULLIF(TRIM(d.codigo_fuente), ''),
        'No especificado'
    ) AS diagnostico
FROM reporting.vw_pacientes p
JOIN reporting.vw_inmunizaciones i
    ON i.id_paciente = p.id_paciente
JOIN reporting.vw_diagnosticos d
    ON d.id_paciente = p.id_paciente
WHERE p.edad_actual < 18
  AND (
      i.inmunizacion_descripcion ILIKE '%bcg%'
      OR i.codigo_fuente ILIKE '%bcg%'
  )
  AND (
      d.diagnostico_estandar ILIKE '%asthma%'
      OR d.diagnostico_estandar ILIKE '%asma%'
      OR d.diagnostico_fuente_estandar ILIKE '%asthma%'
      OR d.diagnostico_fuente_estandar ILIKE '%asma%'
      OR d.codigo_fuente ILIKE '%asthma%'
      OR d.codigo_fuente ILIKE '%asma%'
  )
ORDER BY
    p.nombre_completo ASC,
    p.id_paciente ASC,
    i.fecha_inmunizacion DESC NULLS LAST,
    d.fecha_inicio DESC NULLS LAST
""".strip(),
    )


def _patients_with_multiple_diagnoses(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    present = [spec for spec in CONDITION_SPECS if tokens & spec.token_terms]
    if len(present) < 2:
        return None
    if not (tokens & PATIENT_TERMS):
        return None
    if not (tokens & DISEASE_TERMS or tokens & {"tienen", "tiene", "diagnosticados", "diagnosticadas", "sufren", "padecen"}):
        return None

    age_filter = _age_filter_from_text(normalized)
    period_filter = _recent_years_period_filter(normalized, column="d.fecha_inicio")

    where_parts: list[str] = []
    if period_filter:
        where_parts.append(period_filter.sql)
    condition_sql_by_key = {spec.key: _diagnosis_condition_sql("d", spec.patterns) for spec in present}
    where_parts.append("(\n          " + "\n          OR ".join(condition_sql_by_key[spec.key] for spec in present) + "\n      )")
    where_clause = "\n      AND ".join(where_parts)
    having_clause = "\n       AND ".join(f"bool_or({condition_sql_by_key[spec.key]})" for spec in present)
    labels = ", ".join(spec.label for spec in present)

    patient_where = ""
    if age_filter:
        patient_where = f"\nWHERE {age_filter.sql}"

    return CanonicalReport(
        report_id="patients_with_multiple_specific_diagnoses",
        description=f"Pacientes con diagnósticos simultáneos requeridos: {labels}",
        sql=f"""
WITH dx AS (
    SELECT
        d.id_paciente
    FROM reporting.vw_diagnosticos d
    WHERE {where_clause}
    GROUP BY
        d.id_paciente
    HAVING {having_clause}
)
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    p.ciudad,
    p.estado
FROM reporting.vw_pacientes p
JOIN dx
    ON dx.id_paciente = p.id_paciente{patient_where}
ORDER BY
    p.edad_actual DESC NULLS LAST,
    p.nombre_completo ASC,
    p.id_paciente ASC
""".strip(),
    )


def _frequent_diagnoses_in_children_recent(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & DISEASE_TERMS and tokens & {"frecuente", "frecuentes", "comun", "comunes", "mas", "top", "ranking"}):
        return None
    if not (tokens & CHILD_TERMS):
        return None
    years = _extract_recent_years(normalized)
    if years is None:
        return None
    limit = _extract_requested_limit_from_text(normalized, default=10, maximum=100)

    return CanonicalReport(
        report_id="frequent_diagnoses_in_children_recent_years",
        description=f"Diagnósticos más frecuentes en menores de edad durante los últimos {years} años",
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
JOIN reporting.vw_pacientes p
    ON p.id_paciente = d.id_paciente
WHERE d.fecha_inicio >= (CURRENT_DATE - INTERVAL '{years} years')::date
  AND d.fecha_inicio < CURRENT_DATE
  AND COALESCE(
      d.edad_en_evento,
      DATE_PART('year', AGE(d.fecha_inicio, p.fecha_nacimiento))::int
  ) BETWEEN 0 AND 17
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


def _alive_patients_with_more_than_n_encounters_this_year(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & PATIENT_TERMS and tokens & ALIVE_TERMS and tokens & ENCOUNTER_TERMS):
        return None
    if not _mentions_this_year(tokens):
        return None
    threshold = _extract_more_than_number(normalized)
    if threshold is None:
        return None

    return CanonicalReport(
        report_id="alive_patients_more_than_n_encounters_this_year",
        description=f"Pacientes vivos con más de {threshold} consultas/encuentros este año",
        sql=f"""
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    p.ciudad,
    p.estado,
    COUNT(DISTINCT e.id_encuentro) AS total_encuentros
FROM reporting.vw_pacientes p
JOIN reporting.vw_encuentros e
    ON e.id_paciente = p.id_paciente
WHERE p.fallecido = FALSE
  AND e.fecha_inicio >= DATE_TRUNC('year', CURRENT_DATE)::date
  AND e.fecha_inicio < (DATE_TRUNC('year', CURRENT_DATE) + INTERVAL '1 year')::date
GROUP BY
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    p.ciudad,
    p.estado
HAVING COUNT(DISTINCT e.id_encuentro) > {threshold}
ORDER BY
    total_encuentros DESC,
    p.nombre_completo ASC,
    p.id_paciente ASC
""".strip(),
    )


def _centers_with_more_hypertensive_patients(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & CENTER_TERMS and tokens & PATIENT_TERMS and tokens & {"hipertension", "hypertension", "hipertensos", "hipertensas"}):
        return None
    if not (tokens & RANKING_TERMS):
        return None

    return CanonicalReport(
        report_id="care_centers_ranked_by_hypertensive_patients",
        description="Centros de atención con más pacientes con hipertensión",
        sql="""
SELECT
    d.id_centro_atencion,
    COALESCE(NULLIF(TRIM(d.centro_atencion), ''), 'No especificado') AS centro_atencion,
    COUNT(DISTINCT d.id_paciente) AS total_pacientes,
    COUNT(DISTINCT d.id_diagnostico) AS total_diagnosticos
FROM reporting.vw_diagnosticos d
WHERE d.id_centro_atencion IS NOT NULL
  AND (
      d.diagnostico_estandar ILIKE '%hypertension%'
      OR d.diagnostico_estandar ILIKE '%hipertension%'
      OR d.diagnostico_estandar ILIKE '%hipertensión%'
      OR d.diagnostico_fuente_estandar ILIKE '%hypertension%'
      OR d.diagnostico_fuente_estandar ILIKE '%hipertension%'
      OR d.diagnostico_fuente_estandar ILIKE '%hipertensión%'
      OR d.codigo_fuente ILIKE '%hypertension%'
      OR d.codigo_fuente ILIKE '%hipertension%'
      OR d.codigo_fuente ILIKE '%hipertensión%'
  )
GROUP BY
    d.id_centro_atencion,
    COALESCE(NULLIF(TRIM(d.centro_atencion), ''), 'No especificado')
ORDER BY
    total_pacientes DESC,
    total_diagnosticos DESC,
    centro_atencion ASC,
    d.id_centro_atencion ASC
""".strip(),
    )


def _professionals_with_respiratory_patients_first_quarter(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    respiratory_terms = {
        "respiratorio", "respiratoria", "respiratorios", "respiratorias", "respiratory",
        "pulmonar", "pulmonares", "asma", "bronquitis", "neumonia", "neumonía", "epoc", "copd",
    }
    quarter_terms = {"trimestre", "primer", "primero", "q1"}

    if not (tokens & PROFESSIONAL_TERMS and tokens & PATIENT_TERMS and tokens & ATTENTION_TERMS and tokens & respiratory_terms):
        return None
    if not (tokens & quarter_terms and _mentions_this_year(tokens)):
        return None

    respiratory_filter = _diagnosis_condition_sql(
        "d",
        (
            "respiratory", "respiratorio", "respiratoria", "asthma", "asma",
            "pulmonary", "pulmonar", "bronchitis", "bronquitis", "pneumonia",
            "neumonia", "neumonía", "copd", "epoc",
        ),
    )

    return CanonicalReport(
        report_id="professionals_with_respiratory_patients_first_quarter_current_year",
        description="Profesionales que atendieron pacientes con diagnósticos respiratorios en el primer trimestre del año actual",
        sql=f"""
SELECT
    d.id_profesional,
    COALESCE(NULLIF(TRIM(d.nombre_profesional), ''), 'No especificado') AS nombre_profesional,
    d.id_centro_atencion,
    d.centro_atencion,
    COUNT(DISTINCT d.id_paciente) AS total_pacientes,
    COUNT(DISTINCT d.id_diagnostico) AS total_diagnosticos,
    MAX(d.fecha_inicio) AS ultima_fecha_diagnostico
FROM reporting.vw_diagnosticos d
WHERE d.fecha_inicio >= DATE_TRUNC('year', CURRENT_DATE)::date
  AND d.fecha_inicio < (DATE_TRUNC('year', CURRENT_DATE) + INTERVAL '3 months')::date
  AND ({respiratory_filter})
GROUP BY
    d.id_profesional,
    COALESCE(NULLIF(TRIM(d.nombre_profesional), ''), 'No especificado'),
    d.id_centro_atencion,
    d.centro_atencion
ORDER BY
    total_pacientes DESC,
    total_diagnosticos DESC,
    nombre_profesional ASC,
    d.id_profesional ASC
""".strip(),
    )


def _professionals_with_more_procedures_and_centers(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & PROFESSIONAL_TERMS and tokens & PROCEDURE_TERMS and tokens & CENTER_TERMS):
        return None
    if not (tokens & RANKING_TERMS or tokens & {"atendieron", "realizaron", "hicieron"}):
        return None

    return CanonicalReport(
        report_id="professionals_ranked_by_procedures_and_center",
        description="Profesionales con más procedimientos y centro de atención asociado",
        sql="""
SELECT
    pr.id_profesional,
    COALESCE(NULLIF(TRIM(pr.nombre_profesional), ''), 'No especificado') AS nombre_profesional,
    pr.id_centro_atencion,
    COALESCE(NULLIF(TRIM(pr.centro_atencion), ''), 'No especificado') AS centro_atencion,
    COUNT(DISTINCT pr.id_procedimiento) AS total_procedimientos,
    COUNT(DISTINCT pr.id_paciente) AS total_pacientes
FROM reporting.vw_procedimientos pr
WHERE pr.id_profesional IS NOT NULL
GROUP BY
    pr.id_profesional,
    COALESCE(NULLIF(TRIM(pr.nombre_profesional), ''), 'No especificado'),
    pr.id_centro_atencion,
    COALESCE(NULLIF(TRIM(pr.centro_atencion), ''), 'No especificado')
ORDER BY
    total_procedimientos DESC,
    total_pacientes DESC,
    nombre_profesional ASC,
    centro_atencion ASC,
    pr.id_profesional ASC
""".strip(),
    )


def _patients_with_high_pressure_or_glucose_recent(nl: str, normalized: str, tokens: set[str]) -> CanonicalReport | None:
    if not (tokens & PATIENT_TERMS and tokens & MEASUREMENT_TERMS and tokens & HIGH_TERMS):
        return None
    if not (tokens & PRESSURE_TERMS and tokens & GLUCOSE_TERMS):
        return None
    months = _extract_recent_months(normalized)
    if months is None:
        return None

    return CanonicalReport(
        report_id="patients_high_pressure_or_glucose_recent_months",
        description=f"Pacientes con mediciones altas de presión o glucosa en los últimos {months} meses",
        sql=f"""
SELECT DISTINCT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    m.id_medicion,
    m.fecha_medicion,
    COALESCE(
        NULLIF(TRIM(m.medicion_estandar), ''),
        NULLIF(TRIM(m.medicion_fuente_estandar), ''),
        NULLIF(TRIM(m.codigo_fuente), ''),
        'No especificado'
    ) AS medicion,
    m.valor_numerico,
    m.unidad_estandar,
    m.clasificacion_rango
FROM reporting.vw_pacientes p
JOIN reporting.vw_mediciones m
    ON m.id_paciente = p.id_paciente
WHERE m.fecha_medicion >= (CURRENT_DATE - INTERVAL '{months} months')::date
  AND (
      (
          (
              m.medicion_estandar ILIKE '%blood pressure%'
              OR m.medicion_estandar ILIKE '%presion%'
              OR m.medicion_estandar ILIKE '%presión%'
              OR m.medicion_estandar ILIKE '%systolic%'
              OR m.medicion_estandar ILIKE '%diastolic%'
              OR m.medicion_fuente_estandar ILIKE '%blood pressure%'
              OR m.medicion_fuente_estandar ILIKE '%presion%'
              OR m.medicion_fuente_estandar ILIKE '%presión%'
          )
          AND m.valor_numerico > 140
      )
      OR
      (
          (
              m.medicion_estandar ILIKE '%glucose%'
              OR m.medicion_estandar ILIKE '%glucosa%'
              OR m.medicion_estandar ILIKE '%glicemia%'
              OR m.medicion_fuente_estandar ILIKE '%glucose%'
              OR m.medicion_fuente_estandar ILIKE '%glucosa%'
              OR m.medicion_fuente_estandar ILIKE '%glicemia%'
          )
          AND m.valor_numerico > 180
      )
  )
ORDER BY
    m.fecha_medicion DESC NULLS LAST,
    p.nombre_completo ASC,
    p.id_paciente ASC,
    m.id_medicion ASC
""".strip(),
    )


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return [m.group(0) for m in WORD_RE.finditer(no_accents)]


def _diagnosis_condition_sql(alias: str, patterns: tuple[str, ...]) -> str:
    filters: list[str] = []
    for pattern in patterns:
        safe = pattern.replace("'", "''")
        filters.append(
            "("
            f"{alias}.diagnostico_estandar ILIKE '%{safe}%' "
            f"OR {alias}.diagnostico_fuente_estandar ILIKE '%{safe}%' "
            f"OR {alias}.codigo_fuente ILIKE '%{safe}%'"
            ")"
        )
    return "(" + " OR ".join(filters) + ")"


def _age_filter_from_text(normalized: str) -> _AgeFilter | None:
    text = f" {normalized} "
    match = re.search(r"\bmayor(?:es)?\s+(?:de|a|que)\s+(\d{1,3})\s+(?:anos|anios|años)?\b", text)
    if match:
        age = int(match.group(1))
        if 0 <= age <= 130:
            return _AgeFilter(f"p.edad_actual > {age}")
    match = re.search(r"\bmenor(?:es)?\s+(?:de|a|que)\s+(\d{1,3})\s+(?:anos|anios|años)?\b", text)
    if match:
        age = int(match.group(1))
        if 0 <= age <= 130:
            return _AgeFilter(f"p.edad_actual < {age}")
    if re.search(r"\bmenor(?:es)?\s+de\s+edad\b", text):
        return _AgeFilter("p.edad_actual < 18")
    return None


def _recent_years_period_filter(normalized: str, *, column: str) -> _PeriodFilter | None:
    years = _extract_recent_years(normalized)
    if years is None:
        return None
    return _PeriodFilter(
        sql=f"{column} >= (CURRENT_DATE - INTERVAL '{years} years')::date",
        description=f"últimos {years} años",
    )


def _extract_recent_years(normalized: str) -> int | None:
    text = f" {normalized} "
    patterns = [
        r"\bultim(?:o|os|a|as)?\s+(\d{1,2})\s+(?:anos|anios|años)\b",
        r"\b(\d{1,2})\s+ultim(?:o|os|a|as)?\s+(?:anos|anios|años)\b",
        r"\bdurante\s+los\s+ultim(?:o|os|a|as)?\s+(\d{1,2})\s+(?:anos|anios|años)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            years = int(match.group(1))
            if 1 <= years <= 30:
                return years
    return None


def _extract_recent_months(normalized: str) -> int | None:
    text = f" {normalized} "
    patterns = [
        r"\bultim(?:o|os|a|as)?\s+(\d{1,2})\s+mes(?:es)?\b",
        r"\b(\d{1,2})\s+ultim(?:o|os|a|as)?\s+mes(?:es)?\b",
        r"\bdurante\s+los\s+ultim(?:o|os|a|as)?\s+(\d{1,2})\s+mes(?:es)?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            months = int(match.group(1))
            if 1 <= months <= 60:
                return months
    return None


def _mentions_this_year(tokens: set[str]) -> bool:
    return bool(("este" in tokens or "actual" in tokens) and ({"ano", "anio", "años", "ano"} & tokens or "año" in tokens))


def _extract_more_than_number(normalized: str) -> int | None:
    text = f" {normalized} "
    patterns = [
        r"\bmas\s+de\s+(\d{1,4})\b",
        r"\bmayor(?:es)?\s+(?:a|que)\s+(\d{1,4})\b",
        r"\bpor\s+encima\s+de\s+(\d{1,4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 10000:
                return value
    return None


def _extract_requested_limit_from_text(normalized: str, *, default: int, maximum: int) -> int:
    text = f" {normalized} "
    patterns = [
        r"\btop\s+(\d{1,3})\b",
        r"\b(?:primeros|primeras|principales)\s+(\d{1,3})\b",
        r"\b(?:dame|lista|listame|muestra|muestrame)\s+(?:las|los)?\s*(\d{1,3})\b",
        r"\b(?:las|los)\s+(\d{1,3})\s+mas\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if value > 0:
                return min(maximum, value)
    return default

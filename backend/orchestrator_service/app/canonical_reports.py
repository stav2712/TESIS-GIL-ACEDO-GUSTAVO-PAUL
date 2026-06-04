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
    token_list = _tokens(nl)
    tokens = set(token_list)
    normalized = " ".join(token_list)
    if not tokens:
        return None

    report = _professionals_who_attended_patient(nl, tokens)
    if report is not None:
        return report

    report = _patients_hospitalized_recent_period(normalized, tokens)
    if report is not None:
        return report

    report = _patient_medical_attention_summary(nl, tokens)
    if report is not None:
        return report

    # Debe ir antes del ranking genérico de enfermedades, porque
    # "lístame los pacientes con enfermedades respiratorias" pide pacientes
    # filtrados por una categoría clínica, no pacientes con más diagnósticos.
    report = _patients_with_respiratory_diseases(normalized, tokens)
    if report is not None:
        return report

    report = _medications_taken_by_oldest_patient(normalized, tokens)
    if report is not None:
        return report

    # Debe ir antes de otros rankings de pacientes. Cubre tanto extremos altos
    # como bajos de costo, incluida la diferencia crítica entre "más caro",
    # "menos costoso" y "más económico".
    report = _patient_treatment_cost_extreme(normalized, tokens)
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




def _professionals_who_attended_patient(nl: str, tokens: set[str]) -> CanonicalReport | None:
    """
    Lista profesionales/doctores que atendieron a un paciente por UUID fuente.

    Este canónico evita que el modelo mezcle `vw_pacientes` con columnas de
    `vw_profesionales`, un error que produce columnas inexistentes como
    `p.id_profesional_fuente` o `p.nombre_profesional`.
    """
    match = UUID_RE.search(nl or "")
    if not match:
        return None

    patient_terms = {"paciente", "pacientes", "persona", "personas"}
    professional_terms = {
        "doctor", "doctores", "doctora", "doctoras", "medico", "medicos",
        "medica", "medicas", "profesional", "profesionales", "proveedor",
        "proveedores", "provider", "providers", "clinico", "clinicos",
        "clinica", "clinicas",
    }
    attention_terms = {
        "atendio", "atendieron", "atendido", "atendida", "atendidos",
        "atendidas", "atiende", "atienden", "trato", "trataron", "tratado",
        "tratada", "vio", "vieron", "consulta", "consulto", "consultaron",
        "encuentro", "encuentros", "visita", "visitas", "atencion",
        "atenciones", "listame", "listar", "lista", "dame", "muestra",
        "muestrame", "reporta", "reporte", "informe",
    }

    if not (tokens & patient_terms and tokens & professional_terms and tokens & attention_terms):
        return None

    patient_source_id = match.group(0).lower()
    return CanonicalReport(
        report_id="professionals_who_attended_patient_by_source_id",
        description="Profesionales que atendieron a un paciente por identificador fuente",
        sql=f"""
SELECT DISTINCT
    e.id_profesional,
    pr.id_profesional_fuente,
    COALESCE(
        NULLIF(TRIM(pr.nombre_profesional), ''),
        NULLIF(TRIM(e.profesional), ''),
        'No especificado'
    ) AS nombre_profesional,
    pr.especialidad_estandar,
    pr.especialidad_fuente,
    pr.npi,
    pr.id_centro_atencion,
    pr.organizacion_nombre
FROM reporting.vw_encuentros e
LEFT JOIN reporting.vw_profesionales pr
    ON pr.id_profesional = e.id_profesional
WHERE LOWER(e.id_paciente_fuente) = LOWER('{patient_source_id}')
  AND (
      e.id_profesional IS NOT NULL
      OR NULLIF(TRIM(e.profesional), '') IS NOT NULL
  )
ORDER BY
    nombre_profesional ASC,
    e.id_profesional ASC
""".strip(),
    )


def _patients_hospitalized_recent_period(normalized_text: str, tokens: set[str]) -> CanonicalReport | None:
    """
    Pacientes hospitalizados en periodo reciente claro.

    Cubre el caso frecuente "pacientes hospitalizados en el último trimestre" y
    usa `nombre_paciente`, porque `reporting.vw_encuentros` no expone
    `nombre_completo`.
    """
    patient_terms = {"paciente", "pacientes", "persona", "personas"}
    hospitalization_terms = {
        "hospitalizado", "hospitalizada", "hospitalizados", "hospitalizadas",
        "hospitalizacion", "hospitalizaciones", "internado", "internada",
        "internados", "internadas", "ingresado", "ingresada", "ingresados",
        "ingresadas", "inpatient", "hospital",
    }
    listing_terms = {
        "lista", "listar", "listame", "muestra", "mostrar", "muestrame",
        "dame", "ver", "reporte", "informe", "pacientes", "quienes", "que",
    }

    if not (tokens & patient_terms and tokens & hospitalization_terms and tokens & listing_terms):
        return None

    text = f" {normalized_text} "
    if not _has_recent_quarter_or_three_months(text, tokens):
        return None

    return CanonicalReport(
        report_id="patients_hospitalized_last_quarter",
        description="Pacientes hospitalizados en los últimos tres meses",
        sql="""
SELECT DISTINCT
    e.id_paciente,
    e.id_paciente_fuente,
    e.nombre_paciente,
    e.id_encuentro,
    e.id_encuentro_fuente,
    e.fecha_inicio,
    e.fecha_fin,
    e.tipo_encuentro_estandar,
    e.tipo_encuentro_fuente,
    e.id_profesional,
    e.profesional,
    e.id_centro_atencion,
    e.centro_atencion
FROM reporting.vw_encuentros e
WHERE e.fecha_inicio >= (CURRENT_DATE - INTERVAL '3 months')::date
  AND (
      e.tipo_encuentro_estandar ILIKE '%inpatient%'
      OR e.tipo_encuentro_fuente ILIKE '%inpatient%'
      OR e.encounterclass_nativo ILIKE '%inpatient%'
      OR e.descripcion_encuentro_nativa ILIKE '%hospital%'
      OR e.tipo_encuentro_estandar ILIKE '%hospital%'
      OR e.tipo_encuentro_fuente ILIKE '%hospital%'
  )
ORDER BY
    e.fecha_inicio DESC NULLS LAST,
    e.nombre_paciente ASC,
    e.id_paciente ASC,
    e.id_encuentro ASC
""".strip(),
    )


def _has_recent_quarter_or_three_months(text: str, tokens: set[str]) -> bool:
    if re.search(r"\bultim(?:o|a|os|as)\s+trimestre\b", text):
        return True
    if re.search(r"\bultimo\s+trimestre\b", text):
        return True
    if re.search(r"\bultim(?:o|a|os|as)\s+3\s+mes(?:es)?\b", text):
        return True
    if re.search(r"\b3\s+ultim(?:o|a|os|as)\s+mes(?:es)?\b", text):
        return True
    return bool({"trimestre"} & tokens and {"ultimo", "ultimos", "ultima", "ultimas"} & tokens)
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
    summary_terms = {
        "resumen", "informe", "reporte", "saca", "sacame", "dame", "muestra",
        "mostrar", "muestrame", "ver",
    }
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


def _patients_with_respiratory_diseases(
    normalized_text: str,
    tokens: set[str],
) -> CanonicalReport | None:
    """
    Pacientes con diagnósticos respiratorios.

    Regla importante de mantenimiento: si una consulta canónica se activa,
    debe conservar los filtros explícitos de la pregunta. Este reporte soporta
    filtros etarios simples porque son muy frecuentes en preguntas de pacientes
    (por ejemplo, "entre 22 y 30 años"). Si aparecen términos de edad pero no
    se puede interpretar un filtro seguro, no se activa el canónico y el flujo
    continúa con el traductor.
    """
    patient_terms = {"paciente", "pacientes"}
    disease_terms = {
        "enfermedad", "enfermedades", "diagnostico", "diagnosticos", "condicion",
        "condiciones", "patologia", "patologias", "afeccion", "afecciones",
        "problema", "problemas",
    }
    respiratory_terms = {
        "respiratorio", "respiratoria", "respiratorios", "respiratorias",
        "pulmonar", "pulmonares", "asma", "bronquitis", "neumonia", "epoc", "copd",
    }
    listing_terms = {
        "lista", "listar", "listame", "muestra", "mostrar", "muestrame", "dame",
        "ver", "consulta", "consultar", "reporte", "informe", "pacientes", "que",
    }

    if not (
        tokens & patient_terms
        and tokens & respiratory_terms
        and (tokens & disease_terms or tokens & listing_terms)
    ):
        return None

    age_filter = _age_filter_from_text(normalized_text, tokens)
    if age_filter is None and _has_age_terms(tokens):
        # Evita repetir el bug reportado: si la pregunta trae un modificador de
        # edad que esta función no entiende con seguridad, no generamos un SQL
        # parcial que omita ese filtro.
        return None

    # Synthea/OMOP suele exponer conceptos estándar en inglés. Incluimos también
    # variantes en español para no depender de un único idioma de carga.
    patterns = [
        "respiratory", "respiratorio", "respiratoria", "asthma", "asma",
        "chronic obstructive pulmonary", "copd", "epoc", "pulmonary", "pulmonar",
        "bronchitis", "bronquitis", "pneumonia", "neumonia", "neumonía",
        "upper respiratory", "lower respiratory", "sinusitis", "dyspnea", "apnea",
    ]
    filters: list[str] = []
    for pattern in patterns:
        safe = pattern.replace("'", "''")
        filters.append(
            "("
            f"d.diagnostico_estandar ILIKE '%{safe}%' "
            f"OR d.diagnostico_fuente_estandar ILIKE '%{safe}%' "
            f"OR d.codigo_fuente ILIKE '%{safe}%'"
            ")"
        )

    respiratory_where = "\n        OR ".join(filters)
    where_parts = [f"(\n        {respiratory_where}\n    )"]
    description = "Pacientes con enfermedades o diagnósticos respiratorios"
    report_id = "patients_with_respiratory_diseases"
    if age_filter:
        where_parts.insert(0, age_filter.sql)
        report_id = "patients_with_respiratory_diseases_by_age"
        description = f"{description} y filtro de edad"

    where_clause = "\n  AND ".join(where_parts)
    return CanonicalReport(
        report_id=report_id,
        description=description,
        sql=f"""
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    COUNT(DISTINCT d.id_diagnostico) AS total_diagnosticos_respiratorios,
    MAX(d.fecha_inicio) AS ultima_fecha_diagnostico,
    STRING_AGG(
        DISTINCT COALESCE(
            NULLIF(TRIM(d.diagnostico_estandar), ''),
            NULLIF(TRIM(d.diagnostico_fuente_estandar), ''),
            NULLIF(TRIM(d.codigo_fuente), ''),
            'No especificado'
        ),
        '; '
    ) AS diagnosticos_respiratorios
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d
    ON d.id_paciente = p.id_paciente
WHERE
  {where_clause}
GROUP BY
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual
ORDER BY
    p.nombre_completo ASC,
    p.id_paciente ASC
""".strip(),
    )


@dataclass(frozen=True)
class _AgeFilter:
    sql: str


def _has_age_terms(tokens: set[str]) -> bool:
    return bool(
        tokens
        & {
            "edad", "edades", "anos", "años", "año", "ano", "mayor", "mayores",
            "menor", "menores", "adulto", "adultos", "adulta", "adultas",
        }
    )


def _age_filter_from_text(normalized_text: str, tokens: set[str]) -> _AgeFilter | None:
    """
    Interpreta filtros de edad comunes y seguros.

    No intenta ser un parser NL completo; solo cubre patrones explícitos. Si la
    pregunta menciona edad con una forma no soportada, el canónico se desactiva
    para no omitir condiciones importantes.
    """
    text = f" {normalized_text} "

    # "entre 22 y 30 años", "entre 22 a 30 años", "de 22 a 30 años".
    range_patterns = [
        r"\bentre\s+(\d{1,3})\s+(?:y|a|hasta)\s+(\d{1,3})\s+(?:anos|años|anios)\b",
        r"\bde\s+(\d{1,3})\s+a\s+(\d{1,3})\s+(?:anos|años|anios)\b",
        r"\b(?:edad|edades)\s+(?:entre|de)\s+(\d{1,3})\s+(?:y|a|hasta)\s+(\d{1,3})\b",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, text)
        if match:
            lo, hi = sorted((int(match.group(1)), int(match.group(2))))
            if _valid_age_bound(lo) and _valid_age_bound(hi):
                return _AgeFilter(f"p.edad_actual BETWEEN {lo} AND {hi}")
            return None

    # "mayores de 65 años", "mayor a 18 años".
    match = re.search(r"\bmayor(?:es)?\s+(?:de|a|que)\s+(\d{1,3})\s+(?:anos|años|anios)\b", text)
    if match:
        age = int(match.group(1))
        if _valid_age_bound(age):
            return _AgeFilter(f"p.edad_actual > {age}")
        return None

    # "menores de 18 años", "menor a 30 años".
    match = re.search(r"\bmenor(?:es)?\s+(?:de|a|que)\s+(\d{1,3})\s+(?:anos|años|anios)\b", text)
    if match:
        age = int(match.group(1))
        if _valid_age_bound(age):
            return _AgeFilter(f"p.edad_actual < {age}")
        return None

    # "de 65 años" o "65 años" por sí solo es ambiguo: podría significar edad
    # exacta, mayor de, o un periodo. Lo dejamos al modelo.
    return None


def _valid_age_bound(value: int) -> bool:
    return 0 <= value <= 130

def _medications_taken_by_oldest_patient(
    normalized_text: str,
    tokens: set[str],
) -> CanonicalReport | None:
    patient_terms = {"paciente", "pacientes", "persona", "personas"}
    medication_terms = {
        "medicamento", "medicamentos", "medicina", "medicinas", "farmaco", "farmacos",
        "fármaco", "fármacos", "droga", "drogas", "tratamiento", "tratamientos",
    }
    oldest_terms = {
        "longevo", "longeva", "longevos", "longevas", "viejo", "vieja", "viejos",
        "viejas", "anciano", "anciana", "ancianos", "ancianas", "edad", "mayor",
        "avanzada",
    }
    taken_terms = {
        "tomo", "toma", "tomado", "tomaba", "tomaron", "consume", "consumio",
        "consumido", "recibio", "recibido", "recetado", "recetaron", "prescrito",
        "prescritos", "prescrita", "prescritas", "usa", "usado", "utiliza",
        "utilizado", "tuvo", "tiene", "listame", "listar", "lista", "dame",
        "muestra", "muestrame", "reporte", "informe",
    }

    if not (tokens & patient_terms and tokens & medication_terms and tokens & oldest_terms):
        return None
    if not _has_oldest_patient_intent(normalized_text, tokens):
        return None
    if not (
        tokens & taken_terms
        or tokens & {"medicamento", "medicamentos", "medicina", "medicinas", "farmaco", "farmacos"}
    ):
        return None

    return CanonicalReport(
        report_id="medications_taken_by_oldest_patient",
        description="Medicamentos registrados para el paciente más longevo",
        sql="""
WITH paciente_mas_longevo AS (
    SELECT
        p.id_paciente,
        p.id_paciente_fuente,
        p.nombre_completo,
        p.fecha_nacimiento,
        p.edad_actual
    FROM reporting.vw_pacientes p
    WHERE p.fecha_nacimiento IS NOT NULL OR p.edad_actual IS NOT NULL
    ORDER BY
        p.edad_actual DESC NULLS LAST,
        p.fecha_nacimiento ASC NULLS LAST,
        p.id_paciente ASC
    LIMIT 1
)
SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    p.edad_actual,
    p.fecha_nacimiento,
    m.id_medicamento,
    COALESCE(
        NULLIF(TRIM(m.medicamento_estandar), ''),
        NULLIF(TRIM(m.medicamento_fuente_estandar), ''),
        NULLIF(TRIM(m.codigo_fuente), ''),
        'No especificado'
    ) AS medicamento,
    m.fecha_inicio,
    m.fecha_fin,
    m.edad_en_evento,
    m.via_administracion_estandar,
    m.cantidad,
    m.dias_cobertura,
    m.nombre_profesional,
    m.centro_atencion
FROM paciente_mas_longevo p
JOIN reporting.vw_medicamentos m
    ON m.id_paciente = p.id_paciente
ORDER BY
    m.fecha_inicio DESC NULLS LAST,
    m.id_medicamento ASC
""".strip(),
    )


def _has_oldest_patient_intent(normalized_text: str, tokens: set[str]) -> bool:
    """
    Detecta intención superlativa clara: el paciente más longevo/de mayor edad.

    Evita activar este canónico para consultas distintas como
    "pacientes mayores con medicamentos", donde "mayores" significa un grupo
    etario y no el único paciente más viejo del sistema.
    """
    if {"longevo", "longeva", "longevos", "longevas"} & tokens:
        return True

    text = f" {normalized_text} "
    patterns = [
        r"\bmas\s+(viejo|vieja|viejos|viejas|anciano|anciana|ancianos|ancianas)\b",
        r"\b(de|con)\s+mayor\s+edad\b",
        r"\bmayor\s+edad\b",
        r"\b(de|con)\s+mas\s+edad\b",
        r"\bedad\s+mas\s+avanzada\b",
        r"\bmas\s+avanzado\s+en\s+edad\b",
        r"\bmas\s+avanzada\s+en\s+edad\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


_PATIENT_TERMS = {"paciente", "pacientes", "persona", "personas"}
_COST_TERMS = {
    "costo", "costos", "coste", "costes", "costoso", "costosa", "costosos", "costosas",
    "caro", "cara", "caros", "caras", "gasto", "gastos", "monto", "montos",
    "importe", "importes", "reclamo", "reclamos", "cargo", "cargos", "pago", "pagos",
    "economico", "economica", "economicos", "economicas", "barato", "barata", "baratos", "baratas",
}
_TREATMENT_OR_FINANCIAL_TERMS = {
    "tratamiento", "tratamientos", "atencion", "atenciones", "encuentro", "encuentros",
    "consulta", "consultas", "visita", "visitas", "servicio", "servicios", "procedimiento",
    "procedimientos", "medico", "medica", "medicos", "medicas", "salud", "gasto", "gastos",
    "reclamo", "reclamos", "pago", "pagos", "monto", "montos", "importe", "importes", "costo", "costos",
}

_LOW_COST_PATTERNS = [
    r"\bmenos\s+(costoso|costosa|costosos|costosas|caro|cara|caros|caras|alto|alta|altos|altas|elevado|elevada|elevados|elevadas)\b",
    r"\bmas\s+(economico|economica|economicos|economicas|barato|barata|baratos|baratas|bajo|baja|bajos|bajas)\b",
    r"\bmenor(?:es)?\s+(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\b",
    r"\bminim(?:o|a|os|as)\s+(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\b",
    r"\b(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\s+(menor|menores|minimo|minima|minimos|minimas)\b",
    r"\b(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\s+mas\s+(bajo|baja|bajos|bajas|economico|economica|economicos|economicas|barato|barata|baratos|baratas)\b",
]
_HIGH_COST_PATTERNS = [
    r"\bmas\s+(costoso|costosa|costosos|costosas|caro|cara|caros|caras|alto|alta|altos|altas|elevado|elevada|elevados|elevadas)\b",
    r"\bmayor(?:es)?\s+(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\b",
    r"\bmaxim(?:o|a|os|as)\s+(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\b",
    r"\b(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\s+(mayor|mayores|maximo|maxima|maximos|maximas)\b",
    r"\b(costo|costos|coste|costes|gasto|gastos|monto|montos|importe|importes|cargo|cargos|pago|pagos)\s+mas\s+(alto|alta|altos|altas|caro|cara|caros|caras|costoso|costosa|costosos|costosas|elevado|elevada|elevados|elevadas)\b",
    r"\bmenos\s+(economico|economica|economicos|economicas|barato|barata|baratos|baratas)\b",
]


def _patient_treatment_cost_extreme(normalized_text: str, tokens: set[str]) -> CanonicalReport | None:
    """
    Paciente con mayor o menor costo asociado a atención/tratamiento.

    El bug corregido estaba aquí: "menos costoso" contenía el token "costoso" y
    por eso se trataba como mayor costo; "más económico" no se reconocía como
    costo y caía al modelo. La dirección ahora se infiere con patrones de frase,
    no solo por presencia de palabras sueltas.

    No usamos reporting.vw_reclamos para este caso porque esa vista no expone
    `costo_total_reclamo`. El costo total del reclamo asociado al encuentro está
    disponible en reporting.vw_encuentros como `costo_total_reclamo`.
    """
    if not (tokens & _PATIENT_TERMS and tokens & _COST_TERMS and tokens & _TREATMENT_OR_FINANCIAL_TERMS):
        return None

    direction = _infer_cost_direction(normalized_text)
    if direction is None:
        return None

    return _build_treatment_cost_report(direction, tokens)


def _infer_cost_direction(normalized_text: str) -> str | None:
    text = f" {normalized_text} "

    # Prioridad a costo bajo: frases como "menos costoso" también contienen
    # "costoso", que aislado sería una señal de costo alto.
    if any(re.search(pattern, text) for pattern in _LOW_COST_PATTERNS):
        return "low"
    if any(re.search(pattern, text) for pattern in _HIGH_COST_PATTERNS):
        return "high"
    return None


def _build_treatment_cost_report(direction: str, tokens: set[str]) -> CanonicalReport:
    is_low = direction == "low"
    limit = _extract_limit(tokens, default=1, maximum=100)

    report_id = "patient_lowest_treatment_cost" if is_low else "patient_highest_treatment_cost"
    description = (
        "Paciente con menor costo total de atención/tratamiento registrado en encuentros"
        if is_low
        else "Paciente con mayor costo total de atención/tratamiento registrado en encuentros"
    )
    order_total = "ASC" if is_low else "DESC"
    order_individual = "ASC" if is_low else "DESC"
    tie_column = "menor_costo_individual" if is_low else "mayor_costo_individual"

    return CanonicalReport(
        report_id=report_id,
        description=description,
        sql=f"""
WITH costos_por_paciente AS (
    SELECT
        e.id_paciente,
        e.id_paciente_fuente,
        e.nombre_paciente,
        SUM(e.costo_total_reclamo) AS costo_total_tratamientos,
        MIN(e.costo_total_reclamo) AS menor_costo_individual,
        MAX(e.costo_total_reclamo) AS mayor_costo_individual,
        COUNT(DISTINCT e.id_encuentro) AS total_encuentros_con_costo
    FROM reporting.vw_encuentros e
    WHERE e.costo_total_reclamo IS NOT NULL
    GROUP BY
        e.id_paciente,
        e.id_paciente_fuente,
        e.nombre_paciente
)
SELECT
    c.id_paciente,
    c.id_paciente_fuente,
    c.nombre_paciente,
    c.costo_total_tratamientos,
    c.menor_costo_individual,
    c.mayor_costo_individual,
    c.total_encuentros_con_costo
FROM costos_por_paciente c
ORDER BY
    c.costo_total_tratamientos {order_total},
    c.{tie_column} {order_individual},
    c.id_paciente ASC
LIMIT {limit}
""".strip(),
    )


def _patients_most_recorded_diseases(tokens: set[str]) -> CanonicalReport | None:
    patient_terms = {"paciente", "pacientes"}
    disease_terms = {
        "enfermedad", "enfermedades", "diagnostico", "diagnosticos",
        "condicion", "condiciones", "patologia", "patologias", "afeccion",
        "afecciones", "morbilidad",
    }
    ranking_terms = {
        "mas", "mayor", "mayores", "top", "ranking", "rank", "informe",
        "reporte", "lista", "listar", "listame", "muestra", "mostrar",
        "muestrame", "hazme", "dame",
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
        "encuentro", "encuentros", "atencion", "atenciones", "visita", "visitas",
        "consulta", "consultas", "cita", "citas",
    }
    year_terms = {"ano", "anos", "anio", "anios", "year", "years"}
    count_terms = {
        "cuantos", "cuantas", "cantidad", "total", "conteo", "contar", "hubo",
        "hay", "numero", "resumen", "reporte", "informe",
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
        "frecuente", "frecuentes", "comun", "comunes", "mas", "top", "ranking",
        "rank", "repetidas", "registradas", "resumen", "reporte", "informe",
        "cuales", "cual",
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
        "encuentro", "encuentros", "atencion", "atenciones", "consulta", "consultas",
        "visita", "visitas", "cita", "citas",
    }
    type_terms = {"tipo", "tipos", "clase", "clases", "categoria", "categorias"}
    count_terms = {
        "cuantos", "cuantas", "cantidad", "total", "conteo", "contar", "frecuente",
        "frecuentes", "resumen", "reporte", "informe",
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
        "encuentro", "encuentros", "atencion", "atenciones", "consulta", "consultas",
        "visita", "visitas", "cita", "citas",
    }
    ranking_terms = {
        "mas", "mayor", "mayores", "top", "ranking", "rank", "informe", "reporte",
        "lista", "listar", "listame", "muestra", "mostrar", "muestrame", "hazme", "dame",
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

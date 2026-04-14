from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

DB_DIALECT = os.getenv("DB_DIALECT", "postgresql").lower()
DEFAULT_LIMIT = int(os.getenv("DEFAULT_TRANSLATOR_LIMIT", "100"))

@dataclass
class TranslationResult:
    sql: str
    strategy: str = "rules"

def q(text: str) -> str:
    return text.replace("'", "''")

def apply_limit(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    s = sql.strip().rstrip(";")
    if DB_DIALECT == "mssql":
        if " top " in s.lower():
            return s
        return s.replace("SELECT", f"SELECT TOP {limit}", 1)
    if re.search(r"\blimit\s+\d+", s, flags=re.IGNORECASE):
        return s
    return f"{s} LIMIT {limit}"

def build_text_filters(columns: list[str], terms: list[str], codes: list[str] | None = None) -> str:
    predicates: list[str] = []
    for term in terms:
        term = term.strip().lower()
        if not term:
            continue
        for col in columns:
            predicates.append(f"LOWER(COALESCE({col}, '')) LIKE '%{q(term)}%'")
    for code in codes or []:
        code = str(code).strip().lower()
        if code:
            predicates.append(f"LOWER(COALESCE(d.codigo_fuente, '')) = '{q(code)}'")
    return " OR ".join(dict.fromkeys(predicates)) or "1=1"

def current_period_filter(column: str, text: str) -> str:
    t = text.lower()
    if "este año" in t or "este ano" in t:
        return f"EXTRACT(YEAR FROM {column}) = EXTRACT(YEAR FROM CURRENT_DATE)"
    if "año pasado" in t or "ano pasado" in t:
        return f"EXTRACT(YEAR FROM {column}) = EXTRACT(YEAR FROM CURRENT_DATE) - 1"
    if "este mes" in t:
        return f"{column} >= DATE_TRUNC('month', CURRENT_DATE)"
    if "mes pasado" in t or "último mes" in t or "ultimo mes" in t:
        return (
            f"{column} >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') "
            f"AND {column} < DATE_TRUNC('month', CURRENT_DATE)"
        )
    if "últimos 30 días" in t or "ultimos 30 dias" in t:
        return f"{column} >= CURRENT_DATE - INTERVAL '30 days'"
    if "últimos 7 días" in t or "ultimos 7 dias" in t:
        return f"{column} >= CURRENT_DATE - INTERVAL '7 days'"
    return "1=1"

def detect_age_clause(text: str, alias: str = "p") -> str:
    t = text.lower()
    m = re.search(r"entre\s+(\d{1,3})\s+y\s+(\d{1,3})\s+años", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = min(a, b), max(a, b)
        return f"{alias}.edad_actual BETWEEN {lo} AND {hi}"
    m = re.search(r"mayores? de\s+(\d{1,3})\s+años", t)
    if m:
        return f"{alias}.edad_actual > {int(m.group(1))}"
    m = re.search(r"menores? de\s+(\d{1,3})\s+años", t)
    if m:
        return f"{alias}.edad_actual < {int(m.group(1))}"
    return "1=1"

def detect_encounter_filters(text: str, resolved_values: list[dict[str, Any]]) -> list[str]:
    t = text.lower()
    wanted: set[str] = set()

    for item in resolved_values:
        if item.get("field") == "tipo_encuentro":
            canonical = str(item.get("canonical", "")).lower().strip()
            if canonical:
                wanted.add(canonical)

    if "emergencia" in t or "emergency" in t:
        wanted.add("emergencia")
    if "hospitalización" in t or "hospitalizacion" in t or "inpatient" in t:
        wanted.add("hospitalización")
    if "consulta externa" in t or "ambulatoria" in t or "outpatient" in t or "consulta" in t:
        wanted.add("consulta")

    filters = []
    for item in sorted(wanted):
        filters.append(
            "("
            f"LOWER(COALESCE(e.tipo_encuentro_estandar, '')) LIKE '%{q(item)}%' "
            f"OR LOWER(COALESCE(e.tipo_encuentro_fuente, '')) LIKE '%{q(item)}%'"
            ")"
        )
    return filters

def generate_sql_from_rules(
    text: str,
    resolved_terms: list[dict[str, Any]],
    resolved_values: list[dict[str, Any]],
) -> TranslationResult:
    tl = text.lower()
    age_clause = detect_age_clause(tl, alias="p")

    terms = [str(x.get("canonical", "")).lower() for x in resolved_terms if x.get("canonical")]
    codes = [str(code).lower() for x in resolved_terms for code in x.get("codes", [])]

    if any(word in tl for word in ["diagnóstico", "diagnostico", "diabetes", "hipertension", "hipertensión", "infarto", "asma", "condición", "condicion"]):
        diag_filter = build_text_filters(
            ["d.diagnostico_estandar", "d.diagnostico_fuente_estandar", "d.codigo_fuente"],
            terms,
            codes,
        )
        encounter_filters = detect_encounter_filters(tl, resolved_values)
        encounter_clause = " AND " + " AND ".join(encounter_filters) if encounter_filters else ""
        sql = f"""
        SELECT DISTINCT
            p.id_paciente,
            p.edad_actual,
            p.genero_estandar,
            d.id_diagnostico,
            d.fecha_inicio,
            d.diagnostico_estandar,
            d.codigo_fuente,
            e.id_encuentro,
            e.tipo_encuentro_estandar,
            e.fecha_inicio AS fecha_encuentro
        FROM reporting.vw_pacientes p
        JOIN reporting.vw_diagnosticos d
          ON d.id_paciente = p.id_paciente
        LEFT JOIN reporting.vw_encuentros e
          ON e.id_encuentro = d.id_encuentro
        WHERE {age_clause}
          AND {current_period_filter('COALESCE(e.fecha_inicio, d.fecha_inicio)', tl)}
          AND ({diag_filter})
          {encounter_clause}
        ORDER BY COALESCE(e.fecha_inicio, d.fecha_inicio) DESC NULLS LAST
        """
        return TranslationResult(sql=apply_limit(sql), strategy="rules_diagnosis")

    if any(word in tl for word in ["medición", "medicion", "laboratorio", "glucosa", "hemoglobina", "presión arterial", "presion arterial"]):
        measure_filter = build_text_filters(
            ["m.medicion_estandar", "m.medicion_fuente_estandar", "m.codigo_fuente"],
            terms,
            codes,
        )
        sql = f"""
        SELECT
            m.id_medicion,
            m.id_paciente,
            m.id_encuentro,
            m.fecha_medicion,
            m.medicion_estandar,
            m.valor_numerico,
            m.valor_fuente,
            m.unidad_estandar
        FROM reporting.vw_mediciones m
        WHERE {current_period_filter('m.fecha_medicion', tl)}
          AND ({measure_filter})
        ORDER BY m.fecha_medicion DESC NULLS LAST
        """
        return TranslationResult(sql=apply_limit(sql), strategy="rules_measurement")

    sql = f"""
    SELECT
        p.id_paciente,
        p.id_paciente_fuente,
        p.genero_estandar,
        p.edad_actual,
        p.fecha_nacimiento_aprox
    FROM reporting.vw_pacientes p
    WHERE {age_clause}
    ORDER BY p.id_paciente DESC
    """
    return TranslationResult(sql=apply_limit(sql), strategy="rules_patient_listing")
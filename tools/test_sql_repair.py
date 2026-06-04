from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.query_service.app.sql_repair import repair_sql_for_dialect

UUID = "c5219d70-19b5-9078-2441-c911d985ce8b"


def test_repair_postgres_order_by_alias_expression_inside_cte() -> None:
    sql = """
WITH base AS (
  SELECT
    p.id_paciente,
    p.id_paciente_fuente,
    p.nombre_completo,
    COUNT(d.id_diagnostico) AS total_diagnosticos,
    COUNT(m.id_medicamento) AS total_medicamentos,
    COUNT(pr.id_procedimiento) AS total_procedimientos
  FROM reporting.vw_pacientes p
  LEFT JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
  LEFT JOIN reporting.vw_medicamentos m ON m.id_paciente = p.id_paciente
  LEFT JOIN reporting.vw_procedimientos pr ON pr.id_paciente = p.id_paciente
  GROUP BY p.id_paciente, p.id_paciente_fuente, p.nombre_completo
  ORDER BY total_diagnosticos + total_medicamentos + total_procedimientos DESC,
           p.nombre_completo,
           p.id_paciente
  LIMIT 20
)
SELECT * FROM base
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = " ".join(repaired.split())
    assert "ORDER BY (COUNT(d.id_diagnostico)) + (COUNT(m.id_medicamento)) + (COUNT(pr.id_procedimiento)) DESC" in compact


def test_repair_does_not_change_select_distinct_order_by_patient_id() -> None:
    sql = """
SELECT DISTINCT
  id_paciente,
  id_paciente_fuente,
  nombre_paciente
FROM reporting.vw_reclamos
WHERE fecha_servicio IS NULL
ORDER BY nombre_paciente, id_paciente
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = " ".join(repaired.split())
    assert "(DISTINCT)" not in repaired
    assert "ORDER BY nombre_paciente, id_paciente" in compact


def test_repair_does_not_treat_distinct_on_as_alias_expression() -> None:
    sql = """
SELECT DISTINCT ON (id_paciente)
  id_paciente,
  id_paciente_fuente,
  nombre_paciente
FROM reporting.vw_reclamos
ORDER BY id_paciente, nombre_paciente
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = " ".join(repaired.split())
    assert "(DISTINCT" not in repaired
    assert "ORDER BY id_paciente, nombre_paciente" in compact


def test_repair_patient_360_uuid_comparison() -> None:
    sql = f"""
SELECT p.id_paciente, p.id_paciente_fuente
FROM reporting.vw_paciente_360 p
WHERE p.id_paciente = '{UUID}'
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.id_paciente_fuente =" in repaired
    assert "p.id_paciente =" not in repaired


def test_repair_encounter_uuid_comparison() -> None:
    sql = f"""
SELECT e.id_encuentro
FROM reporting.vw_encuentros e
WHERE e.id_paciente = '{UUID}'
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "e.id_paciente_fuente =" in repaired
    assert "e.id_paciente =" not in repaired


def test_repair_does_not_change_numeric_patient_id() -> None:
    sql = "SELECT p.id_paciente FROM reporting.vw_paciente_360 p WHERE p.id_paciente = 123"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.id_paciente = 123" in repaired


def test_repair_vw_pacientes_qualified_nombre_paciente() -> None:
    sql = "SELECT p.id_paciente, p.nombre_paciente FROM reporting.vw_pacientes p ORDER BY p.nombre_paciente"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.nombre_completo" in repaired
    assert "p.nombre_paciente" not in repaired


def test_repair_vw_encuentros_unqualified_nombre_completo() -> None:
    sql = """
SELECT DISTINCT
  id_paciente,
  id_paciente_fuente,
  nombre_completo,
  fecha_inicio,
  centro_atencion
FROM reporting.vw_encuentros
WHERE tipo_encuentro_estandar = 'Inpatient Visit'
ORDER BY fecha_inicio DESC, id_paciente
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "nombre_paciente" in repaired
    assert "nombre_completo" not in repaired


def test_repair_vw_encuentros_qualified_nombre_completo() -> None:
    sql = "SELECT e.id_paciente, e.nombre_completo FROM reporting.vw_encuentros e ORDER BY e.nombre_completo"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "e.nombre_paciente" in repaired
    assert "e.nombre_completo" not in repaired


def test_repair_does_not_change_nombre_completo_when_joining_pacientes() -> None:
    sql = """
SELECT p.id_paciente, p.nombre_completo, e.fecha_inicio
FROM reporting.vw_pacientes p
JOIN reporting.vw_encuentros e ON e.id_paciente = p.id_paciente
ORDER BY p.nombre_completo
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.nombre_completo" in repaired
    assert "p.nombre_paciente" not in repaired


def test_repair_professional_columns_selected_from_patient_alias() -> None:
    sql = f"""
WITH base AS (
    SELECT DISTINCT
        p.id_profesional,
        p.id_profesional_fuente,
        p.nombre_profesional,
        p.especialidad_estandar
    FROM reporting.vw_pacientes p
    JOIN reporting.vw_encuentros e
        ON e.id_paciente = p.id_paciente
    WHERE e.id_paciente = '{UUID}'
    ORDER BY p.nombre_profesional, p.id_profesional
)
SELECT * FROM base
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "JOIN reporting.vw_profesionales" in repaired
    assert "prof_fix.id_profesional_fuente" in repaired
    assert "prof_fix.nombre_profesional" in repaired
    assert "prof_fix.especialidad_estandar" in repaired
    assert "p.id_profesional_fuente" not in repaired
    assert "p.nombre_profesional" not in repaired
    assert "e.id_paciente_fuente =" in repaired


def test_repair_professional_source_id_from_encounter_alias() -> None:
    sql = """
WITH enc_city AS (
    SELECT
        e.id_profesional,
        e.id_profesional_fuente,
        e.nombre_profesional,
        COUNT(*) AS total_encuentros,
        COUNT(DISTINCT e.id_paciente) AS pacientes
    FROM reporting.vw_encuentros e
    GROUP BY e.id_profesional, e.id_profesional_fuente, e.nombre_profesional
)
SELECT * FROM enc_city
ORDER BY total_encuentros DESC, pacientes DESC, nombre_profesional
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "LEFT JOIN reporting.vw_profesionales" in repaired
    assert "prof_fix.id_profesional_fuente" in repaired
    assert "e.profesional AS nombre_profesional" in repaired
    assert "e.id_profesional_fuente" not in repaired
    assert "e.nombre_profesional" not in repaired


def test_repair_professional_source_id_from_encounter_alias_without_nombre_column() -> None:
    sql = """
SELECT e.id_profesional, e.id_profesional_fuente
FROM reporting.vw_encuentros e
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "LEFT JOIN reporting.vw_profesionales" in repaired
    assert "prof_fix.id_profesional_fuente" in repaired
    assert "e.id_profesional_fuente" not in repaired


def test_repair_nombre_profesional_from_encounter_alias_without_join() -> None:
    sql = "SELECT e.id_profesional, e.nombre_profesional FROM reporting.vw_encuentros e"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "e.profesional AS nombre_profesional" in repaired
    assert "e.nombre_profesional" not in repaired
    assert "reporting.vw_profesionales" not in repaired


def test_repair_encounter_professional_columns_reuses_existing_professional_join() -> None:
    sql = """
SELECT e.id_profesional_fuente, e.nombre_profesional
FROM reporting.vw_encuentros e
LEFT JOIN reporting.vw_profesionales pr ON pr.id_profesional = e.id_profesional
"""
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "pr.id_profesional_fuente" in repaired
    assert "e.profesional AS nombre_profesional" in repaired
    assert "e.id_profesional_fuente" not in repaired
    assert repaired.lower().count("reporting.vw_profesionales") == 1


def test_does_not_repair_other_dialects() -> None:
    sql = "SELECT p.nombre_paciente FROM reporting.vw_pacientes p"
    repaired = repair_sql_for_dialect(sql, "sqlite")
    assert repaired == sql


if __name__ == "__main__":
    test_repair_postgres_order_by_alias_expression_inside_cte()
    test_repair_does_not_change_select_distinct_order_by_patient_id()
    test_repair_does_not_treat_distinct_on_as_alias_expression()
    test_repair_patient_360_uuid_comparison()
    test_repair_encounter_uuid_comparison()
    test_repair_does_not_change_numeric_patient_id()
    test_repair_vw_pacientes_qualified_nombre_paciente()
    test_repair_vw_encuentros_unqualified_nombre_completo()
    test_repair_vw_encuentros_qualified_nombre_completo()
    test_repair_does_not_change_nombre_completo_when_joining_pacientes()
    test_repair_professional_columns_selected_from_patient_alias()
    test_repair_professional_source_id_from_encounter_alias()
    test_repair_professional_source_id_from_encounter_alias_without_nombre_column()
    test_repair_nombre_profesional_from_encounter_alias_without_join()
    test_repair_encounter_professional_columns_reuses_existing_professional_join()
    test_does_not_repair_other_dialects()
    print("SQL repair OK")

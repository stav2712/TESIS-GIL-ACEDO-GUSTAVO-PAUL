from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.query_service.app.sql_repair import repair_sql_for_dialect


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def test_misplaced_join_then_same_detail_filters_use_grouped_bool_or() -> None:
    sql = """
WITH base AS (
    SELECT DISTINCT
        p.id_paciente,
        p.id_paciente_fuente,
        p.nombre_completo,
        p.edad_actual,
        p.ciudad,
        p.estado
    FROM reporting.vw_pacientes p
    JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
    WHERE p.edad_actual > 40
      AND d.diagnostico_estandar ILIKE '%diabetes%'
      AND d.fecha_inicio >= CURRENT_DATE - INTERVAL '5 years'
    JOIN reporting.vw_diagnosticos d2 ON d2.id_paciente = p.id_paciente
    WHERE d2.diagnostico_estandar ILIKE '%hypertension%'
      AND d2.fecha_inicio >= CURRENT_DATE - INTERVAL '5 years'
    ORDER BY p.edad_actual DESC, p.nombre_completo, p.id_paciente
)
SELECT * FROM base
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = _compact(repaired)

    assert "JOIN ( SELECT dx.id_paciente FROM reporting.vw_diagnosticos dx" in compact
    assert "GROUP BY dx.id_paciente HAVING bool_or" in compact
    assert "ILIKE '%diabetes%'" in compact
    assert "ILIKE '%hypertension%'" in compact
    assert "WHERE (p.edad_actual > 40) ORDER BY" in compact
    assert "INTERVAL '5 years' JOIN reporting" not in compact
    assert "EXISTS" not in compact


def test_different_detail_views_fall_back_to_exists() -> None:
    sql = """
SELECT DISTINCT p.id_paciente, p.nombre_completo
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
JOIN reporting.vw_medicamentos m ON m.id_paciente = p.id_paciente
WHERE p.edad_actual > 40
  AND d.diagnostico_estandar ILIKE '%diabetes%'
  AND m.medicamento_estandar ILIKE '%insulin%'
ORDER BY p.nombre_completo
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = _compact(repaired)

    assert "EXISTS" in compact
    assert "FROM reporting.vw_diagnosticos d" in compact
    assert "FROM reporting.vw_medicamentos m" in compact
    assert "JOIN ( SELECT" not in compact


def test_no_rewrite_when_detail_column_is_projected() -> None:
    sql = """
SELECT DISTINCT p.id_paciente, p.nombre_completo, d.diagnostico_estandar
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
JOIN reporting.vw_diagnosticos d2 ON d2.id_paciente = p.id_paciente
WHERE p.edad_actual > 40
  AND d.diagnostico_estandar ILIKE '%diabetes%'
  AND d2.diagnostico_estandar ILIKE '%hypertension%'
ORDER BY p.nombre_completo
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")

    assert repaired == sql


def test_no_rewrite_when_between_is_present() -> None:
    sql = """
SELECT DISTINCT p.id_paciente, p.nombre_completo
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
WHERE p.edad_actual BETWEEN 40 AND 80
  AND d.diagnostico_estandar ILIKE '%diabetes%'
ORDER BY p.nombre_completo
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")

    assert repaired == sql


def test_misplaced_join_repair_preserves_or_precedence() -> None:
    sql = """
SELECT p.id_paciente
FROM reporting.vw_pacientes p
WHERE p.edad_actual > 40 OR p.estado ILIKE '%MA%'
JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
WHERE d.diagnostico_estandar ILIKE '%diabetes%'
ORDER BY p.id_paciente
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = _compact(repaired)

    assert "WHERE (p.edad_actual > 40 OR p.estado ILIKE '%MA%') AND (d.diagnostico_estandar ILIKE '%diabetes%') ORDER BY" in compact


def test_misplaced_join_repair_is_postgres_only() -> None:
    sql = """
SELECT p.id_paciente
FROM reporting.vw_pacientes p
WHERE p.edad_actual > 40
JOIN reporting.vw_diagnosticos d ON d.id_paciente = p.id_paciente
WHERE d.diagnostico_estandar ILIKE '%diabetes%'
"""

    assert repair_sql_for_dialect(sql, "sqlite") == sql




def test_many_misplaced_joins_same_detail_view_are_grouped() -> None:
    sql = """
SELECT DISTINCT p.id_paciente, p.nombre_completo
FROM reporting.vw_pacientes p
JOIN reporting.vw_diagnosticos d1 ON d1.id_paciente = p.id_paciente
WHERE p.edad_actual > 40
  AND d1.diagnostico_estandar ILIKE '%diabetes%'
JOIN reporting.vw_diagnosticos d2 ON d2.id_paciente = p.id_paciente
WHERE d2.diagnostico_estandar ILIKE '%hypertension%'
JOIN reporting.vw_diagnosticos d3 ON d3.id_paciente = p.id_paciente
WHERE d3.diagnostico_estandar ILIKE '%asthma%'
JOIN reporting.vw_diagnosticos d4 ON d4.id_paciente = p.id_paciente
WHERE d4.diagnostico_estandar ILIKE '%covid%'
ORDER BY p.nombre_completo
"""

    repaired = repair_sql_for_dialect(sql, "postgresql")
    compact = _compact(repaired)

    assert "JOIN ( SELECT dx.id_paciente FROM reporting.vw_diagnosticos dx" in compact
    assert compact.count("bool_or") == 4
    assert "ILIKE '%diabetes%'" in compact
    assert "ILIKE '%hypertension%'" in compact
    assert "ILIKE '%asthma%'" in compact
    assert "ILIKE '%covid%'" in compact
    assert "JOIN reporting.vw_diagnosticos d2" not in compact
    assert "JOIN reporting.vw_diagnosticos d3" not in compact
    assert "JOIN reporting.vw_diagnosticos d4" not in compact


if __name__ == "__main__":
    test_misplaced_join_then_same_detail_filters_use_grouped_bool_or()
    test_different_detail_views_fall_back_to_exists()
    test_no_rewrite_when_detail_column_is_projected()
    test_no_rewrite_when_between_is_present()
    test_misplaced_join_repair_preserves_or_precedence()
    test_misplaced_join_repair_is_postgres_only()
    test_many_misplaced_joins_same_detail_view_are_grouped()
    print("SQL repair patient filter tests OK")

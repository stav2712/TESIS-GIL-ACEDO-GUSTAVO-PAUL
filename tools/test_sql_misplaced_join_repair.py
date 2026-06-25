from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.query_service.app.sql_repair import repair_sql_for_dialect


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def test_repair_join_after_where_with_second_where_inside_cte() -> None:
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

    assert "JOIN reporting.vw_diagnosticos d2 ON d2.id_paciente = p.id_paciente WHERE" in compact
    assert "(p.edad_actual > 40 AND d.diagnostico_estandar ILIKE '%diabetes%' AND d.fecha_inicio >= CURRENT_DATE - INTERVAL '5 years') AND (d2.diagnostico_estandar" in compact
    assert compact.count(" WHERE ") == 1
    assert "years') ORDER BY" in compact


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


if __name__ == "__main__":
    test_repair_join_after_where_with_second_where_inside_cte()
    test_misplaced_join_repair_preserves_or_precedence()
    test_misplaced_join_repair_is_postgres_only()
    print("Misplaced JOIN SQL repair OK")

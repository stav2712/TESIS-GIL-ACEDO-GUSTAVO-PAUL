from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.query_service.app.sql_order_scope_repair import (  # noqa: E402
    repair_outer_order_by_dangling_qualifiers,
)


def compact(sql: str) -> str:
    return " ".join(sql.split())


def test_repairs_outer_order_by_alias_from_cte() -> None:
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
  JOIN reporting.vw_inmunizaciones i ON i.id_paciente = p.id_paciente
  WHERE p.edad_actual BETWEEN 18 AND 40
    AND i.inmunizacion_descripcion ILIKE '%influenza%'
)
SELECT * FROM base ORDER BY p.nombre_completo, p.id_paciente
"""
    repaired = repair_outer_order_by_dangling_qualifiers(sql, "postgresql")
    assert "ORDER BY nombre_completo, id_paciente" in compact(repaired)
    assert "ORDER BY p.nombre_completo" not in compact(repaired)


def test_keeps_inner_order_by_aliases_untouched() -> None:
    sql = """
WITH base AS (
  SELECT p.id_paciente, p.nombre_completo
  FROM reporting.vw_pacientes p
  ORDER BY p.nombre_completo, p.id_paciente
)
SELECT * FROM base
"""
    repaired = repair_outer_order_by_dangling_qualifiers(sql, "postgresql")
    assert "ORDER BY p.nombre_completo, p.id_paciente" in compact(repaired)


def test_does_not_repair_joined_outer_query() -> None:
    sql = """
WITH base AS (SELECT id_paciente, nombre_completo FROM reporting.vw_pacientes),
     other AS (SELECT id_paciente FROM reporting.vw_paciente_360)
SELECT * FROM base b JOIN other o ON o.id_paciente = b.id_paciente
ORDER BY b.nombre_completo
"""
    repaired = repair_outer_order_by_dangling_qualifiers(sql, "postgresql")
    assert repaired == sql


def test_does_not_repair_other_dialects() -> None:
    sql = "WITH base AS (SELECT 1 AS id) SELECT * FROM base ORDER BY p.id"
    repaired = repair_outer_order_by_dangling_qualifiers(sql, "sqlite")
    assert repaired == sql


if __name__ == "__main__":
    test_repairs_outer_order_by_alias_from_cte()
    test_keeps_inner_order_by_aliases_untouched()
    test_does_not_repair_joined_outer_query()
    test_does_not_repair_other_dialects()
    print("order by scope repair OK")

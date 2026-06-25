from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.query_service.app.sql_repair import repair_sql_for_dialect


def test_unqualified_professional_columns_from_encounters_get_joined():
    sql = (
        "SELECT id_profesional, id_profesional_fuente, nombre_profesional, "
        "COUNT(*) AS total_encuentros "
        "FROM reporting.vw_encuentros "
        "GROUP BY id_profesional, id_profesional_fuente, nombre_profesional "
        "ORDER BY total_encuentros DESC, nombre_profesional, id_profesional"
    )

    repaired = repair_sql_for_dialect(sql, "postgresql")

    assert "FROM reporting.vw_encuentros e" in repaired
    assert "LEFT JOIN reporting.vw_profesionales prof_fix" in repaired
    assert "prof_fix.id_profesional = e.id_profesional" in repaired
    assert "e.id_profesional" in repaired
    assert "prof_fix.id_profesional_fuente" in repaired
    assert "prof_fix.nombre_profesional" in repaired
    assert "GROUP BY e.id_profesional, prof_fix.id_profesional_fuente, prof_fix.nombre_profesional" in repaired
    assert "ORDER BY (COUNT(*)) DESC, prof_fix.nombre_profesional, e.id_profesional" in repaired


def test_does_not_touch_when_professionals_join_already_exists():
    sql = (
        "SELECT p.id_profesional, p.id_profesional_fuente, p.nombre_profesional, "
        "COUNT(*) AS total_encuentros "
        "FROM reporting.vw_encuentros e "
        "JOIN reporting.vw_profesionales p ON p.id_profesional = e.id_profesional "
        "GROUP BY p.id_profesional, p.id_profesional_fuente, p.nombre_profesional "
        "ORDER BY total_encuentros DESC, p.nombre_profesional, p.id_profesional"
    )

    repaired = repair_sql_for_dialect(sql, "postgresql")

    assert "prof_fix" not in repaired
    assert "JOIN reporting.vw_profesionales p" in repaired
    assert "p.id_profesional_fuente" in repaired


def test_unqualified_encounter_profesional_column_does_not_need_join():
    sql = (
        "SELECT id_profesional, profesional, COUNT(*) AS total_encuentros "
        "FROM reporting.vw_encuentros "
        "GROUP BY id_profesional, profesional "
        "ORDER BY total_encuentros DESC"
    )

    repaired = repair_sql_for_dialect(sql, "postgresql")

    assert "reporting.vw_profesionales" not in repaired
    assert "prof_fix" not in repaired


if __name__ == "__main__":
    test_unqualified_professional_columns_from_encounters_get_joined()
    test_does_not_touch_when_professionals_join_already_exists()
    test_unqualified_encounter_profesional_column_does_not_need_join()
    print("SQL repair professional column tests OK")

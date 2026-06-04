from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Valores mínimos para importar módulos del orquestador sin depender del .env real.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("TRANSLATOR_URL", "http://127.0.0.1:9999/translate")
os.environ.setdefault("QUERY_URL", "http://127.0.0.1:8003/execute")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("ALLOWED_TABLES", "reporting.vw_encuentros,reporting.vw_pacientes")

try:
    from backend.orchestrator_service.app.policies import extract_used_tables
except ModuleNotFoundError:
    # Permite ejecutar este test sobre un ZIP parcial. En el proyecto real se usa
    # backend.orchestrator_service.app.config y security reales.
    config_mod = types.ModuleType("backend.orchestrator_service.app.config")
    config_mod.settings = types.SimpleNamespace(ALLOWED_TABLES=os.environ["ALLOWED_TABLES"])
    sys.modules["backend.orchestrator_service.app.config"] = config_mod

    security_mod = types.ModuleType("backend.orchestrator_service.app.security")

    class UserClaims:  # noqa: D401 - stub de test
        """Stub mínimo para importar policies.py."""

    def require_permission(*_args, **_kwargs):
        return None

    security_mod.UserClaims = UserClaims
    security_mod.require_permission = require_permission
    sys.modules["backend.orchestrator_service.app.security"] = security_mod

    from backend.orchestrator_service.app.policies import extract_used_tables

from backend.query_service.app.guardrails import extract_tables, is_safe_select


def test_extract_year_from_alias_column_is_not_table() -> None:
    sql = """
    SELECT EXTRACT(YEAR FROM e.fecha_inicio)::int AS anio,
           COUNT(DISTINCT e.id_encuentro) AS total_encuentros
    FROM reporting.vw_encuentros e
    WHERE e.fecha_inicio IS NOT NULL
    GROUP BY EXTRACT(YEAR FROM e.fecha_inicio)
    ORDER BY anio ASC
    """

    assert extract_used_tables(sql) == {"reporting.vw_encuentros"}
    assert extract_tables(sql) == {"reporting.vw_encuentros"}
    assert is_safe_select(sql)


def test_extract_year_from_unqualified_column_is_not_table() -> None:
    sql = """
    SELECT EXTRACT(YEAR FROM fecha_inicio)::int AS anio,
           COUNT(*) AS total
    FROM reporting.vw_encuentros
    GROUP BY EXTRACT(YEAR FROM fecha_inicio)
    """

    assert extract_used_tables(sql) == {"reporting.vw_encuentros"}
    assert extract_tables(sql) == {"reporting.vw_encuentros"}
    assert is_safe_select(sql)


def test_cte_real_table_is_kept_but_cte_alias_is_ignored() -> None:
    sql = """
    WITH base AS (
        SELECT id_encuentro, fecha_inicio
        FROM reporting.vw_encuentros
    )
    SELECT EXTRACT(YEAR FROM fecha_inicio)::int AS anio, COUNT(*) AS total
    FROM base
    GROUP BY EXTRACT(YEAR FROM fecha_inicio)
    """

    assert extract_used_tables(sql) == {"reporting.vw_encuentros"}
    assert extract_tables(sql) == {"reporting.vw_encuentros"}
    assert is_safe_select(sql)


if __name__ == "__main__":
    test_extract_year_from_alias_column_is_not_table()
    test_extract_year_from_unqualified_column_is_not_table()
    test_cte_real_table_is_kept_but_cte_alias_is_ignored()
    print("SQL table extraction OK")

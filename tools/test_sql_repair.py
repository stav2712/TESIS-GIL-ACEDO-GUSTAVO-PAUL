from backend.query_service.app.sql_repair import repair_sql_for_dialect


def test_repair_postgres_order_by_alias_expression_inside_cte():
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
    assert "ORDER BY (COUNT(d.id_diagnostico)) + (COUNT(m.id_medicamento)) + (COUNT(pr.id_procedimiento)) DESC" in " ".join(repaired.split())


def test_does_not_repair_other_dialects():
    sql = "SELECT COUNT(*) AS total FROM reporting.vw_pacientes ORDER BY total DESC"
    assert repair_sql_for_dialect(sql, "sqlite") == sql

from backend.orchestrator_service.app.canonical_reports import canonical_sql_for_question
from backend.query_service.app.sql_repair import repair_sql_for_dialect

UUID = "c5219d70-19b5-9078-2441-c911d985ce8b"


def test_patient_360_summary_uses_source_id():
    report = canonical_sql_for_question(f"Saca un resumen de la atención médica del paciente {UUID}")
    assert report is not None
    assert report.report_id == "patient_medical_attention_summary_by_source_id"
    assert "reporting.vw_paciente_360" in report.sql
    assert "p.id_paciente_fuente" in report.sql
    assert "LOWER(p.id_paciente_fuente)" in report.sql
    assert f"'{UUID}'" in report.sql


def test_repair_patient_360_uuid_comparison():
    sql = f"""
    SELECT p.id_paciente, p.id_paciente_fuente
    FROM reporting.vw_paciente_360 p
    WHERE p.id_paciente = '{UUID}'
    """
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.id_paciente_fuente =" in repaired
    assert "p.id_paciente =" not in repaired


def test_repair_does_not_change_numeric_patient_id():
    sql = "SELECT p.id_paciente FROM reporting.vw_paciente_360 p WHERE p.id_paciente = 123"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "p.id_paciente = 123" in repaired


def test_repair_unqualified_when_single_patient_view():
    sql = f"SELECT * FROM reporting.vw_paciente_360 WHERE id_paciente = '{UUID}'"
    repaired = repair_sql_for_dialect(sql, "postgresql")
    assert "id_paciente_fuente =" in repaired


if __name__ == "__main__":
    test_patient_360_summary_uses_source_id()
    test_repair_patient_360_uuid_comparison()
    test_repair_does_not_change_numeric_patient_id()
    test_repair_unqualified_when_single_patient_view()
    print("patient uuid fix OK")

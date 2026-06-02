from backend.orchestrator_service.app.canonical_reports import canonical_sql_for_question


def test_patients_with_most_diseases_report():
    report = canonical_sql_for_question("Hazme el informe de los pacientes con más enfermedades registradas")
    assert report is not None
    assert report.report_id == "patients_most_recorded_diseases"
    assert "COUNT(DISTINCT d.id_diagnostico)" in report.sql
    assert "reporting.vw_diagnosticos" in report.sql


def test_encounters_by_year_report():
    report = canonical_sql_for_question("Cuántos encuentros médicos hubo por año")
    assert report is not None
    assert report.report_id == "encounters_by_year"
    assert "EXTRACT(YEAR FROM e.fecha_inicio)" in report.sql
    assert "COUNT(DISTINCT e.id_encuentro)" in report.sql
    assert "reporting.vw_encuentros" in report.sql


def test_patients_by_gender_report():
    report = canonical_sql_for_question("Cuántos pacientes hay por género")
    assert report is not None
    assert report.report_id == "patients_by_gender"
    assert "p.genero_estandar" in report.sql


def test_frequent_diagnoses_report():
    report = canonical_sql_for_question("Cuáles son los diagnósticos más frecuentes")
    assert report is not None
    assert report.report_id == "diagnoses_most_frequent"
    assert "d.diagnostico_estandar" in report.sql


def test_patients_with_most_encounters_report():
    report = canonical_sql_for_question("Muestra los pacientes con más encuentros médicos")
    assert report is not None
    assert report.report_id == "patients_most_encounters"
    assert "COUNT(DISTINCT e.id_encuentro)" in report.sql


def test_non_matching_question_returns_none():
    report = canonical_sql_for_question("Muéstrame recetas de cocina")
    assert report is None

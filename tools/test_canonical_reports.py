from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator_service.app.canonical_reports import canonical_sql_for_question


def test_patients_with_most_diseases_report() -> None:
    report = canonical_sql_for_question("Hazme el informe de los pacientes con más enfermedades registradas")
    assert report is not None
    assert report.report_id == "patients_most_recorded_diseases"
    assert "COUNT(DISTINCT d.id_diagnostico)" in report.sql
    assert "reporting.vw_diagnosticos" in report.sql


def test_patients_with_respiratory_diseases_report() -> None:
    report = canonical_sql_for_question("lístame los pacientes con enfermedades respiratorias")
    assert report is not None
    assert report.report_id == "patients_with_respiratory_diseases"
    assert "reporting.vw_pacientes p" in report.sql
    assert "reporting.vw_diagnosticos d" in report.sql
    assert "p.nombre_completo" in report.sql
    assert "diagnosticos_respiratorios" in report.sql


def test_patients_with_respiratory_diseases_preserves_age_range() -> None:
    report = canonical_sql_for_question("Pacientes entre 22 y 30 años con problemas respiratorios")
    assert report is not None
    assert report.report_id == "patients_with_respiratory_diseases_by_age"
    assert "reporting.vw_pacientes p" in report.sql
    assert "reporting.vw_diagnosticos d" in report.sql
    assert "p.edad_actual BETWEEN 22 AND 30" in report.sql
    assert "p.nombre_completo" in report.sql
    assert "d.nombre_paciente" not in report.sql


def test_patients_with_respiratory_diseases_ambiguous_age_falls_back_to_model() -> None:
    report = canonical_sql_for_question("Pacientes de 30 años con problemas respiratorios")
    assert report is None or report.report_id != "patients_with_respiratory_diseases"


def test_encounters_by_year_report() -> None:
    report = canonical_sql_for_question("Cuántos encuentros médicos hubo por año")
    assert report is not None
    assert report.report_id == "encounters_by_year"
    assert "EXTRACT(YEAR FROM e.fecha_inicio)" in report.sql
    assert "COUNT(DISTINCT e.id_encuentro)" in report.sql
    assert "reporting.vw_encuentros" in report.sql


def test_patients_by_gender_report() -> None:
    report = canonical_sql_for_question("Cuántos pacientes hay por género")
    assert report is not None
    assert report.report_id == "patients_by_gender"
    assert "p.genero_estandar" in report.sql


def test_frequent_diagnoses_report() -> None:
    report = canonical_sql_for_question("Cuáles son los diagnósticos más frecuentes")
    assert report is not None
    assert report.report_id == "diagnoses_most_frequent"
    assert "d.diagnostico_estandar" in report.sql


def test_patients_with_most_encounters_report() -> None:
    report = canonical_sql_for_question("Muestra los pacientes con más encuentros médicos")
    assert report is not None
    assert report.report_id == "patients_most_encounters"
    assert "COUNT(DISTINCT e.id_encuentro)" in report.sql


def test_patient_highest_treatment_cost_report() -> None:
    report = canonical_sql_for_question("qué paciente ha tenido el tratamiento más costoso?")
    assert report is not None
    assert report.report_id == "patient_highest_treatment_cost"
    assert "reporting.vw_encuentros" in report.sql
    assert "costo_total_reclamo" in report.sql
    assert "nombre_paciente" in report.sql
    assert "nombre_completo" not in report.sql
    assert "reporting.vw_reclamos" not in report.sql
    assert "c.costo_total_tratamientos DESC" in report.sql


def test_patient_highest_treatment_cost_caro_report() -> None:
    report = canonical_sql_for_question("qué paciente ha tenido el tratamiento más caro?")
    assert report is not None
    assert report.report_id == "patient_highest_treatment_cost"
    assert "c.costo_total_tratamientos DESC" in report.sql


def test_patients_lowest_treatment_cost_menos_costoso_report() -> None:
    report = canonical_sql_for_question("qué pacientes han tenido el tratamiento menos costoso?")
    assert report is not None
    assert report.report_id == "patient_lowest_treatment_cost"
    assert "reporting.vw_encuentros" in report.sql
    assert "costo_total_reclamo" in report.sql
    assert "nombre_paciente" in report.sql
    assert "reporting.vw_reclamos" not in report.sql
    assert "c.costo_total_tratamientos ASC" in report.sql
    assert "c.menor_costo_individual ASC" in report.sql


def test_patients_lowest_treatment_cost_mas_economico_report() -> None:
    report = canonical_sql_for_question("qué pacientes han tenido el tratamiento más económico?")
    assert report is not None
    assert report.report_id == "patient_lowest_treatment_cost"
    assert "c.costo_total_tratamientos ASC" in report.sql


def test_patients_lowest_treatment_cost_mas_barato_report() -> None:
    report = canonical_sql_for_question("dame el paciente con el tratamiento más barato")
    assert report is not None
    assert report.report_id == "patient_lowest_treatment_cost"
    assert "c.costo_total_tratamientos ASC" in report.sql


def test_patient_treatment_cost_limit_respects_top_n() -> None:
    report = canonical_sql_for_question("top 5 pacientes con mayor costo de tratamiento")
    assert report is not None
    assert report.report_id == "patient_highest_treatment_cost"
    assert "LIMIT 5" in report.sql


def test_age_filter_like_less_than_does_not_trigger_cost_report() -> None:
    report = canonical_sql_for_question("pacientes con menos de 18 años y tratamientos")
    assert report is None or report.report_id != "patient_lowest_treatment_cost"



def test_patients_hospitalized_last_quarter_report() -> None:
    report = canonical_sql_for_question("pacientes que han sido hospitalizados en el último trimestre")
    assert report is not None
    assert report.report_id == "patients_hospitalized_last_quarter"
    assert "reporting.vw_encuentros" in report.sql
    assert "e.nombre_paciente" in report.sql
    assert "nombre_completo" not in report.sql
    assert "INTERVAL '3 months'" in report.sql


def test_professionals_who_attended_patient_by_uuid_report() -> None:
    uuid = "c5219d70-19b5-9078-2441-c911d985ce8b"
    report = canonical_sql_for_question(
        f"hola, una disculpa, podrías listarme qué doctores atendieron al paciente {uuid}? por favor, gracias"
    )
    assert report is not None
    assert report.report_id == "professionals_who_attended_patient_by_source_id"
    assert "reporting.vw_encuentros" in report.sql
    assert "reporting.vw_profesionales" in report.sql
    assert "LOWER(e.id_paciente_fuente)" in report.sql
    assert "p.id_profesional_fuente" not in report.sql
    assert "p.nombre_profesional" not in report.sql

def test_non_matching_question_returns_none() -> None:
    report = canonical_sql_for_question("Muéstrame recetas de cocina")
    assert report is None


def test_medications_taken_by_oldest_patient_report() -> None:
    report = canonical_sql_for_question(
        "hola, disculpa, podrías listarme los medicamentos que tomó el paciente más longevo? gracias"
    )
    assert report is not None
    assert report.report_id == "medications_taken_by_oldest_patient"
    assert "reporting.vw_pacientes" in report.sql
    assert "reporting.vw_medicamentos" in report.sql
    assert "p.nombre_completo" in report.sql
    assert "p.nombre_paciente" not in report.sql


def test_medications_taken_by_patient_with_greatest_age_report() -> None:
    report = canonical_sql_for_question("lista los medicamentos del paciente de mayor edad")
    assert report is not None
    assert report.report_id == "medications_taken_by_oldest_patient"


def test_older_patients_with_medications_does_not_trigger_oldest_patient_report() -> None:
    report = canonical_sql_for_question("lista pacientes mayores con medicamentos")
    assert report is None or report.report_id != "medications_taken_by_oldest_patient"


if __name__ == "__main__":
    test_patients_with_most_diseases_report()
    test_patients_with_respiratory_diseases_report()
    test_patients_with_respiratory_diseases_preserves_age_range()
    test_patients_with_respiratory_diseases_ambiguous_age_falls_back_to_model()
    test_encounters_by_year_report()
    test_patients_by_gender_report()
    test_frequent_diagnoses_report()
    test_patients_with_most_encounters_report()
    test_patient_highest_treatment_cost_report()
    test_patient_highest_treatment_cost_caro_report()
    test_patients_lowest_treatment_cost_menos_costoso_report()
    test_patients_lowest_treatment_cost_mas_economico_report()
    test_patients_lowest_treatment_cost_mas_barato_report()
    test_patient_treatment_cost_limit_respects_top_n()
    test_age_filter_like_less_than_does_not_trigger_cost_report()
    test_patients_hospitalized_last_quarter_report()
    test_professionals_who_attended_patient_by_uuid_report()
    test_non_matching_question_returns_none()
    test_medications_taken_by_oldest_patient_report()
    test_medications_taken_by_patient_with_greatest_age_report()
    test_older_patients_with_medications_does_not_trigger_oldest_patient_report()

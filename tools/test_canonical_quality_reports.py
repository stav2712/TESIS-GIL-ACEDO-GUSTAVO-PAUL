from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator_service.app.canonical_quality_reports import (  # noqa: E402
    canonical_quality_sql_for_question,
    should_skip_legacy_canonical_reports,
)


def _sql(question: str) -> str:
    report = canonical_quality_sql_for_question(question)
    assert report is not None, question
    return report.sql.lower()


def test_multiple_diagnoses_uses_grouped_bool_or() -> None:
    sql = _sql("cuáles son los pacientes mayores de 40 años diagnosticados con diabetes e hipertensión en los últimos 5 años")
    assert "with dx as" in sql
    assert "group by" in sql
    assert "having" in sql
    assert "bool_or" in sql
    assert "diabetes" in sql
    assert "hypertension" in sql or "hipertension" in sql
    assert "p.edad_actual > 40" in sql
    assert "interval '5 years'" in sql


def test_three_conditions_are_all_required() -> None:
    sql = _sql("qué pacientes tienen asma, diabetes e hipertensión al mismo tiempo")
    assert sql.count("bool_or") >= 3
    assert "asthma" in sql or "asma" in sql
    assert "diabetes" in sql
    assert "hypertension" in sql or "hipertension" in sql


def test_bcg_asthma_minor_patients() -> None:
    sql = _sql("dame los pacientes menores de edad que fueron vacunados con BCG y también tuvieron diagnóstico de asma")
    assert "vw_inmunizaciones" in sql
    assert "vw_diagnosticos" in sql
    assert "p.edad_actual < 18" in sql
    assert "bcg" in sql
    assert "asthma" in sql or "asma" in sql


def test_patient_medications_prescriber_does_not_join_procedures() -> None:
    sql = _sql("qué medicamentos recibió el paciente c5219d70-19b5-9078-2441-c911d985ce8b y qué doctor se los indicó")
    assert "vw_medicamentos" in sql
    assert "vw_procedimientos" not in sql
    assert "nombre_profesional" in sql
    assert "id_paciente_fuente" in sql


def test_children_diagnoses_recent_years_keeps_filters() -> None:
    sql = _sql("cuáles son las enfermedades más frecuentes en niños durante los últimos 3 años")
    assert "vw_diagnosticos" in sql
    assert "vw_pacientes" in sql
    assert "interval '3 years'" in sql
    assert "between 0 and 17" in sql
    assert "limit 3" not in sql


def test_alive_patients_more_than_three_encounters_this_year() -> None:
    sql = _sql("qué pacientes vivos han tenido más de 3 consultas este año")
    assert "p.fallecido = false" in sql
    assert "date_trunc('year', current_date)" in sql
    assert "having count(distinct e.id_encuentro) > 3" in sql
    assert "limit 3" not in sql


def test_centers_hypertension_returns_centers_not_patients() -> None:
    sql = _sql("qué centros de atención atendieron más pacientes con hipertensión")
    assert "id_centro_atencion" in sql
    assert "centro_atencion" in sql
    assert "count(distinct d.id_paciente)" in sql
    assert "nombre_completo" not in sql


def test_professionals_procedures_center() -> None:
    sql = _sql("qué profesionales atendieron más procedimientos y en qué centro trabajan")
    assert "vw_procedimientos" in sql
    assert "id_profesional" in sql
    assert "centro_atencion" in sql
    assert "total_procedimientos" in sql


def test_respiratory_professionals_first_quarter() -> None:
    sql = _sql("qué doctores atendieron pacientes con problemas respiratorios en el primer trimestre de este año")
    assert "vw_diagnosticos" in sql
    assert "interval '3 months'" in sql
    assert "respiratory" in sql or "respiratorio" in sql
    assert "total_pacientes" in sql


def test_high_pressure_glucose_keeps_date_outside_or_group() -> None:
    sql = _sql("pacientes con mediciones altas de presión o glucosa en los últimos 12 meses")
    assert "vw_mediciones" in sql
    assert "interval '12 months'" in sql
    assert "hemoglobin" not in sql
    assert "m.fecha_medicion >=" in sql
    assert "or" in sql


def test_quality_layer_does_not_catch_broad_questions() -> None:
    assert canonical_quality_sql_for_question("cuántos pacientes hay") is None
    assert canonical_quality_sql_for_question("dame todos los médicos") is None
    assert canonical_quality_sql_for_question("lista los centros de atención") is None


def test_guard_skips_legacy_for_specific_patient_diagnosis_without_ranking() -> None:
    assert should_skip_legacy_canonical_reports("dame pacientes con diagnóstico de diabetes") is True
    assert should_skip_legacy_canonical_reports("pacientes con más diagnósticos") is False
    assert should_skip_legacy_canonical_reports("cuáles son las enfermedades más frecuentes") is False


if __name__ == "__main__":
    test_multiple_diagnoses_uses_grouped_bool_or()
    test_three_conditions_are_all_required()
    test_bcg_asthma_minor_patients()
    test_patient_medications_prescriber_does_not_join_procedures()
    test_children_diagnoses_recent_years_keeps_filters()
    test_alive_patients_more_than_three_encounters_this_year()
    test_centers_hypertension_returns_centers_not_patients()
    test_professionals_procedures_center()
    test_respiratory_professionals_first_quarter()
    test_high_pressure_glucose_keeps_date_outside_or_group()
    test_quality_layer_does_not_catch_broad_questions()
    test_guard_skips_legacy_for_specific_patient_diagnosis_without_ranking()
    print("OK")

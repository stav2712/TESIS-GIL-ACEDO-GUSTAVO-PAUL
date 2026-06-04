from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator_service.app.canonical_missing_appointments import (  # noqa: E402
    canonical_missing_appointments_sql_for_question,
)


def test_patients_missing_medical_consultations_report() -> None:
    report = canonical_missing_appointments_sql_for_question(
        "qué pacientes han faltado a sus consultas médicas?"
    )
    assert report is not None
    assert report.report_id == "patients_missing_medical_appointments"
    assert "reporting.vw_reclamos" in report.sql
    assert "fecha_servicio IS NULL" in report.sql
    assert "estado_encuentro" not in report.sql
    assert "reporting.vw_encuentros" not in report.sql


def test_patients_missing_appointments_report() -> None:
    report = canonical_missing_appointments_sql_for_question(
        "qué pacientes han faltado a sus citas?"
    )
    assert report is not None
    assert "r.nombre_paciente" in report.sql


def test_count_question_is_not_intercepted() -> None:
    report = canonical_missing_appointments_sql_for_question(
        "cuántos pacientes han faltado a sus consultas médicas?"
    )
    assert report is None


def test_unrelated_cancelled_encounter_question_is_not_intercepted() -> None:
    report = canonical_missing_appointments_sql_for_question(
        "lista centros con consultas canceladas por mes"
    )
    assert report is None


if __name__ == "__main__":
    test_patients_missing_medical_consultations_report()
    test_patients_missing_appointments_report()
    test_count_question_is_not_intercepted()
    test_unrelated_cancelled_encounter_question_is_not_intercepted()
    print("Canonical missing appointments OK")

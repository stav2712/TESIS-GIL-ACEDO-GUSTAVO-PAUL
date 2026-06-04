from __future__ import annotations

from pathlib import Path
import os
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("TRANSLATOR_URL", "http://127.0.0.1:8001/translate")
os.environ.setdefault("QUERY_URL", "http://127.0.0.1:8003/execute")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("OPENAI_TITLE_ENABLED", "false")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator_service.app.report_title import (  # noqa: E402
    _is_bad_ai_title,
    clean_report_title,
    fallback_report_title,
    legacy_truncated_title,
)


def test_no_ellipsis_when_cleaning() -> None:
    value = "qué pacientes han tenido el tratamiento menos costoso y en qué centros fueron atendidos?..."
    title = clean_report_title(value, max_chars=80)
    assert "..." not in title
    assert "…" not in title
    assert len(title) <= 80


def test_legacy_title_still_detectable() -> None:
    nl = "qué pacientes han tenido el tratamiento menos costoso y en qué centros fueron atendidos?"
    legacy = legacy_truncated_title(nl)
    assert legacy.endswith("…")


def test_cost_titles_are_report_titles() -> None:
    assert fallback_report_title("qué pacientes han tenido el tratamiento menos costoso?") == "Pacientes con tratamientos de menor costo"
    assert fallback_report_title("qué paciente ha tenido el tratamiento más caro?") == "Pacientes con tratamientos de mayor costo"
    assert fallback_report_title("qué pacientes han tenido el tratamiento más económico?") == "Pacientes con tratamientos de menor costo"


def test_patient_condition_title_does_not_add_time_filter() -> None:
    assert fallback_report_title("qué pacientes sufren de asma?") == "Pacientes con asma"
    assert _is_bad_ai_title(
        "Pacientes diagnosticados con asma en el último año",
        "qué pacientes sufren de asma?",
    )
    assert not _is_bad_ai_title("Pacientes con asma", "qué pacientes sufren de asma?")


if __name__ == "__main__":
    test_no_ellipsis_when_cleaning()
    test_legacy_title_still_detectable()
    test_cost_titles_are_report_titles()
    test_patient_condition_title_does_not_add_time_filter()
    print("OK")

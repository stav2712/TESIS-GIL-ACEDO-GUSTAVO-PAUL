from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator_service.app.logs_repo import MongoRepo


def _repo() -> MongoRepo:
    # Evita abrir conexión real a Mongo; solo probamos helpers puros.
    return MongoRepo.__new__(MongoRepo)


def test_failed_job_keeps_user_snapshot() -> None:
    repo = _repo()
    row = repo._audit_row_from_failed_job(
        {
            "job_id": "j1",
            "user_id": 1,
            "username": "admin",
            "full_name": "Administrador",
            "profile": "admin",
            "conversation_id": "c1",
            "nl": "pregunta inválida",
            "status": "failed",
            "error": "Error controlado",
            "created_at": "2026-06-03T00:00:00+00:00",
            "updated_at": "2026-06-03T00:00:01+00:00",
            "finished_at": "2026-06-03T00:00:01+00:00",
        }
    )

    assert row["username"] == "admin"
    assert row["full_name"] == "Administrador"
    assert row["profile"] == "admin"
    assert row["status"] == "failed"


def test_failed_job_admin_legacy_fallback() -> None:
    repo = _repo()
    row = repo._audit_row_from_failed_job(
        {
            "job_id": "j2",
            "user_id": 1,
            "username": "admin",
            "conversation_id": "c1",
            "nl": "pregunta inválida",
            "status": "failed",
            "error": "Error controlado",
            "created_at": "2026-06-03T00:00:00+00:00",
            "updated_at": "2026-06-03T00:00:01+00:00",
            "finished_at": "2026-06-03T00:00:01+00:00",
        }
    )

    assert row["username"] == "admin"
    assert row["full_name"] == "Administrador"
    assert row["profile"] == "admin"


def test_failed_job_can_be_enriched_from_report_identity() -> None:
    repo = _repo()
    by_user_id = {
        2: {
            "username": "tavo",
            "full_name": "Gustavo Gil",
            "profile": "consulta",
        }
    }
    row = repo._audit_row_from_failed_job(
        {
            "job_id": "j3",
            "user_id": 2,
            "username": "tavo",
            "conversation_id": "c1",
            "nl": "pregunta inválida",
            "status": "failed",
            "error": "Error controlado",
            "created_at": "2026-06-03T00:00:00+00:00",
            "updated_at": "2026-06-03T00:00:01+00:00",
            "finished_at": "2026-06-03T00:00:01+00:00",
        },
        by_user_id=by_user_id,
    )

    assert row["username"] == "tavo"
    assert row["full_name"] == "Gustavo Gil"
    assert row["profile"] == "consulta"

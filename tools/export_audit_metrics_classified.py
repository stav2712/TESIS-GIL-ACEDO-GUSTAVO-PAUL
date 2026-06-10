from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Any

from pymongo import MongoClient


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "nl2sql_logs")
REPORTS_COLLECTION = os.getenv("MONGO_COLLECTION", "queries")
JOBS_COLLECTION = os.getenv("MONGO_QUERY_JOBS_COLLECTION", "query_jobs")

OUT_JSON = "audit_metrics_classified_summary.json"
OUT_CSV = "audit_metrics_classified_rows.csv"

DEV_USERS = {"admin", "tavo", "prueba", "1"}
TEST_PATTERNS = [
    r"\btest\b",
    r"\bprueba\b",
    r"\bhola\b",
    r"\basdasd\b",
    r"\bxd\b",
    r"\bjaja\b",
    r"\binsulto\b",
    r"\bidiota\b",
    r"\bestupido\b",
    r"\bestúpido\b",
]


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": round(mean(values), 2) if values else None,
        "median": round(median(values), 2) if values else None,
        "p50": round(percentile(values, 0.50), 2) if values else None,
        "p90": round(percentile(values, 0.90), 2) if values else None,
        "p95": round(percentile(values, 0.95), 2) if values else None,
        "p99": round(percentile(values, 0.99), 2) if values else None,
        "min": round(min(values), 2) if values else None,
        "max": round(max(values), 2) if values else None,
    }


def job_latency_ms(job: dict[str, Any]) -> int | None:
    start = parse_dt(job.get("started_at") or job.get("created_at"))
    end = parse_dt(job.get("finished_at") or job.get("updated_at"))
    if not start or not end:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def clean_text(value: Any, max_len: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]


def sql_tables(sql: str) -> list[str]:
    pattern = r"\breporting\.[a-zA-Z_][a-zA-Z0-9_]*\b"
    return sorted(set(re.findall(pattern, sql or "", flags=re.IGNORECASE)))


def has_test_pattern(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(p, lower, flags=re.IGNORECASE) for p in TEST_PATTERNS)


def classify_row(row: dict[str, Any]) -> tuple[str, str]:
    status = str(row.get("status") or "").lower()
    error = str(row.get("error") or "").lower()
    nl = str(row.get("nl") or "").lower()
    username = str(row.get("username") or "").lower()
    latency = row.get("latency_ms")

    if username in DEV_USERS or has_test_pattern(nl):
        return "desarrollo_pruebas", "Usuario o consulta identificada como prueba/desarrollo"

    if status == "completed":
        if isinstance(latency, (int, float)) and latency > 30000:
            return "reporte_completado_outlier_latencia", "Reporte generado, pero supera 30 s de latencia total"
        return "reporte_completado_valido", "Reporte generado correctamente"

    if "no corresponde" in error or "consulta válida" in error or "clasificador" in error:
        return "bloqueado_por_validacion", "Consulta detenida por validación de entrada"

    if "motor" in error or "translator" in error or "translate" in error or "translation" in error or "modal" in error:
        return "error_traductor_modelo", "Falla asociada al servicio de traducción NL-to-SQL"

    if "sql" in error or "postgres" in error or "psycopg" in error or "database" in error or "execute" in error:
        return "error_sql_bd", "Falla asociada a ejecución SQL o base de datos"

    if "timeout" in error or "connection" in error or "conex" in error or "503" in error or "500" in error:
        return "error_infraestructura", "Falla asociada a tiempo de espera o servicio no disponible"

    if status in {"failed", "abandoned"}:
        return "no_completado_no_clasificado", "Intento no completado sin categoría específica"

    return "otro", "Registro fuera de categorías principales"


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    db = client[MONGO_DB]

    reports = list(db[REPORTS_COLLECTION].find({}, {"_id": 0}))
    jobs = list(db[JOBS_COLLECTION].find({}, {"_id": 0}))

    rows: list[dict[str, Any]] = []

    for r in reports:
        meta = r.get("meta") or {}
        row = {
            "source": "queries",
            "status": "completed",
            "report_id": r.get("report_id"),
            "conversation_id": r.get("conversation_id"),
            "user_id": r.get("user_id"),
            "username": r.get("username"),
            "profile": r.get("profile"),
            "nl": clean_text(r.get("nl"), 500),
            "sql": clean_text(r.get("sql"), 1000),
            "timestamp": r.get("timestamp"),
            "latency_ms": r.get("latency_ms"),
            "translator_latency_ms": meta.get("translator_latency_ms"),
            "feedback": r.get("feedback"),
            "error": "",
            "tables": ", ".join(sql_tables(r.get("sql") or "")),
        }
        row["categoria"], row["criterio"] = classify_row(row)
        rows.append(row)

    for j in jobs:
        status = str(j.get("status") or "").lower()
        if status == "completed":
            continue

        row = {
            "source": "query_jobs",
            "status": status or "failed",
            "report_id": f"job:{j.get('job_id')}",
            "conversation_id": j.get("conversation_id"),
            "user_id": j.get("user_id"),
            "username": j.get("username"),
            "profile": j.get("profile"),
            "nl": clean_text(j.get("nl"), 500),
            "sql": "",
            "timestamp": j.get("finished_at") or j.get("updated_at") or j.get("created_at"),
            "latency_ms": job_latency_ms(j),
            "translator_latency_ms": None,
            "feedback": "",
            "error": clean_text(j.get("error"), 1000),
            "tables": "",
        }
        row["categoria"], row["criterio"] = classify_row(row)
        rows.append(row)

    by_category = Counter(r["categoria"] for r in rows)

    valid_completed = [r for r in rows if r["categoria"] == "reporte_completado_valido"]
    completed_all = [r for r in rows if r["status"] == "completed"]
    feedbacked = [r for r in completed_all if r.get("feedback") in {"positive", "negative"}]

    total_latencies = [
        float(r["latency_ms"]) for r in valid_completed
        if isinstance(r.get("latency_ms"), (int, float))
    ]
    translator_latencies = [
        float(r["translator_latency_ms"]) for r in valid_completed
        if isinstance(r.get("translator_latency_ms"), (int, float))
    ]

    feedback_counter = Counter(str(r.get("feedback") or "sin_feedback") for r in completed_all)
    feedbacked_counter = Counter(str(r.get("feedback")) for r in feedbacked)

    summary = {
        "totales_originales": {
            "registros": len(rows),
            "reportes_completados": len(completed_all),
            "intentos_no_completados": len(rows) - len(completed_all),
        },
        "clasificacion": dict(by_category),
        "muestra_recomendada_para_informe": {
            "criterio": "Solo reportes completados válidos, excluyendo pruebas de desarrollo y outliers > 30s de latencia total",
            "n": len(valid_completed),
        },
        "latencia_total_ms_muestra_recomendada": stats(total_latencies),
        "latencia_traductor_ms_muestra_recomendada": stats(translator_latencies),
        "feedback_reportes_completados": dict(feedback_counter),
        "feedback_solo_valorados": dict(feedbacked_counter),
        "interpretacion": (
            "La auditoría completa no debe usarse como tasa de precisión del modelo. "
            "Debe reportarse como trazabilidad operativa. Para EM y EX se requiere un conjunto de prueba "
            "con SQL esperado o resultado esperado."
        ),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "source", "status", "categoria", "criterio", "report_id", "conversation_id",
            "user_id", "username", "profile", "nl", "sql", "timestamp", "latency_ms",
            "translator_latency_ms", "feedback", "error", "tables",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"\nArchivos generados: {OUT_JSON} y {OUT_CSV}")


if __name__ == "__main__":
    main()
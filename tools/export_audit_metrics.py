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

OUT_JSON = "audit_metrics_summary.json"
OUT_CSV = "audit_metrics_rows.csv"


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


def job_latency_ms(job: dict[str, Any]) -> int | None:
    start = parse_dt(job.get("started_at") or job.get("created_at"))
    end = parse_dt(job.get("finished_at") or job.get("updated_at"))
    if not start or not end:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def sql_tables(sql: str) -> list[str]:
    if not sql:
        return []
    pattern = r"\breporting\.[a-zA-Z_][a-zA-Z0-9_]*\b"
    return sorted(set(re.findall(pattern, sql, flags=re.IGNORECASE)))


def clean_text(value: Any, max_len: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")

    db = client[MONGO_DB]
    reports_col = db[REPORTS_COLLECTION]
    jobs_col = db[JOBS_COLLECTION]

    reports = list(reports_col.find({}, {"_id": 0}))
    jobs = list(jobs_col.find({}, {"_id": 0}))

    completed_rows: list[dict[str, Any]] = []
    for r in reports:
        completed_rows.append({
            "tipo": "completed",
            "report_id": r.get("report_id"),
            "conversation_id": r.get("conversation_id"),
            "user_id": r.get("user_id"),
            "username": r.get("username"),
            "profile": r.get("profile"),
            "nl": clean_text(r.get("nl")),
            "sql": clean_text(r.get("sql"), 500),
            "timestamp": r.get("timestamp"),
            "latency_ms": r.get("latency_ms"),
            "feedback": r.get("feedback"),
            "error": "",
            "translator_strategy": r.get("translator_strategy"),
            "tables": ", ".join(sql_tables(r.get("sql") or "")),
        })

    failed_rows: list[dict[str, Any]] = []
    for j in jobs:
        status = str(j.get("status") or "").lower()
        if status in {"completed", "done", "success"}:
            continue

        failed_rows.append({
            "tipo": status or "failed",
            "report_id": f"job:{j.get('job_id')}",
            "conversation_id": j.get("conversation_id"),
            "user_id": j.get("user_id"),
            "username": j.get("username"),
            "profile": j.get("profile"),
            "nl": clean_text(j.get("nl")),
            "sql": "",
            "timestamp": j.get("finished_at") or j.get("updated_at") or j.get("created_at"),
            "latency_ms": job_latency_ms(j),
            "feedback": "",
            "error": clean_text(j.get("error"), 500),
            "translator_strategy": "",
            "tables": "",
        })

    all_rows = completed_rows + failed_rows

    latencies = [
        float(r["latency_ms"])
        for r in completed_rows
        if isinstance(r.get("latency_ms"), (int, float)) and r.get("latency_ms") >= 0
    ]

    by_status = Counter(r["tipo"] for r in all_rows)
    by_feedback = Counter(str(r.get("feedback") or "sin_feedback") for r in completed_rows)
    by_user = Counter(str(r.get("username") or r.get("user_id") or "sin_usuario") for r in all_rows)

    table_counter = Counter()
    for r in completed_rows:
        for t in [x.strip() for x in str(r.get("tables") or "").split(",") if x.strip()]:
            table_counter[t] += 1

    by_day = defaultdict(lambda: Counter())
    for r in all_rows:
        dt = parse_dt(r.get("timestamp"))
        key = dt.date().isoformat() if dt else "sin_fecha"
        by_day[key][r["tipo"]] += 1

    summary = {
        "fuente": {
            "mongo_uri": MONGO_URI,
            "database": MONGO_DB,
            "reports_collection": REPORTS_COLLECTION,
            "jobs_collection": JOBS_COLLECTION,
        },
        "totales": {
            "intentos_registrados": len(all_rows),
            "reportes_completados": len(completed_rows),
            "intentos_no_completados": len(failed_rows),
            "por_estado": dict(by_status),
        },
        "latencia_reportes_completados_ms": {
            "count": len(latencies),
            "mean": round(mean(latencies), 2) if latencies else None,
            "median": round(median(latencies), 2) if latencies else None,
            "p50": round(percentile(latencies, 0.50), 2) if latencies else None,
            "p90": round(percentile(latencies, 0.90), 2) if latencies else None,
            "p95": round(percentile(latencies, 0.95), 2) if latencies else None,
            "p99": round(percentile(latencies, 0.99), 2) if latencies else None,
            "min": round(min(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "feedback": dict(by_feedback),
        "usuarios": dict(by_user.most_common()),
        "vistas_reporting_mas_usadas": dict(table_counter.most_common()),
        "actividad_por_dia": {day: dict(counter) for day, counter in sorted(by_day.items())},
        "nota": (
            "Estas métricas son operativas y provienen de auditoría. "
            "No calculan Exact Match ni Execution Accuracy porque para ello se requiere SQL esperado "
            "o resultado esperado por consulta."
        ),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "tipo", "report_id", "conversation_id", "user_id", "username", "profile",
            "nl", "sql", "timestamp", "latency_ms", "feedback", "error",
            "translator_strategy", "tables",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"\nArchivos generados: {OUT_JSON} y {OUT_CSV}")


if __name__ == "__main__":
    main()
from __future__ import annotations

import re
from datetime import datetime, timezone
from math import ceil
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import settings

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_title(nl: str) -> str:
    text = CONTROL_CHARS_RE.sub(" ", nl or "")
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:40] + "…") if len(text) > 40 else (text or "Nuevo reporte")


def _without_id(doc: dict | None) -> dict | None:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


class MongoRepo:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        self.client.admin.command("ping")
        db = self.client[settings.MONGO_DB]
        self.reports = db[settings.MONGO_COLLECTION]
        self.convs = db[settings.MONGO_CONVERSATIONS_COLLECTION]
        self.query_jobs = db[getattr(settings, "MONGO_QUERY_JOBS_COLLECTION", "query_jobs")]

        self.reports.create_index([("report_id", ASCENDING)], unique=True)
        self.reports.create_index(
            [("user_id", ASCENDING), ("conversation_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.reports.create_index([("timestamp", DESCENDING)])
        self.reports.create_index([("username", ASCENDING)])
        self.reports.create_index([("full_name", ASCENDING)])
        self.reports.create_index([("nl", "text")])

        self.convs.create_index([("conversation_id", ASCENDING)], unique=True)
        self.convs.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])

        self.query_jobs.create_index([("job_id", ASCENDING)], unique=True)
        self.query_jobs.create_index([("user_id", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)])
        self.query_jobs.create_index([("conversation_id", ASCENDING), ("updated_at", DESCENDING)])

    # ---------- Conversaciones ----------
    def create_conversation(self, user_id: int, title: str | None) -> dict:
        cid = str(uuid4())
        ts = now_iso()
        doc = {
            "conversation_id": cid,
            "user_id": user_id,
            "title": title or "Nuevo reporte",
            "created_at": ts,
            "updated_at": ts,
            "deleted": False,
            "deleted_at": None,
            "selected_report_id": None,
            "last_preview": None,
        }
        self.convs.insert_one(doc)
        return _without_id(doc) or {}

    def list_conversations(self, user_id: int) -> list[dict]:
        cur = self.convs.find({"user_id": user_id, "deleted": False}, {"_id": 0}).sort(
            "updated_at", DESCENDING
        )
        return list(cur)

    def get_conversation(self, user_id: int, conversation_id: str, can_access_all: bool = False) -> dict | None:
        criteria: dict[str, Any] = {"conversation_id": conversation_id, "deleted": False}
        if not can_access_all:
            criteria["user_id"] = user_id
        return self.convs.find_one(criteria, {"_id": 0})

    def rename_conversation(self, user_id: int, conversation_id: str, title: str) -> bool:
        res = self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"title": title, "updated_at": now_iso()}},
        )
        # matched_count evita falso error si el usuario guarda el mismo título.
        return res.matched_count == 1

    def delete_conversation(self, user_id: int, conversation_id: str) -> bool:
        ts = now_iso()
        res = self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"deleted": True, "deleted_at": ts, "updated_at": ts}},
        )
        if res.matched_count != 1:
            return False

        # No se borran reportes por auditoría, pero se desasocian jobs activos de la UI.
        self.query_jobs.update_many(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "status": {"$in": ["queued", "running"]},
            },
            {
                "$set": {
                    "status": "abandoned",
                    "updated_at": ts,
                    "error": "La conversación fue eliminada por el usuario",
                }
            },
        )
        return True

    def select_report(self, user_id: int, conversation_id: str, report_id: str) -> bool:
        ok = self.reports.find_one(
            {"user_id": user_id, "conversation_id": conversation_id, "report_id": report_id},
            {"_id": 0, "report_id": 1},
        )
        if not ok:
            return False
        res = self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"selected_report_id": report_id, "updated_at": now_iso()}},
        )
        # matched_count evita falso error si ya estaba seleccionado.
        return res.matched_count == 1

    # ---------- Reportes ----------
    def add_report(
        self,
        user_id: int,
        conversation_id: str,
        nl: str,
        sql: str,
        latency_ms: int,
        meta: dict | None = None,
        user_snapshot: dict | None = None,
    ) -> dict:
        rid = str(uuid4())
        ts = now_iso()
        doc = {
            "report_id": rid,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "username": (user_snapshot or {}).get("username"),
            "full_name": (user_snapshot or {}).get("full_name"),
            "profile": (user_snapshot or {}).get("profile"),
            "nl": nl,
            "sql": sql,
            "timestamp": ts,
            "latency_ms": latency_ms,
            "feedback": None,
            "meta": meta or {},
        }
        self.reports.insert_one(doc)

        preview = default_title(nl)
        self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"updated_at": ts, "last_preview": preview}},
        )

        conv = self.convs.find_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"_id": 0},
        )
        if conv and not conv.get("selected_report_id"):
            self.convs.update_one(
                {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
                {"$set": {"selected_report_id": rid}},
            )
        return _without_id(doc) or {}

    def list_reports(self, user_id: int, conversation_id: str, can_access_all: bool = False) -> list[dict]:
        criteria: dict[str, Any] = {"conversation_id": conversation_id}
        if not can_access_all:
            criteria["user_id"] = user_id
        cur = self.reports.find(criteria, {"_id": 0}).sort("timestamp", ASCENDING)
        return list(cur)

    def get_report(self, user_id: int, report_id: str, can_access_all: bool = False) -> dict | None:
        criteria: dict[str, Any] = {"report_id": report_id}
        if not can_access_all:
            criteria["user_id"] = user_id
        return self.reports.find_one(criteria, {"_id": 0})

    def set_feedback(self, user_id: int, report_id: str, value: str) -> bool:
        if value not in ("up", "down"):
            return False
        fb = "positive" if value == "up" else "negative"
        res = self.reports.update_one(
            {"user_id": user_id, "report_id": report_id},
            {"$set": {"feedback": fb}},
        )
        # matched_count evita falso error si el feedback ya tenía ese valor.
        return res.matched_count == 1

    # ---------- Trabajos de generación ----------
    def create_query_job(
        self,
        *,
        user_id: int,
        username: str | None,
        conversation_id: str,
        nl: str,
        page: int,
        page_size: int,
    ) -> dict:
        jid = str(uuid4())
        ts = now_iso()
        doc = {
            "job_id": jid,
            "user_id": user_id,
            "username": username,
            "conversation_id": conversation_id,
            "nl": nl,
            "page": page,
            "page_size": page_size,
            "status": "queued",
            "report_id": None,
            "error": None,
            "result": None,
            "created_at": ts,
            "updated_at": ts,
            "finished_at": None,
        }
        self.query_jobs.insert_one(doc)
        return _without_id(doc) or {}

    def get_query_job(self, user_id: int, job_id: str, can_access_all: bool = False) -> dict | None:
        criteria: dict[str, Any] = {"job_id": job_id}
        if not can_access_all:
            criteria["user_id"] = user_id
        return self.query_jobs.find_one(criteria, {"_id": 0})

    def list_active_query_jobs(self, user_id: int) -> list[dict]:
        cur = self.query_jobs.find(
            {"user_id": user_id, "status": {"$in": ["queued", "running"]}},
            {"_id": 0},
        ).sort("updated_at", DESCENDING)
        return list(cur)

    def mark_query_job_running(self, user_id: int, job_id: str) -> bool:
        res = self.query_jobs.update_one(
            {"user_id": user_id, "job_id": job_id, "status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "running", "updated_at": now_iso(), "error": None}},
        )
        return res.matched_count == 1

    def finish_query_job(self, user_id: int, job_id: str, result: dict) -> bool:
        ts = now_iso()
        res = self.query_jobs.update_one(
            {"user_id": user_id, "job_id": job_id, "status": {"$ne": "abandoned"}},
            {
                "$set": {
                    "status": "completed",
                    "report_id": result.get("report_id"),
                    "result": result,
                    "error": None,
                    "updated_at": ts,
                    "finished_at": ts,
                }
            },
        )
        return res.matched_count == 1

    def fail_query_job(self, user_id: int, job_id: str, error: str) -> bool:
        ts = now_iso()
        res = self.query_jobs.update_one(
            {"user_id": user_id, "job_id": job_id, "status": {"$ne": "abandoned"}},
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "updated_at": ts,
                    "finished_at": ts,
                }
            },
        )
        return res.matched_count == 1

    # ---------- Auditoría / administración ----------
    def dashboard_summary(self) -> dict:
        total_reports = self.reports.count_documents({})
        total_conversations = self.convs.count_documents({"deleted": False})
        users = self.reports.distinct("user_id")
        positive = self.reports.count_documents({"feedback": "positive"})
        negative = self.reports.count_documents({"feedback": "negative"})
        latest = list(self.reports.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(8))
        pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "reports": {"$sum": 1},
                    "last_at": {"$max": "$timestamp"},
                    "username": {"$last": "$username"},
                }
            },
            {"$sort": {"reports": -1}},
            {"$limit": 8},
        ]
        top_users = list(self.reports.aggregate(pipeline))
        return {
            "total_reports": total_reports,
            "total_conversations": total_conversations,
            "unique_users": len(users),
            "feedback_positive": positive,
            "feedback_negative": negative,
            "latest_reports": latest,
            "top_users": [
                {
                    "user_id": x.get("_id"),
                    "username": x.get("username"),
                    "reports": x.get("reports", 0),
                    "last_at": x.get("last_at"),
                }
                for x in top_users
            ],
        }

    def list_audit_reports(
        self,
        page: int,
        page_size: int,
        user_id: int | None = None,
        q: str | None = None,
    ) -> dict:
        criteria: dict[str, Any] = {}
        if user_id is not None:
            criteria["user_id"] = user_id
        if q:
            text = CONTROL_CHARS_RE.sub(" ", q.strip())
            text = re.sub(r"\s+", " ", text).strip()[:120]
            if text:
                # Literal search: evita que caracteres como [, (, *, ? rompan Mongo regex
                # o conviertan la búsqueda de auditoría en una expresión costosa.
                rx = {"$regex": re.escape(text), "$options": "i"}
                criteria["$or"] = [
                    {"nl": rx},
                    {"username": rx},
                    {"full_name": rx},
                    {"profile": rx},
                ]
                if text.isdigit():
                    criteria["$or"].append({"user_id": int(text)})

        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        total = self.reports.count_documents(criteria)
        total_pages = max(ceil(total / page_size), 1)
        cur = (
            self.reports.find(criteria, {"_id": 0})
            .sort("timestamp", DESCENDING)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "rows": list(cur),
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

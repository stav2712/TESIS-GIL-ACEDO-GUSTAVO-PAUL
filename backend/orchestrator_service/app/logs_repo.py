from datetime import datetime, timezone
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import settings

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def default_title(nl: str) -> str:
    t = nl.strip()
    return (t[:40] + "…") if len(t) > 40 else (t or "Nuevo reporte")

class MongoRepo:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        self.client.admin.command("ping")
        db = self.client[settings.MONGO_DB]
        self.reports = db[settings.MONGO_COLLECTION]
        self.convs = db[settings.MONGO_CONVERSATIONS_COLLECTION]
        self.reports.create_index([("report_id", ASCENDING)], unique=True)
        self.reports.create_index([("user_id", ASCENDING), ("conversation_id", ASCENDING), ("timestamp", ASCENDING)])
        self.convs.create_index([("conversation_id", ASCENDING)], unique=True)
        self.convs.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])

    def create_conversation(self, user_id: int, title: str | None) -> dict:
        cid = str(uuid4())
        doc = {
            "conversation_id": cid,
            "user_id": user_id,
            "title": title or "Nuevo reporte",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "deleted": False,
            "deleted_at": None,
            "selected_report_id": None,
            "last_preview": None,
        }
        self.convs.insert_one(doc)
        return {k: doc[k] for k in doc if k != "_id"}

    def list_conversations(self, user_id: int) -> list[dict]:
        cur = self.convs.find({"user_id": user_id, "deleted": False}, {"_id": 0}).sort("updated_at", DESCENDING)
        return list(cur)

    def get_conversation(self, user_id: int, conversation_id: str) -> dict | None:
        return self.convs.find_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"_id": 0},
        )

    def rename_conversation(self, user_id: int, conversation_id: str, title: str) -> bool:
        res = self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"title": title, "updated_at": now_iso()}},
        )
        return res.modified_count == 1

    def delete_conversation(self, user_id: int, conversation_id: str) -> bool:
        res = self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"deleted": True, "deleted_at": now_iso()}},
        )
        return res.modified_count == 1

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
        return res.modified_count == 1

    def add_report(
        self,
        user_id: int,
        conversation_id: str,
        nl: str,
        sql: str,
        latency_ms: int,
        *,
        nl_normalized: str | None = None,
        schema_profile: str | None = None,
        resolved_terms: list[dict] | None = None,
        resolved_values: list[dict] | None = None,
        translator_strategy: str | None = None,
    ) -> dict:
        rid = str(uuid4())
        ts = now_iso()
        doc = {
            "report_id": rid,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "nl": nl,
            "nl_normalized": nl_normalized,
            "schema_profile": schema_profile,
            "resolved_terms": resolved_terms or [],
            "resolved_values": resolved_values or [],
            "translator_strategy": translator_strategy,
            "sql": sql,
            "timestamp": ts,
            "latency_ms": latency_ms,
            "feedback": None,
        }
        self.reports.insert_one(doc)

        preview = default_title(nl)
        self.convs.update_one(
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": False},
            {"$set": {"updated_at": ts, "last_preview": preview}},
        )
        conv = self.convs.find_one({"user_id": user_id, "conversation_id": conversation_id}, {"_id": 0})
        if conv and not conv.get("selected_report_id"):
            self.convs.update_one(
                {"user_id": user_id, "conversation_id": conversation_id},
                {"$set": {"selected_report_id": rid}},
            )
        return {k: doc[k] for k in doc if k != "_id"}

    def list_reports(self, user_id: int, conversation_id: str) -> list[dict]:
        cur = self.reports.find(
            {"user_id": user_id, "conversation_id": conversation_id},
            {"_id": 0},
        ).sort("timestamp", ASCENDING)
        return list(cur)

    def get_report(self, user_id: int, report_id: str) -> dict | None:
        return self.reports.find_one(
            {"user_id": user_id, "report_id": report_id},
            {"_id": 0},
        )

    def set_feedback(self, user_id: int, report_id: str, value: str) -> bool:
        if value not in ("up", "down"):
            return False
        fb = "positive" if value == "up" else "negative"
        res = self.reports.update_one(
            {"user_id": user_id, "report_id": report_id},
            {"$set": {"feedback": fb}},
        )
        return res.modified_count == 1
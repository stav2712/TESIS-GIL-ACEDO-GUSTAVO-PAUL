from __future__ import annotations 
 
import re 
from datetime import datetime, timezone 
from math import ceil 
from typing import Any 
from uuid import uuid4 
 
from pymongo import ASCENDING, DESCENDING, MongoClient 
 
from .config import settings 
from .report_title import clean_report_title, fallback_report_title, legacy_truncated_title 
 
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]") 
 
 
def now_iso() -> str: 
    return datetime.now(timezone.utc).isoformat() 
 
 
def default_title(nl: str) -> str: 
    # Compatibilidad: conserva el nombre público usado por el resto del sistema,
    # pero ya no guarda la pregunta truncada. Ahora devuelve un título de reporte.
    return clean_report_title(fallback_report_title(nl)) 
 
 
def _without_id(doc: dict | None) -> dict | None: 
    if not doc: 
        return None 

    return {k: v for k, v in doc.items() if k != "_id"} 
 
 
def _parse_iso(value: str | None) -> datetime | None: 
    if not value: 
        return None 
    try: 
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) 
    except Exception: 
        return None 
 
 
def _job_latency_ms(job: dict[str, Any]) -> int: 
    start = _parse_iso(job.get("created_at")) 
    end = _parse_iso(job.get("finished_at") or job.get("updated_at")) 
    if not start or not end: 
        return 0 
    return max(int((end - start).total_seconds() * 1000), 0) 
 
 
def _safe_search_text(q: str | None) -> str: 
    text = CONTROL_CHARS_RE.sub(" ", (q or "").strip()) 
    return re.sub(r"\s+", " ", text).strip()[:120] 
 
 
def _clean_identity_text(value: Any) -> str | None: 
    text = CONTROL_CHARS_RE.sub(" ", str(value or "")) 
    text = re.sub(r"\s+", " ", text).strip() 
    return text or None 
 
 
def _default_identity_for_username(username: str | None) -> dict[str, str | None]: 
    # Compatibilidad con registros antiguos de query_jobs creados antes de 
    # guardar el snapshot completo. No inventa datos para usuarios normales; 
    # solo cubre el administrador semilla del sistema. 
    if (username or "").strip().lower() == "admin": 
        return {"username": "admin", "full_name": "Administrador", "profile": "admin"} 
    return {"username": username, "full_name": None, "profile": None} 
 
 
class MongoRepo: 
    def __init__(self): 
        self.client = MongoClient(settings.MONGO_URI, 
serverSelectionTimeoutMS=2000) 
        self.client.admin.command("ping") 
        db = self.client[settings.MONGO_DB] 
        self.reports = db[settings.MONGO_COLLECTION] 
        self.convs = db[settings.MONGO_CONVERSATIONS_COLLECTION] 
        self.query_jobs = db[getattr(settings, "MONGO_QUERY_JOBS_COLLECTION", 
"query_jobs")] 
 
        self.reports.create_index([("report_id", ASCENDING)], unique=True) 
        self.reports.create_index( 
            [("user_id", ASCENDING), ("conversation_id", ASCENDING), 
("timestamp", ASCENDING)] 
        ) 
        self.reports.create_index([("timestamp", DESCENDING)]) 
        self.reports.create_index([("username", ASCENDING)]) 
        self.reports.create_index([("full_name", ASCENDING)]) 
        self.reports.create_index([("nl", "text")]) 
 
        self.convs.create_index([("conversation_id", ASCENDING)], unique=True) 
        self.convs.create_index([("user_id", ASCENDING), ("updated_at", 
DESCENDING)]) 
 
        self.query_jobs.create_index([("job_id", ASCENDING)], unique=True) 
        self.query_jobs.create_index([("user_id", ASCENDING), ("status", 
ASCENDING), ("updated_at", DESCENDING)]) 
        self.query_jobs.create_index([("conversation_id", ASCENDING), 
("updated_at", DESCENDING)]) 

        self.query_jobs.create_index([("finished_at", DESCENDING)]) 
 
    # ---------- Conversaciones ---------- 
    def create_conversation(self, user_id: int, title: str | None) -> dict: 
        cid = str(uuid4()) 
        ts = now_iso() 
        clean_title = clean_report_title(title) 
        doc = { 
            "conversation_id": cid, 
            "user_id": user_id, 
            "title": clean_title, 
            "title_source": "auto" if clean_title != "Nuevo reporte" else "system", 
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
        cur = self.convs.find({"user_id": user_id, "deleted": False}, {"_id": 
0}).sort( 
            "updated_at", DESCENDING 
        ) 
        return list(cur) 
 
    def get_conversation(self, user_id: int, conversation_id: str, 
can_access_all: bool = False) -> dict | None: 
        criteria: dict[str, Any] = {"conversation_id": conversation_id, 
"deleted": False} 
        if not can_access_all: 
            criteria["user_id"] = user_id 
        return self.convs.find_one(criteria, {"_id": 0}) 
 
    def rename_conversation(self, user_id: int, conversation_id: str, title: 
str) -> bool: 
        clean_title = clean_report_title(title) 
        res = self.convs.update_one( 
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": 
False}, 
            {"$set": {"title": clean_title, "title_source": "manual", "updated_at": now_iso()}}, 
        ) 
        # matched_count evita falso error si el usuario guarda el mismo título. 
        return res.matched_count == 1 
 
    def delete_conversation(self, user_id: int, conversation_id: str) -> bool: 
        ts = now_iso() 
        res = self.convs.update_one( 
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": 
False}, 
            {"$set": {"deleted": True, "deleted_at": ts, "updated_at": ts}}, 
        ) 
        if res.matched_count != 1: 
            return False 
 

        # No se borran reportes por auditoría, pero se desasocian jobs activos 
        # de la UI.
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
                    "finished_at": ts, 
                    "error": "La conversación fue eliminada por el usuario", 
                } 
            }, 
        ) 
        return True 
 
    def select_report(self, user_id: int, conversation_id: str, report_id: str) -> bool:
        ok = self.reports.find_one( 
            {"user_id": user_id, "conversation_id": conversation_id, 
"report_id": report_id}, 
            {"_id": 0, "report_id": 1}, 
        ) 
        if not ok: 
            return False 
        res = self.convs.update_one( 
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": 
False}, 
            {"$set": {"selected_report_id": report_id, "updated_at": 
now_iso()}}, 
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
        report_title: str | None = None, 
    ) -> dict: 
        rid = str(uuid4()) 
        ts = now_iso() 
        clean_title = clean_report_title(report_title or default_title(nl)) 
        doc = { 
            "report_id": rid, 
            "conversation_id": conversation_id, 
            "user_id": user_id, 
            "username": (user_snapshot or {}).get("username"), 

            "full_name": (user_snapshot or {}).get("full_name"), 
            "profile": (user_snapshot or {}).get("profile"), 
            "nl": nl, 
            "report_title": clean_title, 
            "sql": sql, 
            "timestamp": ts, 
            "latency_ms": latency_ms, 
            "feedback": None, 
            "meta": meta or {}, 
        } 
        self.reports.insert_one(doc) 
 
        preview = clean_title 
        conv = self.convs.find_one( 
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": 
False}, 
            {"_id": 0}, 
        ) 
 
        update_fields: dict[str, Any] = {"updated_at": ts, "last_preview": preview} 
        if conv and self._should_replace_auto_title(conv, nl): 
            update_fields["title"] = preview 
            update_fields["title_source"] = "auto" 
 
        self.convs.update_one( 
            {"user_id": user_id, "conversation_id": conversation_id, "deleted": 
False}, 
            {"$set": update_fields}, 
        ) 
 
        if conv and not conv.get("selected_report_id"): 
            self.convs.update_one( 
                {"user_id": user_id, "conversation_id": conversation_id, 
"deleted": False}, 
                {"$set": {"selected_report_id": rid}}, 
            ) 
        return _without_id(doc) or {} 
 
    def _should_replace_auto_title(self, conv: dict[str, Any], nl: str) -> bool: 
        current = clean_report_title(str(conv.get("title") or "")) 
        title_source = str(conv.get("title_source") or "").strip().lower() 
        if title_source == "manual": 
            return False 
        if not current or current == "Nuevo reporte": 
            return True 
        if current == clean_report_title(legacy_truncated_title(nl)):
            return True 
        if current.endswith("…") or "..." in current:
            return True 
        return False 
 
    def list_reports(self, user_id: int, conversation_id: str, can_access_all: 
bool = False) -> list[dict]: 
        criteria: dict[str, Any] = {"conversation_id": conversation_id} 
        if not can_access_all: 
            criteria["user_id"] = user_id 
        cur = self.reports.find(criteria, {"_id": 0}).sort("timestamp", 
ASCENDING) 
        return list(cur) 
 
    def get_report(self, user_id: int, report_id: str, can_access_all: bool = 
False) -> dict | None: 
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
        full_name: str | None = None, 
        profile: str | None = None, 
        report_title: str | None = None, 
    ) -> dict: 
        jid = str(uuid4()) 
        ts = now_iso() 
        doc = { 
            "job_id": jid, 
            "user_id": user_id, 
            "username": username, 
            "full_name": full_name, 
            "profile": profile, 
            "conversation_id": conversation_id, 
            "nl": nl, 
            "report_title": clean_report_title(report_title or default_title(nl)), 
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
 
    def get_query_job(self, user_id: int, job_id: str, can_access_all: bool = 
False) -> dict | None: 
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

            {"user_id": user_id, "job_id": job_id, "status": {"$in": ["queued", 
"running"]}}, 
            {"$set": {"status": "running", "updated_at": now_iso(), "error": 
None}}, 
        ) 
        return res.matched_count == 1 
 
    def finish_query_job(self, user_id: int, job_id: str, result: dict) -> bool:
        ts = now_iso() 
        res = self.query_jobs.update_one( 
            {"user_id": user_id, "job_id": job_id, "status": {"$ne": 
"abandoned"}}, 
            { 
                "$set": { 
                    "status": "completed", 
                    "report_id": result.get("report_id"), 
                    "report_title": result.get("report_title"), 
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
            {"user_id": user_id, "job_id": job_id, "status": {"$ne": 
"abandoned"}}, 
            { 
                "$set": { 
                    "status": "failed", 
                    "error": str(error or "Error al generar reporte")[:4000], 
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
        latest = list(self.reports.find({}, {"_id": 0}).sort("timestamp", 
DESCENDING).limit(8)) 
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
 
    def _audit_search_criteria(self, *, user_id: int | None, q: str | None, 
include_errors: bool) -> dict[str, Any]: 
        criteria: dict[str, Any] = {} 
        if include_errors: 
            criteria["status"] = {"$in": ["failed", "abandoned"]} 
        if user_id is not None: 
            criteria["user_id"] = user_id 
 
        text = _safe_search_text(q) 
        if text: 
            rx = {"$regex": re.escape(text), "$options": "i"} 
            fields = ["nl", "username", "full_name", "profile"] 
            if include_errors: 
                fields.append("error") 
            criteria["$or"] = [{field: rx} for field in fields] 
            if text.isdigit(): 
                criteria["$or"].append({"user_id": int(text)}) 
        return criteria 
 
    def _audit_row_from_report(self, doc: dict[str, Any]) -> dict[str, Any]: 
        return { 
            "report_id": doc.get("report_id"), 
            "conversation_id": doc.get("conversation_id"), 
            "user_id": doc.get("user_id"), 
            "username": doc.get("username"), 
            "full_name": doc.get("full_name"), 
            "profile": doc.get("profile"), 
            "nl": doc.get("nl") or "", 
            "sql": doc.get("sql") or "", 
            "timestamp": doc.get("timestamp"), 
            "latency_ms": int(doc.get("latency_ms") or 0), 
            "feedback": doc.get("feedback"), 
            "status": "completed", 
            "error": None, 
        } 
 
    def _audit_identity_from_doc(self, doc: dict[str, Any]) -> dict[str, str | None]: 
        username = _clean_identity_text(doc.get("username")) 
        return { 
            "username": username, 
            "full_name": _clean_identity_text(doc.get("full_name")), 
            "profile": _clean_identity_text(doc.get("profile")), 
        } 
 
    def _audit_identity_index( 
        self, 
        report_docs: list[dict[str, Any]], 
        job_docs: list[dict[str, Any]], 
    ) -> tuple[dict[int, dict[str, str | None]], dict[str, dict[str, str | None]]]: 
        # Los reportes exitosos ya tenían snapshot completo del usuario. Se usan 
        # también para enriquecer trabajos fallidos históricos que quedaron con 
        # username pero sin full_name/profile. 
        identity_docs: list[dict[str, Any]] = list(report_docs) 
        user_ids = { 
            int(job["user_id"]) 
            for job in job_docs 
            if job.get("user_id") is not None 
        } 
        if user_ids: 
            try: 
                identity_docs.extend( 
                    list( 
                        self.reports.find( 
                            {"user_id": {"$in": sorted(user_ids)}}, 
                            { 
                                "_id": 0, 
                                "user_id": 1, 
                                "username": 1, 
                                "full_name": 1, 
                                "profile": 1, 
                                "timestamp": 1, 
                            }, 
                        ).sort("timestamp", DESCENDING) 
                    ) 
                ) 
            except Exception: 
                # La auditoría no debe fallar si Mongo rechaza un lookup de 
                # enriquecimiento; en ese caso se muestran los datos del job. 
                pass 
 
        by_user_id: dict[int, dict[str, str | None]] = {} 
        by_username: dict[str, dict[str, str | None]] = {} 
        for doc in identity_docs: 
            identity = self._audit_identity_from_doc(doc) 
            has_useful_data = any( 
                identity.get(key) for key in ("username", "full_name", "profile") 
            ) 
            if not has_useful_data: 
                continue 
 
            raw_user_id = doc.get("user_id") 
            if raw_user_id is not None: 
                try: 
                    by_user_id.setdefault(int(raw_user_id), identity) 
                except Exception: 
                    pass 
 
            username = identity.get("username") 
            if username: 
                by_username.setdefault(username.lower(), identity) 
 
        return by_user_id, by_username 
 
    def _identity_for_failed_job( 
        self, 
        job: dict[str, Any], 
        by_user_id: dict[int, dict[str, str | None]], 
        by_username: dict[str, dict[str, str | None]], 
    ) -> dict[str, str | None]: 
        current = self._audit_identity_from_doc(job) 
        fallback: dict[str, str | None] = {} 
 
        raw_user_id = job.get("user_id") 
        if raw_user_id is not None: 
            try: 
                fallback = by_user_id.get(int(raw_user_id), {}) 
            except Exception: 
                fallback = {} 
 
        username = current.get("username") or fallback.get("username") 
        if not fallback and username: 
            fallback = by_username.get(username.lower(), {}) 
        if not fallback and username: 
            fallback = _default_identity_for_username(username) 
 
        return { 
            "username": current.get("username") or fallback.get("username"), 
            "full_name": current.get("full_name") or fallback.get("full_name"), 
            "profile": current.get("profile") or fallback.get("profile"), 
        } 
 
    def _audit_row_from_failed_job( 
        self, 
        job: dict[str, Any], 
        by_user_id: dict[int, dict[str, str | None]] | None = None, 
        by_username: dict[str, dict[str, str | None]] | None = None, 
    ) -> dict[str, Any]: 
        ts = job.get("finished_at") or job.get("updated_at") or job.get("created_at") 
        identity = self._identity_for_failed_job(job, by_user_id or {}, by_username or {}) 
        return { 
            "report_id": f"job:{job.get('job_id')}", 
            "conversation_id": job.get("conversation_id"), 
            "user_id": job.get("user_id"), 
            "username": identity.get("username"), 
            "full_name": identity.get("full_name"), 
            "profile": identity.get("profile"), 
            "nl": job.get("nl") or "", 
            "sql": "", 
            "timestamp": ts, 
            "latency_ms": _job_latency_ms(job), 
            "feedback": None, 
            "status": job.get("status") or "failed", 
            "error": job.get("error"), 
        } 
 
    def list_audit_reports( 
        self, 
        page: int, 
        page_size: int, 
        user_id: int | None = None, 
        q: str | None = None, 
    ) -> dict: 
        # Auditoría ahora muestra reportes exitosos y también intentos fallidos. 
        # Antes los errores quedaban solo en query_jobs y el auditor veía "sin log". 
        report_criteria = self._audit_search_criteria(user_id=user_id, q=q, include_errors=False) 
        job_criteria = self._audit_search_criteria(user_id=user_id, q=q, include_errors=True) 
 
        report_docs = list(self.reports.find(report_criteria, {"_id": 0})) 
        job_docs = list(self.query_jobs.find(job_criteria, {"_id": 0})) 
        by_user_id, by_username = self._audit_identity_index(report_docs, job_docs) 
 
        report_rows = [self._audit_row_from_report(x) for x in report_docs] 
        failed_rows = [ 
            self._audit_row_from_failed_job(x, by_user_id=by_user_id, by_username=by_username) 
            for x in job_docs 
        ] 
 
        rows = report_rows + failed_rows 
        rows.sort(key=lambda item: str(item.get("timestamp") or ""), 

reverse=True) 
 
        page = max(page, 1) 
        page_size = min(max(page_size, 1), 100) 
        total = len(rows) 
        total_pages = max(ceil(total / page_size), 1) 
        start = (page - 1) * page_size 
        end = start + page_size 
 
        return { 
            "rows": rows[start:end], 
            "total_count": total, 
            "page": page, 
            "page_size": page_size, 
            "total_pages": total_pages, 
        } 
 
 

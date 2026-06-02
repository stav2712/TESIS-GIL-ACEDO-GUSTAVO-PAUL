from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import settings
from .security import UserClaims

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def without_id(doc: dict | None) -> dict | None:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


class PlatformRepo:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        self.client.admin.command("ping")
        db = self.client[settings.MONGO_DB]
        self.templates = db[settings.MONGO_PLATFORM_TEMPLATES_COLLECTION]

        self.templates.create_index([("template_id", ASCENDING)], unique=True)
        self.templates.create_index([("owner_user_id", ASCENDING), ("updated_at", DESCENDING)])
        self.templates.create_index([("visibility", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)])
        self.templates.create_index([("tags", ASCENDING)])
        self.templates.create_index([("deleted", ASCENDING), ("updated_at", DESCENDING)])
        self.templates.create_index([("title", "text"), ("description", "text"), ("nl", "text"), ("tags", "text")])

    def _base_visible_criteria(self, claims: UserClaims) -> dict[str, Any]:
        if claims.is_adminish:
            return {"deleted": False}
        return {
            "deleted": False,
            "$or": [
                {"owner_user_id": claims.user_id},
                {"visibility": "shared", "status": "published"},
            ],
        }

    def _can_edit(self, doc: dict, claims: UserClaims) -> bool:
        return claims.is_adminish or int(doc.get("owner_user_id") or 0) == claims.user_id

    def _public(self, doc: dict, claims: UserClaims) -> dict:
        out = without_id(doc) or {}
        can_edit = self._can_edit(out, claims)
        out["can_edit"] = can_edit
        out["can_delete"] = can_edit
        return out

    def list_templates(self, claims: UserClaims, *, q: str | None = None, tag: str | None = None, mine: bool = False) -> dict:
        criteria = self._base_visible_criteria(claims)
        and_parts: list[dict[str, Any]] = [criteria]

        if mine:
            and_parts.append({"owner_user_id": claims.user_id})

        clean_tag = re.sub(r"\s+", " ", (tag or "").strip().lower())
        if clean_tag:
            and_parts.append({"tags": clean_tag})

        clean_q = CONTROL_CHARS_RE.sub(" ", (q or "").strip())
        clean_q = re.sub(r"\s+", " ", clean_q).strip()[:120]
        if clean_q:
            rx = {"$regex": re.escape(clean_q), "$options": "i"}
            and_parts.append({"$or": [{"title": rx}, {"description": rx}, {"nl": rx}, {"tags": rx}]})

        final_criteria = and_parts[0] if len(and_parts) == 1 else {"$and": and_parts}
        cur = self.templates.find(final_criteria, {"_id": 0}).sort("updated_at", DESCENDING).limit(200)
        rows = [self._public(row, claims) for row in cur]
        return {"rows": rows, "total_count": len(rows)}

    def get_template(self, template_id: str, claims: UserClaims) -> dict | None:
        doc = self.templates.find_one({"template_id": template_id, "deleted": False}, {"_id": 0})
        if not doc:
            return None
        if claims.is_adminish or doc.get("owner_user_id") == claims.user_id or (doc.get("visibility") == "shared" and doc.get("status") == "published"):
            return self._public(doc, claims)
        return None

    def create_template(self, claims: UserClaims, payload: dict) -> dict:
        tid = str(uuid4())
        ts = now_iso()
        doc = {
            "template_id": tid,
            "title": payload["title"],
            "description": payload.get("description"),
            "nl": payload["nl"],
            "tags": payload.get("tags") or [],
            "visibility": payload.get("visibility") or "private",
            "status": payload.get("status") or "published",
            "owner_user_id": claims.user_id,
            "owner_username": claims.username,
            "owner_full_name": claims.full_name,
            "owner_profile": claims.profile,
            "use_count": 0,
            "fork_count": 0,
            "created_at": ts,
            "updated_at": ts,
            "last_used_at": None,
            "deleted": False,
            "deleted_at": None,
        }
        self.templates.insert_one(doc)
        return self._public(doc, claims)

    def update_template(self, template_id: str, claims: UserClaims, changes: dict) -> dict | None:
        doc = self.templates.find_one({"template_id": template_id, "deleted": False}, {"_id": 0})
        if not doc:
            return None
        if not self._can_edit(doc, claims):
            return None

        allowed = {"title", "description", "nl", "tags", "visibility", "status"}
        next_values = {key: value for key, value in changes.items() if key in allowed}
        next_values["updated_at"] = now_iso()
        self.templates.update_one({"template_id": template_id, "deleted": False}, {"$set": next_values})
        updated = self.templates.find_one({"template_id": template_id, "deleted": False}, {"_id": 0})
        return self._public(updated or {}, claims)

    def delete_template(self, template_id: str, claims: UserClaims) -> bool:
        doc = self.templates.find_one({"template_id": template_id, "deleted": False}, {"_id": 0})
        if not doc or not self._can_edit(doc, claims):
            return False
        ts = now_iso()
        res = self.templates.update_one(
            {"template_id": template_id, "deleted": False},
            {"$set": {"deleted": True, "deleted_at": ts, "updated_at": ts}},
        )
        return res.matched_count == 1

    def record_use(self, template_id: str, claims: UserClaims) -> dict | None:
        doc = self.get_template(template_id, claims)
        if not doc:
            return None
        ts = now_iso()
        self.templates.update_one(
            {"template_id": template_id, "deleted": False},
            {"$inc": {"use_count": 1}, "$set": {"last_used_at": ts, "updated_at": ts}},
        )
        updated = self.templates.find_one({"template_id": template_id, "deleted": False}, {"_id": 0}) or {}
        return {"ok": True, "use_count": int(updated.get("use_count") or 0), "last_used_at": ts}

    def fork_template(self, template_id: str, claims: UserClaims) -> dict | None:
        source = self.get_template(template_id, claims)
        if not source:
            return None
        fork = self.create_template(
            claims,
            {
                "title": f"Copia de {source.get('title', 'plantilla')}"[:90],
                "description": source.get("description"),
                "nl": source.get("nl") or "",
                "tags": source.get("tags") or [],
                "visibility": "private",
                "status": "draft",
            },
        )
        self.templates.update_one({"template_id": template_id, "deleted": False}, {"$inc": {"fork_count": 1}, "$set": {"updated_at": now_iso()}})
        return fork

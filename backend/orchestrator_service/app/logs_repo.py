from datetime import datetime, timezone
from uuid import uuid4
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError
from .config import settings

class MongoLogsRepo:
    """
    Repositorio NoSQL (MongoDB) con campos {usuario, NL, SQL, timestamp, latencia, feedback}. :contentReference[oaicite:12]{index=12}
    Feedback inicia nulo y luego se actualiza según pulgar arriba/abajo. :contentReference[oaicite:13]{index=13}
    """
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        try:
            self.client.admin.command("ping")
        except ServerSelectionTimeoutError:
            raise RuntimeError("MongoDB no está corriendo (revisa MONGO_URI o levanta MongoDB).")

        self.col = self.client[settings.MONGO_DB][settings.MONGO_COLLECTION]
        self.col.create_index([("report_id", ASCENDING)], unique=True)
        self.col.create_index([("user_id", ASCENDING), ("timestamp", ASCENDING)])

    def create_log(self, user_id: int, nl: str, sql: str, latency_ms: int) -> str:
        report_id = str(uuid4())
        doc = {
            "report_id": report_id,
            "user_id": user_id,          # usuario
            "nl": nl,                    # NL
            "sql": sql,                  # SQL
            "timestamp": datetime.now(timezone.utc).isoformat(),  # timestamp
            "latency_ms": latency_ms,    # latencia
            "feedback": None,            # feedback (inicia nulo) :contentReference[oaicite:14]{index=14}
        }
        self.col.insert_one(doc)
        return report_id

    def set_feedback(self, report_id: str, value: str) -> bool:
        # value: "up" | "down"
        feedback = "positive" if value == "up" else "negative"
        res = self.col.update_one({"report_id": report_id}, {"$set": {"feedback": feedback}})
        return res.modified_count == 1

    def get_log(self, report_id: str) -> dict | None:
        return self.col.find_one({"report_id": report_id}, {"_id": 0})
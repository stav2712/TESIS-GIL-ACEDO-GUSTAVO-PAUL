from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os

app = FastAPI(title="Translator Service (NL-to-SQL)")

TERMINOLOGY_URL = os.getenv("TERMINOLOGY_URL", "http://127.0.0.1:8004/normalize")
DB_DIALECT = os.getenv("DB_DIALECT", "sqlite").lower()

class TranslateIn(BaseModel):
    nl: str

@app.get("/health")
def health():
    return {"ok": True}

def baseline_translate(nl_norm: str) -> str:
    t = nl_norm.lower()

    # MUY básico para que ya corra (luego se reemplaza por T5 y dataset)
    if "paciente" in t and ("lista" in t or "listar" in t):
        return "SELECT id, full_name, sex, birth_date FROM patients ORDER BY id DESC"
    if "diabetes" in t:
        return """
        SELECT p.id, p.full_name, d.icd10_code, d.description, d.diagnosed_at
        FROM patients p
        JOIN diagnoses d ON d.patient_id = p.id
        WHERE d.icd10_code = 'E11'
        ORDER BY d.diagnosed_at DESC
        """
    return "SELECT id, full_name, sex, birth_date FROM patients ORDER BY id DESC"

def apply_limit(sql: str, limit: int = 100) -> str:
    s = sql.strip().rstrip(";")
    if DB_DIALECT == "mssql":
        if " top " in s.lower():
            return s
        return s.replace("SELECT", f"SELECT TOP {limit}", 1)
    if " limit " in s.lower():
        return s
    return f"{s} LIMIT {limit}"

@app.post("/translate")
async def translate(payload: TranslateIn):
    # normalización (catálogo terminológico)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(TERMINOLOGY_URL, json={"text": payload.nl})
        if r.status_code != 200:
            raise HTTPException(502, "Terminology service no disponible")
        nl_norm = r.json()["normalized"]

    sql = baseline_translate(nl_norm)
    sql = apply_limit(sql, 100)
    return {"sql": sql, "normalized": nl_norm}
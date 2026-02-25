from fastapi import FastAPI
from pydantic import BaseModel
from .config import settings
from .store import load_synonyms

app = FastAPI(title="Terminology Service")

SYN = load_synonyms(settings.SYNONYMS_CSV)

class NormalizeIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True, "synonyms_loaded": len(SYN)}

@app.post("/normalize")
def normalize(payload: NormalizeIn):
    t = payload.text.lower()
    for k, v in SYN.items():
        t = t.replace(k, v.lower())
    return {"normalized": t}
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .store import load_concepts, load_synonyms, load_values

app = FastAPI(title="Terminology Service")

SYN = load_synonyms(settings.SYNONYMS_CSV)
CONCEPTS = load_concepts(settings.CONCEPTS_CSV)
VALUES = load_values(settings.VALUES_CSV)

class NormalizeIn(BaseModel):
    text: str

def replace_synonyms(text: str) -> str:
    out = text.lower()
    for k in sorted(SYN.keys(), key=len, reverse=True):
        out = out.replace(k, SYN[k].lower())
    return out

def resolve_concepts(text: str) -> list[dict]:
    found: list[dict] = []
    t = text.lower()
    for item in CONCEPTS:
        candidates = [item.get("term", "")] + item.get("aliases", [])
        if any(c and c in t for c in candidates):
            found.append(
                {
                    "term": item.get("term"),
                    "canonical": item.get("canonical"),
                    "category": item.get("category"),
                    "codes": item.get("codes", []),
                    "aliases": item.get("aliases", []),
                }
            )
    dedup = []
    seen = set()
    for x in found:
        key = (x.get("canonical"), tuple(x.get("codes", [])))
        if key not in seen:
            seen.add(key)
            dedup.append(x)
    return dedup

def resolve_values(text: str) -> list[dict]:
    found: list[dict] = []
    t = text.lower()
    for item in VALUES:
        candidates = [item.get("term", "")] + item.get("aliases", [])
        if any(c and c in t for c in candidates):
            found.append(
                {
                    "field": item.get("field"),
                    "canonical": item.get("canonical"),
                    "aliases": item.get("aliases", []),
                }
            )
    dedup = []
    seen = set()
    for x in found:
        key = (x.get("field"), x.get("canonical"))
        if key not in seen:
            seen.add(key)
            dedup.append(x)
    return dedup

@app.get("/health")
def health():
    return {
        "ok": True,
        "synonyms_loaded": len(SYN),
        "concepts_loaded": len(CONCEPTS),
        "values_loaded": len(VALUES),
    }

@app.post("/normalize")
def normalize(payload: NormalizeIn):
    normalized = replace_synonyms(payload.text)
    resolved_terms = resolve_concepts(normalized)
    resolved_values = resolve_values(normalized)
    return {
        "normalized": normalized,
        "resolved_terms": resolved_terms,
        "resolved_values": resolved_values,
    }
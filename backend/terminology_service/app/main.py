from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .store import load_concepts, load_synonyms, load_value_map

app = FastAPI(title="Terminology Service")
SYN = load_synonyms(settings.SYNONYMS_CSV)
CONCEPTS = load_concepts(settings.CONCEPTS_CSV)
VALUE_MAP = load_value_map(settings.VALUES_CSV)

class NormalizeIn(BaseModel):
    text: str

def _replace_synonyms(text: str) -> str:
    out = text
    for term in sorted(SYN.keys(), key=len, reverse=True):
        out = out.replace(term, SYN[term].lower())
    return out

@app.get("/health")
def health():
    return {
        "ok": True,
        "synonyms_loaded": len(SYN),
        "concepts_loaded": len(CONCEPTS),
        "values_loaded": len(VALUE_MAP),
    }

@app.post("/normalize")
def normalize(payload: NormalizeIn):
    original = payload.text.strip()
    t = original.lower()
    normalized = _replace_synonyms(t)

    resolved_terms: list[dict] = []
    resolved_values: list[dict] = []
    seen_terms: set[tuple[str, str]] = set()
    seen_values: set[tuple[str, str]] = set()

    for item in CONCEPTS:
        matches = [term for term in item["all_terms"] if term and term in normalized]
        if not matches:
            continue
        best = sorted(matches, key=len, reverse=True)[0]
        key = (item["canonical"], best)
        if key in seen_terms:
            continue
        seen_terms.add(key)
        normalized = normalized.replace(best, item["canonical"].lower())
        resolved_terms.append(
            {
                "surface": best,
                "canonical": item["canonical"],
                "category": item.get("category"),
                "codes": item.get("codes", []),
                "matched_alias": best,
            }
        )

    for item in VALUE_MAP:
        matches = [term for term in item["all_terms"] if term and term in normalized]
        if not matches:
            continue
        best = sorted(matches, key=len, reverse=True)[0]
        key = (item["field"], item["canonical"])
        if key in seen_values:
            continue
        seen_values.add(key)
        normalized = normalized.replace(best, item["canonical"].lower())
        resolved_values.append(
            {
                "field": item["field"],
                "canonical": item["canonical"],
                "matched_alias": best,
            }
        )

    return {
        "normalized": normalized,
        "resolved_terms": resolved_terms,
        "resolved_values": resolved_values,
    }
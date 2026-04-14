from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

def _read_csv(path_str: str) -> list[dict[str, str]]:
    path = Path(path_str)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_synonyms(csv_path: str) -> dict[str, str]:
    rows = _read_csv(csv_path)
    mapping: dict[str, str] = {}
    for row in rows:
        term = (row.get("term") or "").strip().lower()
        canonical = (row.get("canonical") or "").strip()
        if term and canonical:
            mapping[term] = canonical
    return mapping

def load_concepts(csv_path: str) -> list[dict[str, Any]]:
    rows = _read_csv(csv_path)
    out: list[dict[str, Any]] = []
    for row in rows:
        term = (row.get("term") or "").strip().lower()
        canonical = (row.get("canonical") or "").strip()
        category = (row.get("category") or "").strip().lower() or None
        codes = [x.strip() for x in (row.get("codes") or "").split("|") if x.strip()]
        aliases = [x.strip().lower() for x in (row.get("aliases") or "").split("|") if x.strip()]
        if term or aliases:
            out.append(
                {
                    "term": term,
                    "canonical": canonical or term,
                    "category": category,
                    "codes": codes,
                    "aliases": aliases,
                }
            )
    return out

def load_values(csv_path: str) -> list[dict[str, Any]]:
    rows = _read_csv(csv_path)
    out: list[dict[str, Any]] = []
    for row in rows:
        field = (row.get("field") or "").strip()
        term = (row.get("term") or "").strip().lower()
        canonical = (row.get("canonical") or "").strip()
        aliases = [x.strip().lower() for x in (row.get("aliases") or "").split("|") if x.strip()]
        if field and (term or aliases):
            out.append(
                {
                    "field": field,
                    "term": term,
                    "canonical": canonical or term,
                    "aliases": aliases,
                }
            )
    return out
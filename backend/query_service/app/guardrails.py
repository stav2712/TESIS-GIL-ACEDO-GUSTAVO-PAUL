from __future__ import annotations

import re

DISALLOWED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.IGNORECASE)

TABLE_RE = re.compile(
    r"\b(?:from|join)\s+((?:[a-zA-Z_][a-zA-Z0-9_]*\.)?[a-zA-Z_][a-zA-Z0-9_]*)",
    flags=re.IGNORECASE,
)

def is_safe_select(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if not (s.lower().startswith("select") or s.lower().startswith("with")):
        return False
    if DISALLOWED.search(f" {s} "):
        return False
    return True

def extract_tables(sql: str) -> set[str]:
    return {m.group(1).lower() for m in TABLE_RE.finditer(sql)}
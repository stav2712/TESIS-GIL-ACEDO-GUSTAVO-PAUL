import re

DISALLOWED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.IGNORECASE)

def is_safe_select(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if not s.lower().startswith("select"):
        return False
    if DISALLOWED.search(s):
        return False
    return True

def extract_tables(sql: str) -> set[str]:
    tokens = re.findall(r"\b(from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    return {t[1].lower() for t in tokens}
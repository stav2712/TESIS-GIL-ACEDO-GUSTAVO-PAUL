import re

DISALLOWED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.IGNORECASE)
TABLE_TOKEN = re.compile(r'\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_\.]*|"[^"]+"\."[^"]+")', re.IGNORECASE)

def is_safe_select(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if not s.lower().startswith("select"):
        return False
    if DISALLOWED.search(s):
        return False
    if ";" in s:
        return False
    return True

def extract_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for raw in TABLE_TOKEN.findall(sql):
        token = raw.replace('"', '').strip().lower()
        tables.add(token)
    return tables
from __future__ import annotations

import re

SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_sql_from_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw

    fence = SQL_FENCE_RE.search(raw)
    if fence:
        raw = fence.group(1).strip()

    raw = raw.replace("\r", "").strip()
    lines = [line.rstrip() for line in raw.split("\n")]

    cleaned: list[str] = []
    started = False
    for line in lines:
        if not started:
            low = line.lower().strip()
            if low.startswith("select") or low.startswith("with"):
                started = True
                cleaned.append(line)
        else:
            cleaned.append(line)

    if cleaned:
        raw = "\n".join(cleaned).strip()

    raw = raw.strip().rstrip(";")
    return raw


def ensure_select_only(sql: str) -> str:
    s = (sql or "").strip().rstrip(";")
    if not s:
        raise ValueError("El modelo no devolvió SQL")
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("El modelo no devolvió un SELECT/CTE válido")
    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " create "]
    padded = f" {low} "
    if any(token in padded for token in banned):
        raise ValueError("El modelo devolvió una sentencia no permitida")
    return s

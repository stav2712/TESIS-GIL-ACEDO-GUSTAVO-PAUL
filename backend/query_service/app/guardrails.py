from __future__ import annotations

import re


DISALLOWED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|CALL|EXEC|EXECUTE|MERGE|COPY)\b",
    re.IGNORECASE,
)

LINE_COMMENT_RE = re.compile(r"--.*?(?=\n|$)")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
SINGLE_QUOTED_RE = re.compile(r"'(?:''|[^'])*'")
DOLLAR_QUOTED_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*\$.*?\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$.*?\$\$",
    re.DOTALL,
)

TABLE_RE = re.compile(
    r'\b(?:from|join)\s+((?:"?[A-Za-z_][A-Za-z0-9_]*"?\.)?"?[A-Za-z_][A-Za-z0-9_]*"?)',
    flags=re.IGNORECASE,
)


def _analysis_sql(sql: str) -> str:
    s = BLOCK_COMMENT_RE.sub(" ", sql)
    s = LINE_COMMENT_RE.sub(" ", s)
    s = DOLLAR_QUOTED_RE.sub("''", s)
    s = SINGLE_QUOTED_RE.sub("''", s)
    return s


def _clean_identifier(identifier: str) -> str:
    parts = [p.strip().strip('"').lower() for p in identifier.split(".")]
    return ".".join(p for p in parts if p)


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _read_identifier(s: str, i: int) -> tuple[str | None, int]:
    i = _skip_ws(s, i)

    if i >= len(s):
        return None, i

    if s[i] == '"':
        j = i + 1
        while j < len(s):
            if s[j] == '"':
                return s[i:j + 1], j + 1
            j += 1
        return None, i

    m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", s[i:])
    if not m:
        return None, i

    return m.group(0), i + len(m.group(0))


def _skip_parentheses(s: str, i: int) -> int:
    i = _skip_ws(s, i)

    if i >= len(s) or s[i] != "(":
        return i

    depth = 0

    while i < len(s):
        ch = s[i]

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1

        i += 1

    return i


def extract_cte_names(sql: str) -> set[str]:
    """
    Extrae nombres de CTEs declarados al inicio:

    WITH base AS (...),
         dx AS (...),
         pr AS (...),
         med AS (...)
    SELECT ...

    Soporta tambi?n:
    WITH RECURSIVE ...
    WITH base AS MATERIALIZED (...)
    WITH base AS NOT MATERIALIZED (...)
    WITH base(col1, col2) AS (...)
    """
    s = _analysis_sql(sql).strip()
    lower = s.lower()

    if not lower.startswith("with"):
        return set()

    i = 4
    i = _skip_ws(s, i)

    if s[i:i + 9].lower() == "recursive":
        i += 9

    ctes: set[str] = set()

    while i < len(s):
        name, i2 = _read_identifier(s, i)

        if not name:
            break

        ctes.add(_clean_identifier(name))
        i = _skip_ws(s, i2)

        # Opcional: WITH cte(col1, col2) AS (...)
        if i < len(s) and s[i] == "(":
            i = _skip_parentheses(s, i)
            i = _skip_ws(s, i)

        # Debe venir AS
        if s[i:i + 2].lower() != "as":
            break

        i += 2
        i = _skip_ws(s, i)

        # Opcional en PostgreSQL: AS MATERIALIZED / AS NOT MATERIALIZED
        if s[i:i + 3].lower() == "not":
            i += 3
            i = _skip_ws(s, i)

        if s[i:i + 12].lower() == "materialized":
            i += 12
            i = _skip_ws(s, i)

        # Cuerpo del CTE
        if i >= len(s) or s[i] != "(":
            break

        i = _skip_parentheses(s, i)
        i = _skip_ws(s, i)

        # Otro CTE separado por coma
        if i < len(s) and s[i] == ",":
            i += 1
            continue

        break

    return ctes


def is_safe_select(sql: str) -> bool:
    s = sql.strip()

    if not s:
        return False

    analysis = _analysis_sql(s).strip()

    # Permite un ?nico ; final, pero bloquea m?ltiples sentencias.
    if ";" in analysis.rstrip(";"):
        return False

    analysis = analysis.rstrip(";").strip()

    if not (
        analysis.lower().startswith("select")
        or analysis.lower().startswith("with")
    ):
        return False

    if DISALLOWED.search(f" {analysis} "):
        return False

    return True


def extract_tables(sql: str) -> set[str]:
    """
    Extrae tablas/vistas reales usadas en FROM/JOIN.

    Ignora referencias a CTEs como:
    FROM base
    JOIN dx
    JOIN pr
    JOIN med

    Pero sigue capturando las vistas reales dentro de los CTEs:
    reporting.vw_pacientes
    reporting.vw_diagnosticos
    etc.
    """
    s = _analysis_sql(sql)
    cte_names = extract_cte_names(s)

    tables: set[str] = set()

    for match in TABLE_RE.finditer(s):
        table_name = _clean_identifier(match.group(1))

        if not table_name:
            continue

        # Si es un nombre sin esquema y coincide con un CTE, no es tabla real.
        if "." not in table_name and table_name in cte_names:
            continue

        tables.add(table_name)

    return tables

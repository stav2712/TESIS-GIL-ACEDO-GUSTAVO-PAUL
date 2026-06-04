from __future__ import annotations

import re


DISALLOWED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|CALL|EXEC|EXECUTE|MERGE|COPY|VACUUM|ANALYZE|LOCK|NOTIFY|LISTEN)\b",
    re.IGNORECASE,
)

# Funciones que pueden bloquear el servicio, leer archivos del servidor,
# abrir conexiones externas, modificar estado de sesión o revelar metadata sensible.
DANGEROUS_FUNCTIONS = re.compile(
    r"(?<![A-Za-z0-9_])(?:(?:pg_catalog|public)\s*\.\s*)?"
    r"(pg_sleep|dblink|dblink_connect|lo_import|lo_export|pg_read_file|"
    r"pg_read_binary_file|pg_ls_dir|pg_stat_file|pg_advisory_lock|"
    r"pg_advisory_xact_lock|pg_terminate_backend|pg_cancel_backend|"
    r"set_config|current_setting|version|inet_server_addr|inet_server_port|"
    r"pg_backend_pid|pg_postmaster_start_time)\s*\(",
    re.IGNORECASE,
)

# En PostgreSQL, SELECT ... INTO crea una tabla. No es una consulta read-only.
SELECT_INTO = re.compile(
    r"\bselect\b(?:(?!\bfrom\b).)*\binto\b",
    re.IGNORECASE | re.DOTALL,
)

# SELECT ... FOR UPDATE/SHARE toma locks. No debe permitirse en reportes.
LOCKING_CLAUSE = re.compile(
    r"\bfor\s+(update|no\s+key\s+update|share|key\s+share)\b",
    re.IGNORECASE,
)

LINE_COMMENT_RE = re.compile(r"--.*?(?=\n|$)")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
SINGLE_QUOTED_RE = re.compile(r"'(?:''|[^'])*'")
DOLLAR_QUOTED_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*\$.*?\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$.*?\$\$",
    re.DOTALL,
)

IDENT = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
TABLE_RE = re.compile(
    rf"\b(?:from|join)\s+(({IDENT}\s*\.\s*)?{IDENT})",
    flags=re.IGNORECASE,
)

# PostgreSQL permite sintaxis como EXTRACT(YEAR FROM fecha_inicio) o
# SUBSTRING(campo FROM ...). Ese FROM no introduce una tabla.
SOURCE_LIKE_FUNCTIONS = {"extract", "substring", "trim", "overlay"}


def _analysis_sql(sql: str) -> str:
    s = BLOCK_COMMENT_RE.sub(" ", sql)
    s = LINE_COMMENT_RE.sub(" ", s)
    s = DOLLAR_QUOTED_RE.sub("''", s)
    s = SINGLE_QUOTED_RE.sub("''", s)
    return s


def _clean_identifier(identifier: str) -> str:
    parts = [p.strip().strip('"').lower() for p in re.split(r"\s*\.\s*", identifier)]
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
                return s[i : j + 1], j + 1
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


def _enclosing_function_name_before_keyword(sql: str, keyword_start: int) -> str | None:
    """Devuelve la función que contiene el keyword, si el keyword está dentro de func(...)."""
    depth = 0
    open_paren = -1

    for idx in range(keyword_start - 1, -1, -1):
        ch = sql[idx]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                open_paren = idx
                break
            depth -= 1

    if open_paren < 0:
        return None

    prefix = sql[:open_paren].rstrip()
    match = re.search(r'("?[A-Za-z_][A-Za-z0-9_]*"?)\s*$', prefix)
    if not match:
        return None
    return match.group(1).strip('"').lower()


def _is_function_internal_from(sql: str, keyword_start: int) -> bool:
    function_name = _enclosing_function_name_before_keyword(sql, keyword_start)
    return bool(function_name and function_name in SOURCE_LIKE_FUNCTIONS)


def _iter_table_matches(sql: str):
    for match in TABLE_RE.finditer(sql):
        # match.start() apunta al FROM/JOIN encontrado por TABLE_RE.
        if _is_function_internal_from(sql, match.start()):
            continue
        yield match


def extract_cte_names(sql: str) -> set[str]:
    """
    Extrae nombres de CTEs declarados al inicio.
    Soporta WITH RECURSIVE, MATERIALIZED, NOT MATERIALIZED y columnas explícitas.
    """
    s = _analysis_sql(sql).strip()
    lower = s.lower()
    if not lower.startswith("with"):
        return set()

    i = _skip_ws(s, 4)
    if s[i : i + 9].lower() == "recursive":
        i = _skip_ws(s, i + 9)

    ctes: set[str] = set()
    while i < len(s):
        name, i2 = _read_identifier(s, i)
        if not name:
            break

        ctes.add(_clean_identifier(name))
        i = _skip_ws(s, i2)

        # WITH cte(col1, col2) AS (...)
        if i < len(s) and s[i] == "(":
            i = _skip_ws(s, _skip_parentheses(s, i))

        if s[i : i + 2].lower() != "as":
            break

        i = _skip_ws(s, i + 2)

        # AS NOT MATERIALIZED (...)
        if s[i : i + 3].lower() == "not":
            i = _skip_ws(s, i + 3)
        if s[i : i + 12].lower() == "materialized":
            i = _skip_ws(s, i + 12)

        if i >= len(s) or s[i] != "(":
            break

        i = _skip_ws(s, _skip_parentheses(s, i))
        if i < len(s) and s[i] == ",":
            i = _skip_ws(s, i + 1)
            continue
        break

    return ctes


def is_safe_select(sql: str) -> bool:
    s = sql.strip()
    if not s:
        return False

    analysis = _analysis_sql(s).strip()

    # Permite un único ; final, pero bloquea múltiples sentencias.
    if ";" in analysis.rstrip(";"):
        return False

    analysis = analysis.rstrip(";").strip()
    lower = analysis.lower()

    if not (lower.startswith("select") or lower.startswith("with")):
        return False

    if DISALLOWED.search(f" {analysis} "):
        return False

    if SELECT_INTO.search(analysis):
        return False

    if LOCKING_CLAUSE.search(analysis):
        return False

    if DANGEROUS_FUNCTIONS.search(analysis):
        return False

    return True


def extract_tables(sql: str) -> set[str]:
    """
    Extrae tablas/vistas reales usadas en FROM/JOIN.
    Ignora CTEs sin esquema, pero mantiene las vistas reales dentro de ellos.
    Ignora FROM internos de funciones SQL como EXTRACT(YEAR FROM fecha).
    """
    s = _analysis_sql(sql)
    cte_names = extract_cte_names(s)
    tables: set[str] = set()

    for match in _iter_table_matches(s):
        table_name = _clean_identifier(match.group(1))
        if not table_name:
            continue

        # Si es un nombre sin esquema y coincide con un CTE, no es tabla real.
        if "." not in table_name and table_name in cte_names:
            continue

        tables.add(table_name)

    return tables

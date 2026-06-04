from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from .config import settings
from .security import UserClaims, require_permission

IDENT = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
TABLE_RE = re.compile(
    rf"\b(?:from|join)\s+(({IDENT}\s*\.\s*)?{IDENT})",
    flags=re.IGNORECASE,
)
TABLE_ALIAS_RE = re.compile(
    rf"\b(?:from|join)\s+(({IDENT}\s*\.\s*)?{IDENT})(?:\s+(?:as\s+)?({IDENT}))?",
    flags=re.IGNORECASE,
)

LINE_COMMENT_RE = re.compile(r"--.*?(?=\n|$)")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
SINGLE_QUOTED_RE = re.compile(r"'(?:''|[^'])*'")
DOLLAR_QUOTED_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*\$.*?\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$.*?\$\$",
    re.DOTALL,
)

SQL_KEYWORDS_AFTER_TABLE = {
    "on",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "group",
    "order",
    "limit",
    "offset",
    "fetch",
    "union",
    "except",
    "intersect",
    "having",
}

# PostgreSQL permite sintaxis como EXTRACT(YEAR FROM e.fecha_inicio). El FROM
# dentro de esas funciones NO es un origen de tabla. Si el extractor lo trata
# como tabla, aparece el falso positivo e.fecha_inicio en permisos globales.
SOURCE_LIKE_FUNCTIONS = {"extract", "substring", "trim", "overlay"}


# ---------- Análisis SQL liviano ----------
def _analysis_sql(sql: str) -> str:
    sql = BLOCK_COMMENT_RE.sub(" ", sql)
    sql = LINE_COMMENT_RE.sub(" ", sql)
    sql = DOLLAR_QUOTED_RE.sub("''", sql)
    sql = SINGLE_QUOTED_RE.sub("''", sql)
    return sql


def _clean_identifier(identifier: str) -> str:
    parts = [p.strip().strip('"').lower() for p in re.split(r"\s*\.\s*", identifier)]
    return ".".join(p for p in parts if p)


def _short_name(table: str) -> str:
    return table.split(".")[-1]


def _word_pattern(word: str) -> str:
    return rf'(?<![A-Za-z0-9_])"?{re.escape(word)}"?(?![A-Za-z0-9_])'


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


def extract_used_tables(sql: str) -> set[str]:
    s = _analysis_sql(sql)
    tables: set[str] = set()
    for match in _iter_table_matches(s):
        table = _clean_identifier(match.group(1))
        # Si el modelo llegara a usar un CTE sin esquema, no lo bloqueamos aquí;
        # query_service valida las vistas reales permitidas globalmente.
        if "." in table:
            tables.add(table)
    return tables


def _table_aliases(sql: str, used_tables: set[str]) -> dict[str, str]:
    """Devuelve alias -> tabla real. También registra nombre corto y tabla completa."""
    s = _analysis_sql(sql)
    aliases: dict[str, str] = {}

    for table in used_tables:
        aliases[table] = table
        aliases[_short_name(table)] = table

    for match in TABLE_ALIAS_RE.finditer(s):
        if _is_function_internal_from(s, match.start()):
            continue

        table = _clean_identifier(match.group(1))
        if table not in used_tables:
            continue

        alias = match.group(3)
        if not alias:
            continue

        alias_clean = _clean_identifier(alias)
        if not alias_clean or alias_clean in SQL_KEYWORDS_AFTER_TABLE:
            continue

        # Evita confundir JOIN ... ON con alias.
        if alias_clean != table and "." not in alias_clean:
            aliases[alias_clean] = table

    return aliases


def _contains_unqualified_column(sql: str, column: str) -> bool:
    s = _analysis_sql(sql).lower()
    # Evita contar alias.columna como columna sin calificador.
    return re.search(rf'(?<![A-Za-z0-9_\.])"?{re.escape(column)}"?(?![A-Za-z0-9_])', s) is not None


def _contains_qualified_column(sql: str, qualifier: str, column: str) -> bool:
    s = _analysis_sql(sql).lower()
    return re.search(
        rf'{_word_pattern(qualifier)}\s*\.\s*"?{re.escape(column)}"?(?![A-Za-z0-9_])',
        s,
    ) is not None


def _references_column(sql: str, table: str, column: str, used_tables: set[str]) -> bool:
    aliases = _table_aliases(sql, used_tables)
    qualifiers = {alias for alias, alias_table in aliases.items() if alias_table == table}

    if any(_contains_qualified_column(sql, qualifier, column) for qualifier in qualifiers):
        return True

    # En consultas de una sola vista, una columna sin prefijo pertenece a esa vista.
    if len(used_tables) == 1 and _contains_unqualified_column(sql, column):
        return True

    return False


def _has_select_star(sql: str) -> bool:
    s = _analysis_sql(sql).lower()
    return (
        re.search(r"\bselect\s+\*\s+\bfrom\b", s) is not None
        or re.search(r"\bselect\b.*\b[A-Za-z_][A-Za-z0-9_]*\s*\.\s*\*", s, re.DOTALL) is not None
    )


def _split_select_items(sql: str) -> list[str]:
    s = _analysis_sql(sql)
    lower = s.lower()
    select_at = lower.find("select")
    if select_at < 0:
        return []

    i = select_at + len("select")
    depth = 0
    from_at: int | None = None
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif depth == 0 and lower[i : i + 4] == "from" and (i == 0 or not lower[i - 1].isalnum()):
            from_at = i
            break
        i += 1

    if from_at is None:
        return []

    raw = s[select_at + len("select") : from_at]
    items: list[str] = []
    start = 0
    depth = 0
    for idx, ch in enumerate(raw):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == "," and depth == 0:
            item = raw[start:idx].strip()
            if item:
                items.append(item)
            start = idx + 1

    item = raw[start:].strip()
    if item:
        items.append(item)

    return items


def _output_name_from_select_item(item: str) -> str | None:
    m = re.search(rf"\bas\s+({IDENT})\s*$", item, flags=re.IGNORECASE)
    if m:
        return _clean_identifier(m.group(1)).split(".")[-1]

    # Columna simple o calificada: p.nombre_paciente -> nombre_paciente.
    m = re.search(rf"({IDENT})(?:\s*\.\s*({IDENT}))?\s*$", item)
    if not m:
        return None

    if m.group(2):
        return _clean_identifier(m.group(2))

    token = _clean_identifier(m.group(1))
    if token.lower() in {"desc", "asc", "null", "true", "false"}:
        return None
    return token


def _select_output_names_referencing(
    sql: str,
    table: str,
    columns: set[str],
    used_tables: set[str],
) -> set[str]:
    names: set[str] = set()
    aliases = _table_aliases(sql, used_tables)
    qualifiers = {alias for alias, alias_table in aliases.items() if alias_table == table}

    for item in _split_select_items(sql):
        if item == "*" or item.endswith(".*"):
            continue

        for column in columns:
            qualified = any(_contains_qualified_column(item, qualifier, column) for qualifier in qualifiers)
            unqualified = len(used_tables) == 1 and _contains_unqualified_column(item, column)

            if qualified or unqualified:
                output_name = _output_name_from_select_item(item)
                if output_name:
                    names.add(output_name)
                names.add(column)
    return names


# ---------- Reglas de perfil ----------
def global_allowed_tables() -> set[str]:
    return {x.strip().lower() for x in settings.ALLOWED_TABLES.split(",") if x.strip()}


def ensure_can_run_query(claims: UserClaims) -> None:
    require_permission(claims, "can_query")


def ensure_can_export(claims: UserClaims) -> None:
    require_permission(claims, "can_export")


def ensure_can_view_audit(claims: UserClaims) -> None:
    require_permission(claims, "can_view_audit")


def ensure_can_view_config(claims: UserClaims) -> None:
    require_permission(claims, "can_view_system_config")


def _column_rules_for_used_tables(
    claims: UserClaims,
    used_tables: set[str],
    rule_name: str,
) -> dict[str, set[str]]:
    rules: dict[str, set[str]] = {}
    for table in used_tables:
        raw = (claims.column_permissions or {}).get(table) or {}
        columns = {str(c).strip().lower() for c in raw.get(rule_name, []) if str(c).strip()}
        if columns:
            rules[table] = columns
    return rules


def _forbidden_column_hits(sql: str, claims: UserClaims, used_tables: set[str]) -> dict[str, list[str]]:
    forbidden = _column_rules_for_used_tables(claims, used_tables, "forbidden")
    if not forbidden:
        return {}

    hits: dict[str, list[str]] = defaultdict(list)

    for table, columns in forbidden.items():
        for column in sorted(columns):
            if _references_column(sql, table, column, used_tables):
                hits[table].append(column)

        # SELECT * expondría columnas prohibidas de la vista.
        if columns and _has_select_star(sql):
            for column in sorted(columns):
                if column not in hits[table]:
                    hits[table].append(column)

    return {table: cols for table, cols in hits.items() if cols}


def ensure_sql_allowed_by_profile(sql: str, claims: UserClaims) -> None:
    used_tables = extract_used_tables(sql)
    if not used_tables:
        return

    # El query_service sigue siendo la última barrera global.
    globally_allowed = global_allowed_tables()
    if globally_allowed:
        forbidden_global = used_tables - globally_allowed
        if forbidden_global:
            raise HTTPException(
                403,
                {
                    "error": "La consulta usa vistas no permitidas globalmente",
                    "tables": sorted(forbidden_global),
                },
            )

    # Restricción del perfil:
    # - table_access_mode="all": no agrega restricción por perfil; solo aplica la lista global.
    # - table_access_mode="custom": usa exactamente claims.allowed_tables.
    #   Si la lista está vacía, el perfil no puede consultar ninguna vista.
    if claims.table_access_mode == "custom":
        allowed_by_profile = set(claims.allowed_tables)
        forbidden_profile = used_tables - allowed_by_profile
        if forbidden_profile:
            raise HTTPException(
                403,
                {
                    "error": "Tu perfil no permite consultar algunas vistas usadas por esta pregunta",
                    "tables": sorted(forbidden_profile),
                    "allowed_tables": sorted(allowed_by_profile),
                },
            )

    forbidden_columns = _forbidden_column_hits(sql, claims, used_tables)
    if forbidden_columns:
        raise HTTPException(
            403,
            {
                "error": "Tu perfil no permite usar algunos campos de las vistas consultadas",
                "columns": forbidden_columns,
            },
        )


def _columns_to_hide(sql: str, claims: UserClaims, result_columns: list[str]) -> set[str]:
    used_tables = extract_used_tables(sql)
    if not used_tables:
        return set()

    hidden_by_table = _column_rules_for_used_tables(claims, used_tables, "hidden")
    if not hidden_by_table:
        return set()

    result_by_lower = {str(col).lower(): str(col) for col in result_columns}
    hidden_result_names: set[str] = set()

    for table, hidden_columns in hidden_by_table.items():
        # Si el resultado conserva el mismo nombre de columna, se oculta directo.
        for col in hidden_columns:
            if col in result_by_lower:
                hidden_result_names.add(result_by_lower[col])

        # Si el SELECT usó alias, ocultamos el nombre de salida aproximado.
        for output_name in _select_output_names_referencing(sql, table, hidden_columns, used_tables):
            if output_name.lower() in result_by_lower:
                hidden_result_names.add(result_by_lower[output_name.lower()])

    return hidden_result_names


def apply_column_permissions_to_result(data: dict[str, Any], claims: UserClaims, sql: str) -> dict[str, Any]:
    columns = [str(c) for c in data.get("columns", [])]
    rows = list(data.get("rows", []) or [])
    hidden = _columns_to_hide(sql, claims, columns)

    if not hidden:
        return {**data, "suppressed_columns": data.get("suppressed_columns", []) or []}

    visible_columns = [col for col in columns if col not in hidden]
    visible_rows = [
        {col: row.get(col) for col in visible_columns}
        for row in rows
    ]

    base_message = data.get("result_message")
    hidden_message = f"Se ocultaron {len(hidden)} columna(s) por reglas del perfil."
    result_message = f"{base_message} {hidden_message}" if base_message else hidden_message

    return {
        **data,
        "columns": visible_columns,
        "rows": visible_rows,
        "suppressed_columns": sorted(hidden),
        "result_message": result_message,
    }


def visible_sql(sql: str, claims: UserClaims) -> str:
    return sql if claims.can("can_view_sql") else ""

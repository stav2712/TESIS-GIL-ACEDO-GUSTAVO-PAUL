from __future__ import annotations

import re

IDENTIFIER_RE = r"[A-Za-z_][A-Za-z0-9_]*"


def repair_outer_order_by_dangling_qualifiers(sql: str, dialect: str) -> str:
    """
    Repara un caso conservador que algunos modelos NL2SQL generan con CTEs:

        WITH base AS (...) SELECT * FROM base ORDER BY p.nombre_completo

    En el SELECT externo, el alias `p` ya no existe porque solo vivía dentro
    del CTE. PostgreSQL lo rechaza con "falta una entrada para la tabla p en
    la cláusula FROM". Cuando el SELECT externo proyecta `*` desde una única
    fuente sin JOIN, el nombre exportado por el CTE/subquery puede ordenarse de
    forma no calificada:

        WITH base AS (...) SELECT * FROM base ORDER BY nombre_completo

    La reparación es deliberadamente estrecha:
    - solo PostgreSQL;
    - solo en el ORDER BY del SELECT externo;
    - solo si el SELECT externo es `SELECT * FROM <fuente>` sin JOIN ni coma;
    - solo elimina calificadores simples `alias.columna` en esa cláusula.

    No cambia filtros, JOINs, columnas seleccionadas, permisos ni guardrails.
    """
    if (dialect or "").strip().lower() not in {"postgres", "postgresql"}:
        return sql

    s = sql or ""
    if "." not in s or not re.search(r"\border\s+by\b", s, flags=re.IGNORECASE):
        return s

    outer_select = _find_outer_select_start(s)
    if outer_select < 0:
        return s

    from_pos = _find_top_level_keyword(s, "from", start=outer_select + len("select"))
    if from_pos < 0:
        return s

    # La reparación se permite solo si el SELECT externo es SELECT *.
    select_list = s[outer_select + len("select") : from_pos].strip()
    if select_list != "*":
        return s

    order_pos = _find_top_level_order_by(s, start=from_pos + len("from"))
    if order_pos < 0:
        return s

    from_clause = s[from_pos + len("from") : order_pos]
    if not _looks_like_single_outer_source(from_clause):
        return s

    order_start = _skip_order_by(s, order_pos)
    if order_start < 0:
        return s

    order_end = _find_order_by_end(s, order_start)
    order_expr = s[order_start:order_end]
    repaired_expr = _strip_simple_qualifiers(order_expr)
    if repaired_expr == order_expr:
        return s
    return s[:order_start] + repaired_expr + s[order_end:]


def _find_outer_select_start(sql: str) -> int:
    """Devuelve el SELECT principal, ignorando CTEs `WITH ... AS (...)`."""
    first_select = _find_top_level_keyword(sql, "select", start=0)
    if first_select < 0:
        return -1

    i = _skip_ws(sql, 0)
    if not _keyword_at(sql, i, "with"):
        return first_select

    # Con WITH, el primer SELECT de nivel 0 después de todas las definiciones de
    # CTE es el SELECT principal. Los SELECT internos quedan a profundidad > 0.
    return first_select


def _strip_simple_qualifiers(order_expr: str) -> str:
    pattern = re.compile(
        rf"(?<![\w.])({IDENTIFIER_RE})\s*\.\s*({IDENTIFIER_RE})(?!\s*\.)",
        flags=re.IGNORECASE,
    )
    return pattern.sub(lambda match: match.group(2), order_expr)


def _looks_like_single_outer_source(from_clause: str) -> bool:
    clause = from_clause.strip()
    if not clause:
        return False

    # Si hay coma o JOIN al nivel superior, quitar calificadores podría volver
    # ambiguo el ORDER BY. En ese caso no tocamos nada.
    if _has_top_level_comma(clause):
        return False
    if _find_top_level_keyword(clause, "join", start=0) >= 0:
        return False

    # Acepta `base`, `base b`, `base AS b`, `(SELECT ...) base` y variantes con
    # comillas simples/dobles ya que solo validamos que sea una fuente única.
    return True


def _find_top_level_order_by(sql: str, start: int = 0) -> int:
    i = start
    while True:
        pos = _find_top_level_keyword(sql, "order", start=i)
        if pos < 0:
            return -1
        after_order = _skip_ws(sql, pos + len("order"))
        if _keyword_at(sql, after_order, "by"):
            return pos
        i = pos + len("order")


def _skip_order_by(sql: str, order_pos: int) -> int:
    if not _keyword_at(sql, order_pos, "order"):
        return -1
    by_pos = _skip_ws(sql, order_pos + len("order"))
    if not _keyword_at(sql, by_pos, "by"):
        return -1
    return _skip_ws(sql, by_pos + len("by"))


def _find_order_by_end(sql: str, start: int) -> int:
    # Cláusulas que pueden aparecer después del ORDER BY externo.
    for keyword in ("limit", "offset", "fetch", "for", "union", "intersect", "except"):
        pos = _find_top_level_keyword(sql, keyword, start=start)
        if pos >= 0:
            return pos
    return len(sql)


def _find_top_level_keyword(sql: str, keyword: str, start: int = 0) -> int:
    lower_keyword = keyword.lower()
    i = max(start, 0)
    depth = 0
    quote: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        ch = sql[i]

        if dollar_tag is not None:
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                dollar_tag = None
            else:
                i += 1
            continue

        if quote is not None:
            if quote == "'" and ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            elif quote == '"' and ch == '"':
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue

        if ch == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if match:
                dollar_tag = match.group(0)
                i += len(dollar_tag)
                continue

        if sql.startswith("--", i):
            newline = sql.find("\n", i + 2)
            if newline < 0:
                return -1
            i = newline + 1
            continue

        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end < 0:
                return -1
            i = end + 2
            continue

        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue

        if depth == 0 and _keyword_at(sql, i, lower_keyword):
            return i
        i += 1

    return -1


def _keyword_at(sql: str, pos: int, keyword: str) -> bool:
    if pos < 0:
        return False
    end = pos + len(keyword)
    if sql[pos:end].lower() != keyword.lower():
        return False
    before = sql[pos - 1] if pos > 0 else ""
    after = sql[end] if end < len(sql) else ""
    if before and (before.isalnum() or before == "_"):
        return False
    if after and (after.isalnum() or after == "_"):
        return False
    return True


def _skip_ws(sql: str, pos: int) -> int:
    while pos < len(sql) and sql[pos].isspace():
        pos += 1
    return pos


def _has_top_level_comma(sql: str) -> bool:
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote is not None:
            if quote == "'" and ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            elif quote == '"' and ch == '"':
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch == "," and depth == 0:
            return True
        i += 1
    return False

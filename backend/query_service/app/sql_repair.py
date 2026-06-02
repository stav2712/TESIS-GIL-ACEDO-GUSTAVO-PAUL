from __future__ import annotations

import re
from dataclasses import dataclass

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
PATIENT_SOURCE_VIEWS = {"reporting.vw_pacientes", "reporting.vw_paciente_360"}


@dataclass(frozen=True)
class _SelectBlock:
    start: int
    end: int
    depth: int


def repair_sql_for_dialect(sql: str, dialect: str) -> str:
    """
    Reparaciones conservadoras para SQL generado por el modelo.

    Actualmente corrige un caso común en PostgreSQL: el modelo usa alias del
    SELECT dentro de expresiones del ORDER BY del mismo SELECT, por ejemplo:

        COUNT(*) AS total_x ... ORDER BY total_x + otro_alias DESC

    PostgreSQL permite ORDER BY total_x, pero no siempre permite usar ese alias
    como parte de una expresión en el mismo nivel. La reparación reemplaza esos
    alias por su expresión original solo dentro del ORDER BY correspondiente.
    """
    if (dialect or "").strip().lower() not in {"postgres", "postgresql"}:
        return sql

    repaired = repair_postgres_order_by_alias_expressions(sql)
    repaired = repair_patient_uuid_source_identifier(repaired)
    return repaired


def repair_postgres_order_by_alias_expressions(sql: str) -> str:
    result = sql
    blocks = _find_select_blocks(result)
    # Procesar desde el final evita recalcular posiciones después de reemplazos.
    for block in sorted(blocks, key=lambda item: item.start, reverse=True):
        repaired = _repair_select_block(result[block.start : block.end], block.depth)
        if repaired != result[block.start : block.end]:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def repair_patient_uuid_source_identifier(sql: str) -> str:
    """
    Corrige una confusión común del modelo con datos Synthea/OMOP:
    id_paciente es entero interno, mientras que id_paciente_fuente es el
    identificador externo tipo UUID que el usuario suele copiar desde la UI.

    Solo se aplica cuando la consulta referencia vistas de paciente conocidas
    y compara `id_paciente` contra un literal con formato UUID. No convierte
    números, no toca otros campos y el Query Service vuelve a pasar guardrails
    después de reparar.
    """
    aliases = _patient_view_aliases(sql)
    if not aliases:
        return sql

    repaired = sql
    for alias in sorted(aliases, key=len, reverse=True):
        repaired = _replace_patient_uuid_comparisons_for_qualifier(repaired, alias)

    # También corregimos la forma no calificada cuando hay una vista de paciente
    # conocida: WHERE id_paciente = 'uuid'. Solo aplica a literales UUID, no a
    # IDs numéricos internos.
    repaired = _replace_unqualified_patient_uuid_comparison(repaired)

    return repaired


def _patient_view_aliases(sql: str) -> set[str]:
    aliases: set[str] = set()

    # FROM reporting.vw_paciente_360 p / JOIN reporting.vw_pacientes AS p
    pattern = re.compile(
        r"\b(?:from|join)\s+(reporting\.vw_(?:paciente_360|pacientes))"
        r"(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        table = match.group(1).lower()
        if table not in PATIENT_SOURCE_VIEWS:
            continue
        alias = match.group(2)
        if alias and alias.lower() not in {"where", "join", "left", "right", "inner", "outer", "full", "on", "group", "order", "limit"}:
            aliases.add(alias)
        # También soporta consultas sin alias: reporting.vw_paciente_360.id_paciente
        aliases.add(table)
        aliases.add(table.split(".")[-1])

    return aliases


def _replace_patient_uuid_comparisons_for_qualifier(sql: str, qualifier: str) -> str:
    q = re.escape(qualifier)
    # p.id_paciente = 'uuid'  -> p.id_paciente_fuente = 'uuid'
    sql = re.sub(
        rf"\b{q}\s*\.\s*id_paciente\s*(=|<>|!=)\s*('(?:{UUID_RE})')",
        rf"{qualifier}.id_paciente_fuente \1 \2",
        sql,
        flags=re.IGNORECASE,
    )
    # p.id_paciente IN ('uuid', 'uuid') -> p.id_paciente_fuente IN (...)
    sql = re.sub(
        rf"\b{q}\s*\.\s*id_paciente\s+in\s*\(((?:\s*'(?:{UUID_RE})'\s*,?)+)\)",
        rf"{qualifier}.id_paciente_fuente IN (\1)",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _replace_unqualified_patient_uuid_comparison(sql: str) -> str:
    sql = re.sub(
        rf"(?<![\.\w])id_paciente\s*(=|<>|!=)\s*('(?:{UUID_RE})')",
        r"id_paciente_fuente \1 \2",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        rf"(?<![\.\w])id_paciente\s+in\s*\(((?:\s*'(?:{UUID_RE})'\s*,?)+)\)",
        r"id_paciente_fuente IN (\1)",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _find_select_blocks(sql: str) -> list[_SelectBlock]:
    blocks: list[_SelectBlock] = []
    i = 0
    depth = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state == "single":
            if ch == "'" and nxt == "'":
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue

        if state == "double":
            if ch == '"' and nxt == '"':
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue

        if state == "line_comment":
            if ch in "\r\n":
                state = None
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = None
                i += 2
                continue
            i += 1
            continue

        if state == "dollar":
            assert dollar_tag is not None
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            i += 1
            continue

        if ch == "'":
            state = "single"
            i += 1
            continue
        if ch == '"':
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue

        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue

        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue

        if _keyword_at(sql, i, "select"):
            end = _select_block_end(sql, i, depth)
            blocks.append(_SelectBlock(i, end, depth))
            i += len("select")
            continue

        i += 1

    return blocks


def _select_block_end(sql: str, select_pos: int, select_depth: int) -> int:
    i = select_pos + len("select")
    depth = select_depth
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state == "single":
            if ch == "'" and nxt == "'":
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue
        if state == "double":
            if ch == '"' and nxt == '"':
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue
        if state == "line_comment":
            if ch in "\r\n":
                state = None
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = None
                i += 2
                continue
            i += 1
            continue
        if state == "dollar":
            assert dollar_tag is not None
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            i += 1
            continue

        if ch == "'":
            state = "single"
            i += 1
            continue
        if ch == '"':
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue

        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue

        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            if depth == select_depth:
                return i
            depth = max(depth - 1, 0)
            i += 1
            continue

        if depth == select_depth and _keyword_at_any(sql, i, {"union", "intersect", "except"}):
            return i

        i += 1

    return len(sql)


def _repair_select_block(block_sql: str, absolute_depth: int) -> str:
    # Dentro del fragmento, el nivel superior del SELECT equivale a profundidad 0.
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql

    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + 6, depth=0)
    if from_pos < 0:
        return block_sql

    aliases = _select_aliases(block_sql[select_pos + 6 : from_pos])
    if not aliases:
        return block_sql

    order_pos = _find_top_level_keyword(block_sql, "order", start=from_pos + 4, depth=0)
    while order_pos >= 0:
        by_pos = _skip_ws(block_sql, order_pos + len("order"))
        if _keyword_at(block_sql, by_pos, "by"):
            break
        order_pos = _find_top_level_keyword(block_sql, "order", start=order_pos + 1, depth=0)
    if order_pos < 0:
        return block_sql

    order_expr_start = _skip_ws(block_sql, by_pos + len("by"))
    order_expr_end = _find_order_by_end(block_sql, order_expr_start)
    order_expr = block_sql[order_expr_start:order_expr_end]
    repaired_order_expr = _replace_alias_tokens(order_expr, aliases)

    if repaired_order_expr == order_expr:
        return block_sql
    return block_sql[:order_expr_start] + repaired_order_expr + block_sql[order_expr_end:]


def _select_aliases(select_list: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in _split_top_level_commas(select_list):
        parsed = _parse_alias(item)
        if not parsed:
            continue
        alias, expression = parsed
        if alias.lower() in aliases:
            continue
        aliases[alias.lower()] = expression
    return aliases


def _parse_alias(item: str) -> tuple[str, str] | None:
    text = item.strip()
    if not text:
        return None

    as_pos = _find_last_top_level_keyword(text, "as")
    if as_pos >= 0:
        expression = text[:as_pos].strip()
        alias_part = text[as_pos + 2 :].strip()
        alias = _clean_alias(alias_part)
        if expression and alias:
            return alias, expression
        return None

    # Soporte conservador para: expresion alias
    # No se aplica si el elemento parece una referencia simple sin alias.
    parts = text.rsplit(None, 1)
    if len(parts) == 2:
        expression, alias_part = parts
        alias = _clean_alias(alias_part)
        if alias and not _is_simple_identifier_or_qualified_name(expression):
            return alias, expression.strip()

    return None


def _clean_alias(value: str) -> str | None:
    alias = value.strip().rstrip(",")
    if alias.startswith('"') and alias.endswith('"') and len(alias) >= 2:
        inner = alias[1:-1].replace('""', '"')
        return inner if IDENTIFIER_RE.match(inner) else None
    return alias if IDENTIFIER_RE.match(alias) else None


def _replace_alias_tokens(order_expr: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return order_expr

    result: list[str] = []
    i = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(order_expr):
        ch = order_expr[i]
        nxt = order_expr[i + 1] if i + 1 < len(order_expr) else ""

        if state == "single":
            result.append(ch)
            if ch == "'" and nxt == "'":
                result.append(nxt)
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue

        if state == "double":
            result.append(ch)
            if ch == '"' and nxt == '"':
                result.append(nxt)
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue

        if state == "line_comment":
            result.append(ch)
            if ch in "\r\n":
                state = None
            i += 1
            continue

        if state == "block_comment":
            result.append(ch)
            if ch == "*" and nxt == "/":
                result.append(nxt)
                i += 2
                state = None
                continue
            i += 1
            continue

        if state == "dollar":
            assert dollar_tag is not None
            if order_expr.startswith(dollar_tag, i):
                result.append(dollar_tag)
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            result.append(ch)
            i += 1
            continue

        if ch == "'":
            result.append(ch)
            state = "single"
            i += 1
            continue
        if ch == '"':
            result.append(ch)
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            result.append(ch + nxt)
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            result.append(ch + nxt)
            state = "block_comment"
            i += 2
            continue

        tag = _dollar_tag_at(order_expr, i)
        if tag:
            result.append(tag)
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(order_expr) and (order_expr[j].isalnum() or order_expr[j] == "_"):
                j += 1
            token = order_expr[i:j]
            alias_expr = aliases.get(token.lower())
            prev_non_ws = _previous_non_ws(order_expr, i)
            next_non_ws = _next_non_ws(order_expr, j)
            if alias_expr and prev_non_ws != "." and next_non_ws != ".":
                result.append(f"({alias_expr})")
            else:
                result.append(token)
            i = j
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    i = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "single":
            if ch == "'" and nxt == "'":
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue
        if state == "double":
            if ch == '"' and nxt == '"':
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue
        if state == "line_comment":
            if ch in "\r\n":
                state = None
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = None
                i += 2
                continue
            i += 1
            continue
        if state == "dollar":
            assert dollar_tag is not None
            if text.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            i += 1
            continue

        if ch == "'":
            state = "single"
            i += 1
            continue
        if ch == '"':
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue

        tag = _dollar_tag_at(text, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
        i += 1

    parts.append(text[start:].strip())
    return parts


def _find_top_level_keyword(sql: str, keyword: str, *, start: int, depth: int) -> int:
    i = start
    current_depth = 0
    state: str | None = None
    dollar_tag: str | None = None
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if state == "single":
            if ch == "'" and nxt == "'":
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue
        if state == "double":
            if ch == '"' and nxt == '"':
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue
        if state == "line_comment":
            if ch in "\r\n":
                state = None
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = None
                i += 2
                continue
            i += 1
            continue
        if state == "dollar":
            assert dollar_tag is not None
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            i += 1
            continue

        if ch == "'":
            state = "single"
            i += 1
            continue
        if ch == '"':
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue
        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue

        if ch == "(":
            current_depth += 1
            i += 1
            continue
        if ch == ")":
            current_depth = max(current_depth - 1, 0)
            i += 1
            continue
        if current_depth == depth and _keyword_at(sql, i, keyword):
            return i
        i += 1
    return -1


def _find_last_top_level_keyword(sql: str, keyword: str) -> int:
    found = -1
    pos = _find_top_level_keyword(sql, keyword, start=0, depth=0)
    while pos >= 0:
        found = pos
        pos = _find_top_level_keyword(sql, keyword, start=pos + len(keyword), depth=0)
    return found


def _find_order_by_end(sql: str, start: int) -> int:
    boundaries = {"limit", "offset", "fetch", "for", "union", "intersect", "except"}
    i = start
    depth = 0
    state: str | None = None
    dollar_tag: str | None = None
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if state == "single":
            if ch == "'" and nxt == "'":
                i += 2
                continue
            if ch == "'":
                state = None
            i += 1
            continue
        if state == "double":
            if ch == '"' and nxt == '"':
                i += 2
                continue
            if ch == '"':
                state = None
            i += 1
            continue
        if state == "line_comment":
            if ch in "\r\n":
                state = None
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = None
                i += 2
                continue
            i += 1
            continue
        if state == "dollar":
            assert dollar_tag is not None
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = None
                dollar_tag = None
                continue
            i += 1
            continue
        if ch == "'":
            state = "single"
            i += 1
            continue
        if ch == '"':
            state = "double"
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue
        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue
        if depth == 0 and _keyword_at_any(sql, i, boundaries):
            return i
        i += 1
    return len(sql)


def _skip_ws(sql: str, pos: int) -> int:
    while pos < len(sql) and sql[pos].isspace():
        pos += 1
    return pos


def _previous_non_ws(sql: str, pos: int) -> str | None:
    i = pos - 1
    while i >= 0 and sql[i].isspace():
        i -= 1
    return sql[i] if i >= 0 else None


def _next_non_ws(sql: str, pos: int) -> str | None:
    i = pos
    while i < len(sql) and sql[i].isspace():
        i += 1
    return sql[i] if i < len(sql) else None


def _keyword_at_any(sql: str, pos: int, keywords: set[str]) -> bool:
    return any(_keyword_at(sql, pos, keyword) for keyword in keywords)


def _keyword_at(sql: str, pos: int, keyword: str) -> bool:
    end = pos + len(keyword)
    if end > len(sql):
        return False
    if sql[pos:end].lower() != keyword.lower():
        return False
    before = sql[pos - 1] if pos > 0 else ""
    after = sql[end] if end < len(sql) else ""
    if before and (before.isalnum() or before == "_"):
        return False
    if after and (after.isalnum() or after == "_"):
        return False
    return True


def _dollar_tag_at(sql: str, pos: int) -> str | None:
    if pos >= len(sql) or sql[pos] != "$":
        return None
    match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[pos:])
    return match.group(0) if match else None


def _is_simple_identifier_or_qualified_name(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?', value.strip()))

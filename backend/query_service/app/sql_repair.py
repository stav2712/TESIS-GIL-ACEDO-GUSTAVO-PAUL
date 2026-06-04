from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

PATIENT_DEMOGRAPHIC_VIEW = "reporting.vw_pacientes"
PATIENT_360_VIEW = "reporting.vw_paciente_360"
PATIENT_DEATH_VIEW = "reporting.vw_defunciones"
PROFESSIONAL_VIEW = "reporting.vw_profesionales"
ENCOUNTER_VIEW = "reporting.vw_encuentros"

EVENT_DETAIL_NAME_VIEWS = {
    "reporting.vw_encuentros",
    "reporting.vw_diagnosticos",
    "reporting.vw_procedimientos",
    "reporting.vw_medicamentos",
    "reporting.vw_mediciones",
    "reporting.vw_observaciones",
    "reporting.vw_dispositivos",
    "reporting.vw_alergias",
    "reporting.vw_planes_cuidado",
    "reporting.vw_inmunizaciones",
    "reporting.vw_estudios_imagen",
    "reporting.vw_suministros",
    "reporting.vw_cobertura_pagador",
    "reporting.vw_reclamos",
    "reporting.vw_reclamos_transacciones",
    "reporting.vw_eventos_clinicos",
}

# Vistas que exponen id_paciente_fuente y donde un UUID del usuario debe
# compararse contra ese identificador textual, no contra id_paciente entero.
PATIENT_SOURCE_ID_VIEWS = {
    PATIENT_DEMOGRAPHIC_VIEW,
    PATIENT_360_VIEW,
    PATIENT_DEATH_VIEW,
    *EVENT_DETAIL_NAME_VIEWS,
}

PROFESSIONAL_COLUMNS = {
    "id_profesional",
    "id_profesional_fuente",
    "nombre_profesional",
    "npi",
    "dea",
    "especialidad_estandar",
    "especialidad_fuente",
    "especialidad_nativa",
    "genero_estandar",
    "genero_fuente",
    "genero_nativo",
    "id_centro_atencion",
    "id_organizacion_fuente",
    "organizacion_nombre",
}

# Estas columnas NO existen en vw_pacientes. Si aparecen calificadas con el
# alias de pacientes y la consulta ya une encuentros, se resuelven mediante
# vw_profesionales.
PATIENT_ALIAS_INVALID_PROFESSIONAL_COLUMNS = PROFESSIONAL_COLUMNS - {
    "id_profesional",
    "id_centro_atencion",
}

# En vw_encuentros el nombre del profesional se expone como `profesional`, no
# como `nombre_profesional`. El identificador fuente y datos de especialidad
# viven en vw_profesionales.
ENCOUNTER_ALIAS_INVALID_PROFESSIONAL_COLUMNS = PROFESSIONAL_COLUMNS - {
    "id_profesional",
    "id_centro_atencion",
}

ENCOUNTER_LOCAL_PROFESSIONAL_COLUMN_MAP = {
    "nombre_profesional": "profesional",
}

SQL_KEYWORDS_AFTER_SOURCE = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "on",
    "group",
    "order",
    "limit",
    "offset",
    "fetch",
    "union",
    "intersect",
    "except",
    "having",
    "window",
    "qualify",
}

JOIN_KEYWORDS = {
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
}

CLAUSE_AFTER_SOURCE_RE = (
    r"WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|OFFSET|FETCH|UNION|INTERSECT|EXCEPT|"
    r"JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|FULL\s+JOIN|CROSS\s+JOIN"
)


@dataclass(frozen=True)
class _SelectBlock:
    start: int
    end: int
    depth: int


def repair_sql_for_dialect(sql: str, dialect: str) -> str:
    """
    Reparaciones conservadoras para SQL generado por el modelo.

    Se aplican solo en PostgreSQL, antes de guardrails y ejecución. No relajan
    seguridad ni convierten consultas no-SELECT; solo corrigen patrones claros
    de SQL que el modelo genera con columnas incompatibles con las vistas.
    """
    if (dialect or "").strip().lower() not in {"postgres", "postgresql"}:
        return sql

    repaired = repair_postgres_order_by_alias_expressions(sql)
    repaired = repair_patient_uuid_source_identifier(repaired)
    repaired = repair_patient_demographic_name_columns(repaired)
    repaired = repair_event_detail_name_columns(repaired)
    repaired = repair_professional_columns_from_patient_alias(repaired)
    repaired = repair_professional_columns_from_encounter_alias(repaired)
    return repaired


def repair_postgres_order_by_alias_expressions(sql: str) -> str:
    """
    PostgreSQL permite ORDER BY alias, pero no siempre alias dentro de
    expresiones como `ORDER BY total_a + total_b`. El modelo suele generar ese
    patrón en CTEs; lo reescribimos usando las expresiones reales del SELECT.
    """
    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_order_by_aliases(original)
        if repaired != original:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def repair_patient_uuid_source_identifier(sql: str) -> str:
    """
    Si el usuario pega un UUID de Synthea, debe compararse con
    id_paciente_fuente. id_paciente es entero interno. La reparación solo se
    aplica a literales con formato UUID; los IDs numéricos no se tocan.
    """
    aliases = _view_aliases(sql, PATIENT_SOURCE_ID_VIEWS)
    if not aliases:
        return sql

    repaired = sql
    for qualifier in sorted(aliases, key=len, reverse=True):
        repaired = _replace_patient_uuid_comparisons_for_qualifier(repaired, qualifier)

    # No calificado: se aplica solo si hay alguna vista paciente/evento en el
    # SQL y el literal claramente es UUID.
    repaired = _replace_unqualified_patient_uuid_comparison(repaired)
    return repaired


def repair_patient_demographic_name_columns(sql: str) -> str:
    """
    Corrige nombre_paciente cuando el modelo lo usa sobre vw_pacientes.
    En vw_pacientes la columna real es nombre_completo.
    """
    aliases = _view_aliases(sql, {PATIENT_DEMOGRAPHIC_VIEW})
    repaired = sql

    for qualifier in sorted(aliases, key=len, reverse=True):
        q = re.escape(qualifier)
        repaired = re.sub(
            rf"\b{q}\s*\.\s*nombre_paciente\b",
            f"{qualifier}.nombre_completo",
            repaired,
            flags=re.IGNORECASE,
        )

    for block in sorted(_find_select_blocks(repaired), key=lambda item: item.start, reverse=True):
        original = repaired[block.start : block.end]
        if not _simple_select_from_only_view(original, PATIENT_DEMOGRAPHIC_VIEW):
            continue
        fixed = _replace_unqualified_identifier(original, "nombre_paciente", "nombre_completo")
        if fixed != original:
            repaired = repaired[: block.start] + fixed + repaired[block.end :]

    return repaired


def repair_event_detail_name_columns(sql: str) -> str:
    """
    Corrige nombre_completo cuando el modelo lo usa sobre vistas de eventos o
    detalle. En esas vistas la columna expuesta es nombre_paciente.
    """
    aliases = _view_aliases(sql, EVENT_DETAIL_NAME_VIEWS)
    repaired = sql

    for qualifier in sorted(aliases, key=len, reverse=True):
        q = re.escape(qualifier)
        repaired = re.sub(
            rf"\b{q}\s*\.\s*nombre_completo\b",
            f"{qualifier}.nombre_paciente",
            repaired,
            flags=re.IGNORECASE,
        )

    for block in sorted(_find_select_blocks(repaired), key=lambda item: item.start, reverse=True):
        original = repaired[block.start : block.end]
        if _simple_select_single_detail_view(original) is None:
            continue
        fixed = _replace_unqualified_identifier(original, "nombre_completo", "nombre_paciente")
        if fixed != original:
            repaired = repaired[: block.start] + fixed + repaired[block.end :]

    return repaired


def repair_professional_columns_from_patient_alias(sql: str) -> str:
    """
    Repara el patrón donde el modelo usa el alias de vw_pacientes para columnas
    de profesional en consultas que ya unen vw_encuentros.

    Ejemplo que se corrige:
      p.id_profesional_fuente, p.nombre_profesional, p.especialidad_estandar
    cuando `p` es vw_pacientes y existe `JOIN reporting.vw_encuentros e`.
    """
    if re.search(r"\breporting\.vw_profesionales\b", sql, flags=re.IGNORECASE):
        return sql

    patient_aliases = _view_aliases(sql, {PATIENT_DEMOGRAPHIC_VIEW})
    encounter_aliases = _view_aliases(sql, {ENCOUNTER_VIEW})
    if not patient_aliases or not encounter_aliases:
        return sql

    patient_alias = _alias_with_invalid_professional_columns(
        sql,
        patient_aliases,
        PATIENT_ALIAS_INVALID_PROFESSIONAL_COLUMNS,
    )
    if patient_alias is None:
        return sql

    encounter_alias = _preferred_alias(encounter_aliases, ENCOUNTER_VIEW)
    if encounter_alias is None:
        return sql

    professional_alias = _unique_alias(sql, "prof_fix")
    repaired = _replace_professional_column_references(sql, patient_alias, professional_alias)
    return _insert_professional_join(repaired, encounter_alias, professional_alias, join_type="JOIN")


def repair_professional_columns_from_encounter_alias(sql: str) -> str:
    """
    Repara columnas de profesional que el modelo atribuye erróneamente a
    reporting.vw_encuentros.

    Casos cubiertos:
    - e.nombre_profesional -> e.profesional
    - e.id_profesional_fuente -> prof_fix.id_profesional_fuente + LEFT JOIN a
      reporting.vw_profesionales

    Es deliberadamente conservador: solo toca columnas con alias de
    vw_encuentros o columnas no calificadas cuando el SELECT usa únicamente
    vw_encuentros como fuente.
    """
    encounter_aliases = _view_aliases(sql, {ENCOUNTER_VIEW})
    if not encounter_aliases:
        return sql

    repaired = sql
    professional_aliases = _view_aliases(repaired, {PROFESSIONAL_VIEW})
    professional_alias = _preferred_alias(professional_aliases, PROFESSIONAL_VIEW)
    should_add_professional_join = False

    aliases_needing_nombre_alias: set[str] = set()
    for encounter_alias in sorted(encounter_aliases, key=len, reverse=True):
        before = repaired
        repaired, needs_join, renamed_nombre = _replace_encounter_professional_column_references(
            repaired,
            encounter_alias,
            professional_alias,
        )
        if renamed_nombre:
            aliases_needing_nombre_alias.add(encounter_alias)
        should_add_professional_join = should_add_professional_join or needs_join
        if needs_join and professional_alias is None:
            professional_alias = _unique_alias(repaired, "prof_fix")
            # Reaplica las columnas que necesitan vw_profesionales con el alias
            # ya decidido. La primera pasada solo detecta si hacía falta unir.
            repaired, _, renamed_nombre_second_pass = _replace_encounter_professional_column_references(
                repaired,
                encounter_alias,
                professional_alias,
            )
            if renamed_nombre_second_pass:
                aliases_needing_nombre_alias.add(encounter_alias)

    for encounter_alias in aliases_needing_nombre_alias:
        repaired = _alias_encounter_profesional_select_items(repaired, encounter_alias)

    if should_add_professional_join and professional_alias:
        encounter_alias = _preferred_alias(_view_aliases(repaired, {ENCOUNTER_VIEW}), ENCOUNTER_VIEW)
        if encounter_alias:
            repaired = _insert_professional_join(
                repaired,
                encounter_alias,
                professional_alias,
                join_type="LEFT JOIN",
            )

    return repaired


def _replace_patient_uuid_comparisons_for_qualifier(sql: str, qualifier: str) -> str:
    q = re.escape(qualifier)
    sql = re.sub(
        rf"\b{q}\s*\.\s*id_paciente\s*(=|<>|!=)\s*('(?:{UUID_RE})')",
        rf"{qualifier}.id_paciente_fuente \1 \2",
        sql,
        flags=re.IGNORECASE,
    )
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


def _alias_with_invalid_professional_columns(
    sql: str,
    aliases: set[str],
    invalid_columns: set[str],
) -> str | None:
    for alias in sorted(aliases, key=len, reverse=True):
        q = re.escape(alias)
        for column in sorted(invalid_columns, key=len, reverse=True):
            if re.search(rf"\b{q}\s*\.\s*{re.escape(column)}\b", sql, flags=re.IGNORECASE):
                return alias
    return None


def _replace_professional_column_references(sql: str, patient_alias: str, professional_alias: str) -> str:
    repaired = sql
    q = re.escape(patient_alias)
    for column in sorted(PROFESSIONAL_COLUMNS, key=len, reverse=True):
        repaired = re.sub(
            rf"\b{q}\s*\.\s*{re.escape(column)}\b",
            f"{professional_alias}.{column}",
            repaired,
            flags=re.IGNORECASE,
        )
    return repaired


def _replace_encounter_professional_column_references(
    sql: str,
    encounter_alias: str,
    professional_alias: str | None,
) -> tuple[str, bool, bool]:
    repaired = sql
    needs_join = False
    renamed_nombre = False
    q = re.escape(encounter_alias)

    for wrong, right in ENCOUNTER_LOCAL_PROFESSIONAL_COLUMN_MAP.items():
        pattern = rf"\b{q}\s*\.\s*{re.escape(wrong)}\b"
        if re.search(pattern, repaired, flags=re.IGNORECASE):
            renamed_nombre = True
            repaired = re.sub(
                pattern,
                f"{encounter_alias}.{right}",
                repaired,
                flags=re.IGNORECASE,
            )

    for column in sorted(ENCOUNTER_ALIAS_INVALID_PROFESSIONAL_COLUMNS, key=len, reverse=True):
        if column in ENCOUNTER_LOCAL_PROFESSIONAL_COLUMN_MAP:
            continue
        pattern = rf"\b{q}\s*\.\s*{re.escape(column)}\b"
        if not re.search(pattern, repaired, flags=re.IGNORECASE):
            continue
        needs_join = True
        if professional_alias:
            repaired = re.sub(
                pattern,
                f"{professional_alias}.{column}",
                repaired,
                flags=re.IGNORECASE,
            )

    return repaired, needs_join, renamed_nombre


def _alias_encounter_profesional_select_items(sql: str, encounter_alias: str) -> str:
    """
    Si el modelo seleccionó e.nombre_profesional, la reparación lo convierte a
    e.profesional. En una lista SELECT conviene conservar el nombre de salida
    `nombre_profesional`, sobre todo cuando una consulta externa ordena por esa
    columna del CTE.
    """
    result = sql
    expression = rf"{re.escape(encounter_alias)}\s*\.\s*profesional"

    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        block_sql = result[block.start : block.end]
        select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
        if select_pos < 0:
            continue
        from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
        if from_pos < 0:
            continue

        select_list = block_sql[select_pos + len("select") : from_pos]
        items = _split_top_level_commas(select_list)
        if not items:
            continue

        changed = False
        fixed_items: list[str] = []
        for item in items:
            stripped = item.strip()
            distinct_prefix = ""
            expr = stripped
            distinct_match = re.match(r"(?is)^distinct\s+(.+)$", stripped)
            if distinct_match:
                distinct_prefix = "DISTINCT "
                expr = distinct_match.group(1).strip()

            if re.fullmatch(expression, expr, flags=re.IGNORECASE):
                fixed_items.append(f"{distinct_prefix}{encounter_alias}.profesional AS nombre_profesional")
                changed = True
            else:
                fixed_items.append(stripped)

        if changed:
            fixed_select_list = "\n " + ",\n ".join(fixed_items) + "\n"
            fixed_block = block_sql[: select_pos + len("select")] + fixed_select_list + block_sql[from_pos:]
            result = result[: block.start] + fixed_block + result[block.end :]

    return result


def _insert_professional_join(
    sql: str,
    encounter_alias: str,
    professional_alias: str,
    *,
    join_type: str = "LEFT JOIN",
) -> str:
    if re.search(
        rf"\b{re.escape(PROFESSIONAL_VIEW)}\s+(?:AS\s+)?{re.escape(professional_alias)}\b",
        sql,
        flags=re.IGNORECASE,
    ):
        return sql

    join_sql = (
        f"\n{join_type} {PROFESSIONAL_VIEW} {professional_alias}"
        f"\n     ON {professional_alias}.id_profesional = {encounter_alias}.id_profesional"
    )
    q = re.escape(encounter_alias)

    # Caso 1: vw_encuentros aparece como JOIN y por tanto ya tiene ON. Se
    # inserta después del ON completo.
    join_pattern = re.compile(
        rf"(\bJOIN\s+{re.escape(ENCOUNTER_VIEW)}\s+(?:AS\s+)?{q}\b\s+ON\s+.*?)"
        rf"(?=\s+(?:{CLAUSE_AFTER_SOURCE_RE})\b|\s*\)|\s*$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    repaired, count = join_pattern.subn(lambda match: match.group(1).rstrip() + join_sql, sql, count=1)
    if count:
        return repaired

    # Caso 2: vw_encuentros es la fuente principal con alias explícito.
    from_with_alias_pattern = re.compile(
        rf"(\bFROM\s+{re.escape(ENCOUNTER_VIEW)}\s+(?:AS\s+)?{q}\b)"
        rf"(?=\s+(?:{CLAUSE_AFTER_SOURCE_RE})\b|\s*\)|\s*$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    repaired, count = from_with_alias_pattern.subn(lambda match: match.group(1).rstrip() + join_sql, sql, count=1)
    if count:
        return repaired

    # Caso 3: fuente principal sin alias. PostgreSQL permite referirse a la
    # relación como vw_encuentros.columna cuando no se declaró alias.
    if encounter_alias.lower() in {ENCOUNTER_VIEW.lower(), ENCOUNTER_VIEW.split(".")[-1].lower()}:
        from_without_alias_pattern = re.compile(
            rf"(\bFROM\s+{re.escape(ENCOUNTER_VIEW)}\b)"
            rf"(?=\s+(?:{CLAUSE_AFTER_SOURCE_RE})\b|\s*\)|\s*$)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        repaired, count = from_without_alias_pattern.subn(lambda match: match.group(1).rstrip() + join_sql, sql, count=1)
        if count:
            return repaired

    return sql


def _view_aliases(sql: str, target_views: set[str]) -> set[str]:
    aliases: set[str] = set()
    pattern = re.compile(
        r"\b(?:from|join)\s+(reporting\.vw_[A-Za-z0-9_]+)"
        r"(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
        flags=re.IGNORECASE,
    )
    target_views_l = {view.lower() for view in target_views}
    for match in pattern.finditer(sql):
        table = match.group(1).lower()
        if table not in target_views_l:
            continue
        alias = match.group(2)
        aliases.add(table)
        aliases.add(table.split(".")[-1])
        if alias and alias.lower() not in SQL_KEYWORDS_AFTER_SOURCE:
            aliases.add(alias)
    return aliases


def _preferred_alias(aliases: set[str], view_name: str) -> str | None:
    view_short = view_name.split(".")[-1]
    explicit = [item for item in aliases if item.lower() not in {view_name.lower(), view_short.lower()}]
    if explicit:
        return sorted(explicit, key=len)[0]
    if view_short in aliases:
        return view_short
    if view_name in aliases:
        return view_name
    return sorted(aliases, key=len)[0] if aliases else None


def _unique_alias(sql: str, base: str) -> str:
    existing = {m.group(0).lower() for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)}
    alias = base
    suffix = 2
    while alias.lower() in existing:
        alias = f"{base}_{suffix}"
        suffix += 1
    return alias


def _simple_select_single_detail_view(block_sql: str) -> str | None:
    for view_name in EVENT_DETAIL_NAME_VIEWS:
        if _simple_select_from_only_view(block_sql, view_name):
            return view_name
    return None


def _simple_select_from_only_view(block_sql: str, view_name: str) -> bool:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return False
    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return False

    first_table_match = re.match(
        r"\s+(reporting\.vw_[A-Za-z0-9_]+)(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
        block_sql[from_pos + len("from") :],
        flags=re.IGNORECASE,
    )
    if not first_table_match:
        return False
    if first_table_match.group(1).lower() != view_name:
        return False

    join_pos = _find_top_level_keyword(block_sql, "join", start=from_pos + len("from"), depth=0)
    return join_pos < 0


def _repair_select_block_order_by_aliases(block_sql: str) -> str:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql
    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return block_sql

    aliases = _select_aliases(block_sql[select_pos + len("select") : from_pos])
    if not aliases:
        return block_sql

    order_pos = _find_order_by(block_sql, start=from_pos + len("from"), depth=0)
    if order_pos < 0:
        return block_sql

    by_pos = _skip_ws(block_sql, order_pos + len("order"))
    if not _keyword_at(block_sql, by_pos, "by"):
        return block_sql

    order_expr_start = _skip_ws(block_sql, by_pos + len("by"))
    order_expr_end = _find_order_by_end(block_sql, order_expr_start)
    order_expr = block_sql[order_expr_start:order_expr_end]
    repaired_order_expr = _replace_aliases_in_order_expr(order_expr, aliases)
    if repaired_order_expr == order_expr:
        return block_sql
    return block_sql[:order_expr_start] + repaired_order_expr + block_sql[order_expr_end:]


def _select_aliases(select_list_sql: str) -> dict[str, str]:
    """
    Extrae aliases reales del SELECT de forma conservadora.

    Importante: en `SELECT DISTINCT id_paciente, ...`, `DISTINCT` es un
    modificador del SELECT, no una expresión. Antes se interpretaba
    erróneamente como si `id_paciente` fuera alias de `DISTINCT`, lo que podía
    convertir `ORDER BY id_paciente` en `ORDER BY (DISTINCT)`.
    """
    aliases: dict[str, str] = {}
    normalized_select_list = _strip_select_modifier(select_list_sql)

    for item in _split_top_level_commas(normalized_select_list):
        item = item.strip()
        if not item:
            continue

        match = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item, flags=re.IGNORECASE)
        expr = item
        alias = None
        if match:
            alias = match.group(1)
            expr = item[: match.start()].strip()
        else:
            implicit = re.match(r"(?is)^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item)
            if implicit:
                possible_expr = implicit.group(1).strip()
                possible_alias = implicit.group(2)
                if _is_safe_implicit_alias(possible_expr, possible_alias):
                    alias = possible_alias
                    expr = possible_expr

        if alias and IDENTIFIER_RE.match(alias):
            aliases[alias.lower()] = expr.strip()
    return aliases


def _strip_select_modifier(select_list_sql: str) -> str:
    text = select_list_sql.lstrip()
    prefix_len = len(select_list_sql) - len(text)
    if not _keyword_at(text, 0, "distinct") and not _keyword_at(text, 0, "all"):
        return select_list_sql

    if _keyword_at(text, 0, "all"):
        return select_list_sql[:prefix_len] + text[len("all") :].lstrip()

    idx = _skip_ws(text, len("distinct"))
    if not _keyword_at(text, idx, "on"):
        return select_list_sql[:prefix_len] + text[idx:].lstrip()

    idx = _skip_ws(text, idx + len("on"))
    if idx >= len(text) or text[idx] != "(":
        return select_list_sql[:prefix_len] + text[idx:].lstrip()

    end = _matching_paren_end(text, idx)
    if end is None:
        return select_list_sql[:prefix_len] + text[idx:].lstrip()
    return select_list_sql[:prefix_len] + text[end:].lstrip()


def _matching_paren_end(text: str, open_pos: int) -> int | None:
    depth = 0
    i = open_pos
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(text):
        if state is not None:
            state, dollar_tag, jumped = _advance_string_or_comment_state(text, i, state, dollar_tag)
            i = jumped if jumped is not None else i + 1
            continue

        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        tag = _dollar_tag_at(text, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1

    return None


def _is_safe_implicit_alias(expr: str, alias: str) -> bool:
    alias_l = alias.lower()
    expr_l = expr.strip().lower()
    if alias_l in SQL_KEYWORDS_AFTER_SOURCE:
        return False
    if expr_l in {"distinct", "all"} | SQL_KEYWORDS_AFTER_SOURCE:
        return False
    if _is_simple_column_reference(expr):
        return False
    return _looks_like_nontrivial_expression(expr)


def _is_simple_column_reference(expr: str) -> bool:
    return bool(re.fullmatch(r'"?[A-Za-z_][A-Za-z0-9_]*"?(?:\s*\.\s*"?[A-Za-z_][A-Za-z0-9_]*"?)*', expr.strip()))


def _looks_like_nontrivial_expression(expr: str) -> bool:
    stripped = expr.strip()
    if not stripped:
        return False
    return bool(
        re.search(r"\)\s*$", stripped)
        or "::" in stripped
        or re.search(r"\bcase\b.+\bend\b", stripped, flags=re.IGNORECASE | re.DOTALL)
        or re.search(r"[+*/-]", stripped)
        or re.search(r"'(?:''|[^'])*'", stripped)
    )


def _replace_aliases_in_order_expr(order_expr: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return order_expr

    def replacer(token: str, prev_ch: str, next_ch: str) -> str:
        if token.lower() in aliases and prev_ch != "." and next_ch != ".":
            return f"({aliases[token.lower()]})"
        return token

    return _replace_identifier_tokens(order_expr, replacer)


def _replace_unqualified_identifier(sql: str, old: str, new: str) -> str:
    old_l = old.lower()

    def replacer(token: str, prev_ch: str, next_ch: str) -> str:
        if token.lower() == old_l and prev_ch != "." and next_ch != ".":
            return new
        return token

    return _replace_identifier_tokens(sql, replacer)


def _replace_identifier_tokens(sql: str, replacer: Callable[[str, str, str], str]) -> str:
    result: list[str] = []
    i = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state is not None:
            new_state, new_tag, jumped = _advance_string_or_comment_state(sql, i, state, dollar_tag)
            result.append(sql[i:jumped] if jumped is not None else ch)
            if jumped is not None:
                i = jumped
            else:
                i += 1
            state, dollar_tag = new_state, new_tag
            continue

        tag = _dollar_tag_at(sql, i)
        if tag:
            result.append(tag)
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            token = sql[i:j]
            prev_non_ws = _previous_non_ws(sql, i)
            next_non_ws = _next_non_ws(sql, j)
            result.append(replacer(token, prev_non_ws, next_non_ws))
            i = j
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _find_select_blocks(sql: str) -> list[_SelectBlock]:
    blocks: list[_SelectBlock] = []
    i = 0
    depth = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        if state is not None:
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql, i, state, dollar_tag)
            i = jumped if jumped is not None else i + 1
            continue

        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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
        if state is not None:
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql, i, state, dollar_tag)
            i = jumped if jumped is not None else i + 1
            continue

        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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


def _advance_string_or_comment_state(
    sql: str,
    i: int,
    state: str,
    dollar_tag: str | None,
) -> tuple[str | None, str | None, int | None]:
    ch = sql[i]
    nxt = sql[i + 1] if i + 1 < len(sql) else ""

    if state == "single":
        if ch == "'" and nxt == "'":
            return state, dollar_tag, i + 2
        if ch == "'":
            return None, dollar_tag, i + 1
        return state, dollar_tag, None
    if state == "double":
        if ch == '"' and nxt == '"':
            return state, dollar_tag, i + 2
        if ch == '"':
            return None, dollar_tag, i + 1
        return state, dollar_tag, None
    if state == "line_comment":
        if ch in "\r\n":
            return None, dollar_tag, i + 1
        return state, dollar_tag, None
    if state == "block_comment":
        if ch == "*" and nxt == "/":
            return None, dollar_tag, i + 2
        return state, dollar_tag, None
    if state == "dollar":
        if dollar_tag is not None and sql.startswith(dollar_tag, i):
            return None, None, i + len(dollar_tag)
        return state, dollar_tag, None
    return state, dollar_tag, None


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    i = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(text):
        if state is not None:
            state, dollar_tag, jumped = _advance_string_or_comment_state(text, i, state, dollar_tag)
            i = jumped if jumped is not None else i + 1
            continue

        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        tag = _dollar_tag_at(text, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
        i += 1

    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _find_order_by(block_sql: str, start: int, depth: int) -> int:
    order_pos = _find_top_level_keyword(block_sql, "order", start=start, depth=depth)
    while order_pos >= 0:
        by_pos = _skip_ws(block_sql, order_pos + len("order"))
        if _keyword_at(block_sql, by_pos, "by"):
            return order_pos
        order_pos = _find_top_level_keyword(block_sql, "order", start=order_pos + 1, depth=depth)
    return -1


def _find_order_by_end(block_sql: str, start: int) -> int:
    candidates = []
    for keyword in ("limit", "offset", "fetch", "union", "intersect", "except"):
        pos = _find_top_level_keyword(block_sql, keyword, start=start, depth=0)
        if pos >= 0:
            candidates.append(pos)
    return min(candidates) if candidates else len(block_sql)


def _find_top_level_keyword(sql: str, keyword: str, *, start: int, depth: int) -> int:
    i = start
    current_depth = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        if state is not None:
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql, i, state, dollar_tag)
            i = jumped if jumped is not None else i + 1
            continue

        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        tag = _dollar_tag_at(sql, i)
        if tag:
            state = "dollar"
            dollar_tag = tag
            i += len(tag)
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


def _keyword_at_any(sql: str, pos: int, keywords: set[str]) -> bool:
    return any(_keyword_at(sql, pos, keyword) for keyword in keywords)


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


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _previous_non_ws(s: str, i: int) -> str:
    j = i - 1
    while j >= 0 and s[j].isspace():
        j -= 1
    return s[j] if j >= 0 else ""


def _next_non_ws(s: str, i: int) -> str:
    j = i
    while j < len(s) and s[j].isspace():
        j += 1
    return s[j] if j < len(s) else ""


def _dollar_tag_at(sql: str, i: int) -> str | None:
    match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
    return match.group(0) if match else None

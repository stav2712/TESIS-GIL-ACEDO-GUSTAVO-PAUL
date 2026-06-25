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

# Vistas que exponen id_paciente y pueden funcionar como filtros de existencia
# contra reporting.vw_pacientes. Esta lista está alineada con el esquema de
# vistas entregado y se mantiene explícita para no reescribir vistas nuevas o
# desconocidas por accidente.
PATIENT_EXISTENCE_FILTER_VIEWS = {
    PATIENT_DEATH_VIEW,
    *EVENT_DETAIL_NAME_VIEWS,
}

# Columnas reales de reporting.vw_pacientes. Solo se usan para validar que una
# proyección sin alias pertenece al paciente antes de optimizar JOINs de
# detalle. Si una columna no está aquí, la optimización se desactiva.
PATIENT_DEMOGRAPHIC_COLUMNS = {
    "id_paciente",
    "id_paciente_fuente",
    "prefix",
    "primer_nombre",
    "segundo_nombre",
    "apellido",
    "suffix",
    "apellido_soltera",
    "nombre_completo",
    "gender_concept_id",
    "genero_estandar",
    "genero_fuente",
    "race_concept_id",
    "raza_estandar",
    "raza_fuente",
    "ethnicity_concept_id",
    "etnia_estandar",
    "etnia_fuente",
    "estado_civil",
    "lugar_nacimiento",
    "year_of_birth",
    "month_of_birth",
    "day_of_birth",
    "fecha_nacimiento_aprox",
    "fecha_nacimiento_nativa",
    "fecha_nacimiento",
    "edad_actual",
    "fecha_fallecimiento",
    "fallecido",
    "id_ubicacion",
    "direccion",
    "ciudad",
    "estado",
    "condado",
    "zip",
    "pais_estandar",
    "pais_fuente",
    "latitud",
    "longitud",
    "id_profesional",
    "id_centro_atencion",
    "gastos_salud_acumulados",
    "cobertura_salud_acumulada",
    "ingreso_anual",
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


@dataclass(frozen=True)
class _PatientFilterJoin:
    view_name: str
    alias: str
    on_condition: str


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
    repaired = repair_misplaced_joins_after_where(repaired)
    repaired = repair_patient_same_detail_filter_joins_to_grouped_having(repaired)
    repaired = repair_patient_filter_joins_to_exists(repaired)
    repaired = repair_patient_uuid_source_identifier(repaired)
    repaired = repair_patient_demographic_name_columns(repaired)
    repaired = repair_event_detail_name_columns(repaired)
    repaired = repair_professional_columns_from_patient_alias(repaired)
    repaired = repair_professional_columns_from_encounter_alias(repaired)
    repaired = repair_unqualified_professional_columns_from_encounter_source(repaired)
    return repaired


def repair_postgres_order_by_alias_expressions(sql: str) -> str:
    """
    PostgreSQL permite ORDER BY alias, pero no siempre alias dentro de
    expresiones como `ORDER BY total_a + total_b`. El modelo suele generar ese
    patrón en CTEs; lo reescribimos usando las expresiones reales del SELECT.
    """
    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item:
item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_order_by_aliases(original)
        if repaired != original:

            result = result[: block.start] + repaired + result[block.end :]
    return result


def repair_misplaced_joins_after_where(sql: str) -> str:
    """
    Repara un patrón inválido y frecuente en NL2SQL: el modelo agrega un JOIN
    después de una cláusula WHERE y luego abre un segundo WHERE.

    Ejemplo inválido:
      ... FROM pacientes p JOIN diagnosticos d ON ...
      WHERE condicion_d
      JOIN diagnosticos d2 ON ...
      WHERE condicion_d2

    Reparación conservadora:
      ... FROM pacientes p JOIN diagnosticos d ON ...
      JOIN diagnosticos d2 ON ...
      WHERE condicion_d AND condicion_d2

    No se cambia seguridad ni permisos: solo se reordena un JOIN top-level que
    ya estaba en el SQL generado y se fusiona el segundo WHERE como AND.
    """
    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_misplaced_joins_after_where(original)
        if repaired != original:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def _repair_select_block_misplaced_joins_after_where(block_sql: str) -> str:
    """
    Repara todos los JOINs top-level que el modelo haya colocado dentro de un
    WHERE de un mismo SELECT.

    La versión anterior reparaba iterativamente un JOIN por pasada. Funcionaba
    para el caso común de 1 JOIN mal ubicado, pero podía dejar SQL inválido si
    venían varios JOIN/WHERE encadenados. Esta versión parsea la secuencia
    completa de forma conservadora:

      WHERE condicion_1
      JOIN vista_2 alias_2 ON ...
      WHERE condicion_2
      JOIN vista_3 alias_3 ON ...
      WHERE condicion_3

    y la convierte a:

      JOIN vista_2 alias_2 ON ...
      JOIN vista_3 alias_3 ON ...
      WHERE (condicion_1) AND (condicion_2) AND (condicion_3)

    Si encuentra algo dudoso, devuelve el bloque original.
    """
    fixed = _repair_all_misplaced_joins_after_where(block_sql)
    return fixed


def _repair_all_misplaced_joins_after_where(block_sql: str) -> str:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql
    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return block_sql
    first_where_pos = _find_top_level_keyword(block_sql, "where", start=from_pos + len("from"), depth=0)
    if first_where_pos < 0:
        return block_sql

    first_condition_start = _skip_ws(block_sql, first_where_pos + len("where"))
    first_misplaced_join_pos = _find_first_top_level_join_start(block_sql, start=first_condition_start, depth=0)
    if first_misplaced_join_pos < 0:
        return block_sql
    if first_misplaced_join_pos <= first_where_pos:
        return block_sql

    first_condition = _clean_where_condition_fragment(block_sql[first_condition_start:first_misplaced_join_pos])
    if not first_condition:
        return block_sql

    conditions: list[str] = [first_condition]
    join_fragments: list[str] = []
    cursor = first_misplaced_join_pos

    # Límite deliberado: cubre casos muy grandes sin permitir bucles abiertos
    # ni reparaciones masivas ante SQL demasiado extraño.
    for _ in range(12):
        cursor = _skip_ws(block_sql, cursor)
        if cursor >= len(block_sql):
            break

        join_pos = _join_keyword_start_at(block_sql, cursor)
        if join_pos != cursor:
            break

        join_end = _find_misplaced_join_end(block_sql, join_pos)
        if join_end <= join_pos:
            return block_sql

        join_fragment = block_sql[join_pos:join_end].strip()
        if not _looks_like_safe_reporting_join_fragment(join_fragment):
            return block_sql
        join_fragments.append(join_fragment)

        cursor = _skip_ws(block_sql, join_end)
        if cursor >= len(block_sql):
            break

        if _keyword_at(block_sql, cursor, "where"):
            condition_start = _skip_ws(block_sql, cursor + len("where"))
            condition_end = _find_condition_end_after_where_or_join(block_sql, condition_start)
            condition = _clean_where_condition_fragment(block_sql[condition_start:condition_end])
            if not condition:
                return block_sql
            conditions.append(condition)
            cursor = condition_end
            continue

        # Si después del JOIN viene ORDER/GROUP/LIMIT/etc., se permite mover el
        # JOIN sin agregar condición nueva. Cualquier otro token se considera
        # demasiado ambiguo para reparar.
        if _is_clause_boundary_at(block_sql, cursor):
            break
        return block_sql
    else:
        # Si agotó 12 iteraciones todavía había JOINs, mejor no arriesgar una
        # reparación parcial.
        return block_sql

    if not join_fragments:
        return block_sql

    trailing = block_sql[cursor:]
    if trailing and not trailing[0].isspace():
        trailing = "\n" + trailing

    merged_condition = "\n  AND ".join(
        _parenthesize_condition_for_where_merge(condition)
        for condition in conditions
    )

    before_where = block_sql[:first_where_pos].rstrip()
    return (
        f"{before_where}\n"
        + "\n".join(join_fragments)
        + f"\nWHERE {merged_condition}"
        + trailing
    )


def _repair_one_misplaced_join_after_where(block_sql: str) -> str:
    """Compatibilidad interna: delega en la reparación multi-JOIN."""
    return _repair_all_misplaced_joins_after_where(block_sql)


def _join_keyword_start_at(sql: str, pos: int) -> int:
    """Devuelve pos si ahí empieza JOIN/LEFT JOIN/etc.; si no, -1."""
    for keyword in ("join", "left", "right", "inner", "full", "cross"):
        if not _keyword_at(sql, pos, keyword):
            continue
        if keyword == "join":
            return pos
        after_join_type = _skip_ws(sql, pos + len(keyword))
        if _keyword_at(sql, after_join_type, "join"):
            return pos
    return -1


def _find_condition_end_after_where_or_join(sql: str, condition_start: int) -> int:
    candidates: list[int] = []
    join_pos = _find_first_top_level_join_start(sql, start=condition_start, depth=0)
    if join_pos >= 0:
        candidates.append(join_pos)
    for keyword in ("group", "having", "order", "limit", "offset", "fetch", "union", "intersect", "except"):
        pos = _find_top_level_keyword(sql, keyword, start=condition_start, depth=0)
        if pos >= 0:
            candidates.append(pos)
    return min(candidates) if candidates else len(sql)


def _is_clause_boundary_at(sql: str, pos: int) -> bool:
    return any(
        _keyword_at(sql, pos, keyword)
        for keyword in ("group", "having", "order", "limit", "offset", "fetch", "union", "intersect", "except")
    )


def _find_first_top_level_join_start(sql: str, *, start: int, depth: int) -> int:
    candidates: list[int] = []
    for keyword in ("join", "left", "right", "inner", "full", "cross"):
        pos = _find_top_level_keyword(sql, keyword, start=start, depth=depth)
        if pos >= 0:
            if keyword == "join":
                candidates.append(pos)
            else:
                after_join_type = _skip_ws(sql, pos + len(keyword))
                if _keyword_at(sql, after_join_type, "join"):
                    candidates.append(pos)
    return min(candidates) if candidates else -1


def _find_misplaced_join_end(sql: str, join_pos: int) -> int:
    candidates: list[int] = []
    for keyword in ("where", "group", "having", "order", "limit", "offset", "fetch", "union", "intersect", "except"):
        pos = _find_top_level_keyword(sql, keyword, start=join_pos + 1, depth=0)
        if pos >= 0:
            candidates.append(pos)
    return min(candidates) if candidates else len(sql)


def _find_condition_end_after_where(sql: str, condition_start: int) -> int:
    candidates: list[int] = []
    for keyword in ("group", "having", "order", "limit", "offset", "fetch", "union", "intersect", "except"):
        pos = _find_top_level_keyword(sql, keyword, start=condition_start, depth=0)
        if pos >= 0:
            candidates.append(pos)
    return min(candidates) if candidates else len(sql)


def _clean_where_condition_fragment(condition: str) -> str:
    text = condition.strip()
    text = re.sub(r"(?is)\s+(?:and|or)\s*$", "", text).strip()
    return text


def _parenthesize_condition_for_where_merge(condition: str) -> str:
    """
    Envuelve condiciones al fusionar WHERE para preservar precedencia lógica.

    Ejemplo: `a OR b` unido con `c` debe quedar `(a OR b) AND (c)`, no
    `a OR b AND c`, porque PostgreSQL evalúa AND antes que OR.
    """
    text = condition.strip()
    if not text:
        return text
    if text.startswith("(") and text.endswith(")") and _enclosing_parentheses_cover_entire_text(text):
        return text
    return f"({text})"


def _enclosing_parentheses_cover_entire_text(text: str) -> bool:
    if not (text.startswith("(") and text.endswith(")")):
        return False
    closing = _find_matching_paren(text, 0)
    return closing == len(text) - 1


def _looks_like_safe_reporting_join_fragment(join_fragment: str) -> bool:
    if ";" in join_fragment:
        return False
    if not re.match(r"(?is)^(?:join|left\s+join|right\s+join|inner\s+join|full\s+join|cross\s+join)\s+reporting\.vw_[A-Za-z0-9_]+\b", join_fragment.strip()):
        return False
    if not re.search(r"(?is)\bon\b", join_fragment):
        return False
    return True


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
        repaired = _replace_patient_uuid_comparisons_for_qualifier(repaired,
qualifier)

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

    for block in sorted(_find_select_blocks(repaired), key=lambda item:
item.start, reverse=True):
        original = repaired[block.start : block.end]
        if not _simple_select_from_only_view(original,
PATIENT_DEMOGRAPHIC_VIEW):
            continue
        fixed = _replace_unqualified_identifier(original, "nombre_paciente",
"nombre_completo")
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

    for block in sorted(_find_select_blocks(repaired), key=lambda item:
item.start, reverse=True):
        original = repaired[block.start : block.end]
        if _simple_select_single_detail_view(original) is None:
            continue
        fixed = _replace_unqualified_identifier(original, "nombre_completo",
"nombre_paciente")
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
    repaired = _replace_professional_column_references(sql, patient_alias,
professional_alias)
    return _insert_professional_join(repaired, encounter_alias,
professional_alias, join_type="JOIN")




def repair_unqualified_professional_columns_from_encounter_source(sql: str) -> str:
    """
    Repara un patrón frecuente del modelo cuando usa reporting.vw_encuentros
    como única fuente, pero proyecta columnas que realmente pertenecen a
    reporting.vw_profesionales.

    Ejemplo inválido:
      SELECT id_profesional, id_profesional_fuente, nombre_profesional, COUNT(*)
      FROM reporting.vw_encuentros
      GROUP BY id_profesional, id_profesional_fuente, nombre_profesional

    Reparación conservadora:
      SELECT e.id_profesional, prof_fix.id_profesional_fuente,
             prof_fix.nombre_profesional, COUNT(*)
      FROM reporting.vw_encuentros e
      LEFT JOIN reporting.vw_profesionales prof_fix
        ON prof_fix.id_profesional = e.id_profesional
      GROUP BY e.id_profesional, prof_fix.id_profesional_fuente,
               prof_fix.nombre_profesional

    Solo se aplica cuando el SELECT tiene como fuente principal única
    vw_encuentros y todavía no une vw_profesionales. Si hay JOINs previos,
    subconsultas ambiguas o fuentes múltiples, devuelve el SQL original.
    """
    if re.search(r"\breporting\.vw_profesionales\b", sql, flags=re.IGNORECASE):
        return sql

    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_unqualified_professional_columns_from_encounters(original)
        if repaired != original:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def _repair_select_block_unqualified_professional_columns_from_encounters(block_sql: str) -> str:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql
    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return block_sql

    from_body_start = _skip_ws(block_sql, from_pos + len("from"))
    source = _read_reporting_view_source(block_sql, from_body_start)
    if source is None:
        return block_sql
    view_name, encounter_alias, source_end = source
    if view_name.lower() != ENCOUNTER_VIEW.lower():
        return block_sql

    clause_start = _find_first_clause_after_from_source(block_sql, source_end)
    from_tail = block_sql[source_end:clause_start]
    # Esta regla solo trabaja con vw_encuentros como fuente única. Si ya hay
    # JOINs, coma de fuentes múltiples u otra relación entre FROM y cláusulas,
    # no se toca para evitar cambios semánticos.
    if from_tail.strip():
        return block_sql

    select_list = block_sql[select_pos + len("select") : from_pos]
    remaining = block_sql[clause_start:]
    scope_sql = select_list + "\\n" + remaining

    invalid_unqualified = _unqualified_professional_columns_used_in_sql(scope_sql)
    if not invalid_unqualified:
        return block_sql

    encounter_alias = encounter_alias or _unique_alias(block_sql, "e")
    professional_alias = _unique_alias(block_sql, "prof_fix")

    source_sql = f"{ENCOUNTER_VIEW} {encounter_alias}"
    join_sql = (
        f" LEFT JOIN {PROFESSIONAL_VIEW} {professional_alias}"
        f" ON {professional_alias}.id_profesional = {encounter_alias}.id_profesional"
    )

    rewritten_scope = _rewrite_unqualified_encounter_professional_scope(
        scope_sql,
        encounter_alias=encounter_alias,
        professional_alias=professional_alias,
    )
    rewritten_select_list, rewritten_remaining = rewritten_scope.split("\\n", 1)
    if rewritten_remaining and not rewritten_remaining[0].isspace():
        rewritten_remaining = " " + rewritten_remaining

    return (
        block_sql[: select_pos + len("select")]
        + rewritten_select_list
        + block_sql[from_pos: from_body_start]
        + source_sql
        + join_sql
        + rewritten_remaining
    )


def _find_first_clause_after_from_source(sql: str, start: int) -> int:
    candidates: list[int] = []
    for keyword in ("where", "group", "having", "order", "limit", "offset", "fetch", "union", "intersect", "except"):
        pos = _find_top_level_keyword(sql, keyword, start=start, depth=0)
        if pos >= 0:
            candidates.append(pos)
    join_pos = _find_first_top_level_join_start(sql, start=start, depth=0)
    if join_pos >= 0:
        candidates.append(join_pos)
    return min(candidates) if candidates else len(sql)


def _unqualified_professional_columns_used_in_sql(sql: str) -> set[str]:
    columns: set[str] = set()
    professional_only_columns = ENCOUNTER_ALIAS_INVALID_PROFESSIONAL_COLUMNS

    def detector(token: str, prev_ch: str, next_ch: str) -> str:
        if prev_ch != "." and next_ch != "." and token.lower() in professional_only_columns:
            columns.add(token.lower())
        return token

    _replace_identifier_tokens(sql, detector)
    return columns


def _rewrite_unqualified_encounter_professional_scope(
    sql: str,
    *,
    encounter_alias: str,
    professional_alias: str,
) -> str:
    professional_only_columns = ENCOUNTER_ALIAS_INVALID_PROFESSIONAL_COLUMNS

    def replacer(token: str, prev_ch: str, next_ch: str) -> str:
        token_l = token.lower()
        if prev_ch == "." or next_ch == ".":
            return token
        if token_l in professional_only_columns:
            return f"{professional_alias}.{token_l}"
        if token_l == "id_profesional":
            return f"{encounter_alias}.id_profesional"
        return token

    return _replace_identifier_tokens(sql, replacer)
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
    professional_alias = _preferred_alias(professional_aliases,
PROFESSIONAL_VIEW)
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
        repaired = _alias_encounter_profesional_select_items(repaired,
encounter_alias)

    if should_add_professional_join and professional_alias:
        encounter_alias = _preferred_alias(_view_aliases(repaired,
{ENCOUNTER_VIEW}), ENCOUNTER_VIEW)
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


def _alias_with_invalid_professional_columns(sql: str,aliases: set[str],invalid_columns: set[str],) -> str | None:
    for alias in sorted(aliases, key=len, reverse=True):
        q = re.escape(alias)
        for column in sorted(invalid_columns, key=len, reverse=True):
            if re.search(rf"\b{q}\s*\.\s*{re.escape(column)}\b", sql,
flags=re.IGNORECASE):
                return alias
    return None


def _replace_professional_column_references(sql: str, patient_alias: str,professional_alias: str) -> str:
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


def _replace_encounter_professional_column_references(sql: str,encounter_alias: str,professional_alias: str | None,) -> tuple[str, bool, bool]:
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

    for column in sorted(ENCOUNTER_ALIAS_INVALID_PROFESSIONAL_COLUMNS, key=len,
reverse=True):

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

    for block in sorted(_find_select_blocks(result), key=lambda item:
item.start, reverse=True):
        block_sql = result[block.start : block.end]
        select_pos = _find_top_level_keyword(block_sql, "select", start=0,
depth=0)
        if select_pos < 0:
            continue
        from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos
+ len("select"), depth=0)
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


def _insert_professional_join(sql: str,encounter_alias: str,professional_alias: str,*,join_type: str = "LEFT JOIN",) -> str:
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
    repaired, count = from_with_alias_pattern.subn(lambda match:
match.group(1).rstrip() + join_sql, sql, count=1)
    if count:
        return repaired

    # Caso 3: fuente principal sin alias. PostgreSQL permite referirse a la
    # relación como vw_encuentros.columna cuando no se declaró alias.
    if encounter_alias.lower() in {ENCOUNTER_VIEW.lower(),
ENCOUNTER_VIEW.split(".")[-1].lower()}:
        from_without_alias_pattern = re.compile(
            rf"(\bFROM\s+{re.escape(ENCOUNTER_VIEW)}\b)"
            rf"(?=\s+(?:{CLAUSE_AFTER_SOURCE_RE})\b|\s*\)|\s*$)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        repaired, count = from_without_alias_pattern.subn(lambda match:
match.group(1).rstrip() + join_sql, sql, count=1)
        if count:
            return repaired

    return sql



def repair_patient_same_detail_filter_joins_to_grouped_having(sql: str) -> str:
    """
    Optimiza un patrón común y costoso en consultas NL2SQL clínicas:

      SELECT DISTINCT p.columnas...
      FROM reporting.vw_pacientes p
      JOIN reporting.vw_diagnosticos d  ON d.id_paciente = p.id_paciente
      JOIN reporting.vw_diagnosticos d2 ON d2.id_paciente = p.id_paciente
      WHERE p.condicion
        AND d.condicion_diabetes
        AND d2.condicion_hipertension

    Cuando todos los JOINs de detalle son INNER JOINs hacia la MISMA vista y
    solo se usan como filtros de existencia, se reemplazan por una tabla
    derivada agrupada por id_paciente con HAVING bool_or(...). En bases OMOP
    grandes esto evita multiplicar filas antes del DISTINCT y suele ser mucho
    más rápido que dos EXISTS correlacionados.

    La regla es deliberadamente conservadora:
    - Solo parte de reporting.vw_pacientes.
    - Solo acepta SELECT DISTINCT con proyección de columnas de paciente.
    - Solo acepta INNER JOIN simple por id_paciente.
    - Solo optimiza si todos los JOINs de detalle son de la misma vista.
    - No toca GROUP BY/HAVING/BETWEEN/subconsultas/EXISTS existentes.
    - No toca si SELECT/ORDER BY usan columnas de los aliases de detalle.
    """
    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_patient_same_detail_filter_joins_to_grouped_having(original)
        if repaired != original:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def repair_patient_filter_joins_to_exists(sql: str) -> str:
    """
    Reescribe JOINs de detalle usados solo como filtros de existencia a EXISTS.

    Esta regla queda como fallback conservador para JOINs a vistas distintas.
    Para múltiples filtros sobre la misma vista, primero se intenta la versión
    agrupada con bool_or por rendimiento.
    """
    result = sql
    for block in sorted(_find_select_blocks(result), key=lambda item: item.start, reverse=True):
        original = result[block.start : block.end]
        repaired = _repair_select_block_patient_filter_joins_to_exists(original)
        if repaired != original:
            result = result[: block.start] + repaired + result[block.end :]
    return result


def _repair_select_block_patient_same_detail_filter_joins_to_grouped_having(block_sql: str) -> str:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql

    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return block_sql

    where_pos = _find_top_level_keyword(block_sql, "where", start=from_pos + len("from"), depth=0)
    if where_pos < 0:
        return block_sql

    select_list = block_sql[select_pos + len("select") : from_pos]
    if not _select_list_has_plain_distinct(select_list):
        return block_sql

    if _find_top_level_keyword(block_sql, "group", start=where_pos + len("where"), depth=0) >= 0:
        return block_sql
    if _find_top_level_keyword(block_sql, "having", start=where_pos + len("where"), depth=0) >= 0:
        return block_sql

    from_fragment = block_sql[from_pos + len("from") : where_pos]
    parsed = _parse_patient_filter_from_fragment(from_fragment)
    if parsed is None:
        return block_sql

    patient_alias = parsed["patient_alias"]
    patient_joins = parsed["joins"]
    if len(patient_joins) < 2:
        return block_sql

    detail_views_l = {join.view_name.lower() for join in patient_joins}
    if len(detail_views_l) != 1:
        return block_sql

    filter_aliases = {join.alias for join in patient_joins}
    if not _select_list_is_patient_only_projection(select_list, patient_alias, filter_aliases):
        return block_sql

    where_condition_start = _skip_ws(block_sql, where_pos + len("where"))
    where_condition_end = _find_condition_end_after_where(block_sql, where_condition_start)
    trailing_clauses = block_sql[where_condition_end:]
    if _qualified_aliases_in_sql(trailing_clauses, filter_aliases):
        return block_sql

    where_sql = block_sql[where_condition_start:where_condition_end].strip()
    if not where_sql:
        return block_sql
    if _contains_sql_keyword(where_sql, "select") or _contains_sql_keyword(where_sql, "exists"):
        return block_sql
    if _contains_sql_keyword(where_sql, "between"):
        return block_sql

    terms = _collect_conjunctive_conditions(where_sql)
    if not terms:
        return block_sql

    known_aliases = {patient_alias.lower(): patient_alias}
    known_aliases.update({join.alias.lower(): join.alias for join in patient_joins})

    patient_terms: list[str] = []
    filter_terms_by_alias: dict[str, list[str]] = {join.alias: [] for join in patient_joins}

    for term in terms:
        prefixes = _qualified_identifier_prefixes_in_sql(term)
        if not prefixes:
            return block_sql

        unknown_prefixes = {prefix for prefix in prefixes if prefix.lower() not in known_aliases}
        if unknown_prefixes:
            return block_sql

        referenced_aliases = {known_aliases[prefix.lower()] for prefix in prefixes}

        if referenced_aliases == {patient_alias}:
            patient_terms.append(term)
            continue

        if len(referenced_aliases) == 1:
            alias = next(iter(referenced_aliases))
            if alias in filter_terms_by_alias:
                filter_terms_by_alias[alias].append(term)
                continue

        return block_sql

    if any(not filter_terms_by_alias[join.alias] for join in patient_joins):
        return block_sql

    detail_view = patient_joins[0].view_name
    detail_alias = _unique_alias(block_sql, "dx")
    derived_alias = _unique_alias(block_sql + " " + detail_alias, "dx_filter")

    per_alias_conditions: list[str] = []
    for join in patient_joins:
        normalized_terms = [
            _replace_qualified_alias(term, join.alias, detail_alias)
            for term in filter_terms_by_alias[join.alias]
        ]
        condition = " AND ".join(_parenthesize_condition_for_where_merge(term) for term in normalized_terms)
        if not condition:
            return block_sql
        per_alias_conditions.append(condition)

    prefilter_condition = "\n        OR ".join(f"({condition})" for condition in per_alias_conditions)
    having_condition = "\n        AND ".join(f"bool_or({condition})" for condition in per_alias_conditions)

    derived_table = (
        f"(\n"
        f"    SELECT {detail_alias}.id_paciente\n"
        f"    FROM {detail_view} {detail_alias}\n"
        f"    WHERE {prefilter_condition}\n"
        f"    GROUP BY {detail_alias}.id_paciente\n"
        f"    HAVING {having_condition}\n"
        f") {derived_alias}"
    )

    repaired_from = (
        f" {PATIENT_DEMOGRAPHIC_VIEW} {patient_alias}\n"
        f"JOIN {derived_table}\n"
        f"  ON {derived_alias}.id_paciente = {patient_alias}.id_paciente"
    )

    outer_conditions = [_parenthesize_condition_for_where_merge(term) for term in patient_terms]
    repaired_where = ""
    if outer_conditions:
        repaired_where = "\nWHERE " + "\n  AND ".join(outer_conditions)

    if trailing_clauses and not trailing_clauses[0].isspace():
        trailing_clauses = "\n" + trailing_clauses

    return (
        block_sql[: from_pos + len("from")]
        + repaired_from
        + repaired_where
        + trailing_clauses
    )


def _repair_select_block_patient_filter_joins_to_exists(block_sql: str) -> str:
    select_pos = _find_top_level_keyword(block_sql, "select", start=0, depth=0)
    if select_pos < 0:
        return block_sql

    from_pos = _find_top_level_keyword(block_sql, "from", start=select_pos + len("select"), depth=0)
    if from_pos < 0:
        return block_sql

    where_pos = _find_top_level_keyword(block_sql, "where", start=from_pos + len("from"), depth=0)
    if where_pos < 0:
        return block_sql

    select_list = block_sql[select_pos + len("select") : from_pos]
    if not _select_list_has_plain_distinct(select_list):
        return block_sql

    if _find_top_level_keyword(block_sql, "group", start=where_pos + len("where"), depth=0) >= 0:
        return block_sql
    if _find_top_level_keyword(block_sql, "having", start=where_pos + len("where"), depth=0) >= 0:
        return block_sql

    where_condition_start = _skip_ws(block_sql, where_pos + len("where"))
    where_condition_end = _find_condition_end_after_where(block_sql, where_condition_start)

    from_fragment = block_sql[from_pos + len("from") : where_pos]
    parsed = _parse_patient_filter_from_fragment(from_fragment)
    if parsed is None:
        return block_sql

    patient_alias = parsed["patient_alias"]
    patient_joins = parsed["joins"]
    if not patient_joins:
        return block_sql

    filter_aliases = {join.alias for join in patient_joins}

    if not _select_list_is_patient_only_projection(select_list, patient_alias, filter_aliases):
        return block_sql

    trailing_clauses = block_sql[where_condition_end:]
    if trailing_clauses and not trailing_clauses[0].isspace():
        trailing_clauses = "\n" + trailing_clauses

    if _qualified_aliases_in_sql(trailing_clauses, filter_aliases):
        return block_sql

    where_sql = block_sql[where_condition_start:where_condition_end].strip()
    if not where_sql:
        return block_sql
    if _contains_sql_keyword(where_sql, "select") or _contains_sql_keyword(where_sql, "exists"):
        return block_sql
    if _contains_sql_keyword(where_sql, "between"):
        return block_sql

    terms = _collect_conjunctive_conditions(where_sql)
    if not terms:
        return block_sql

    known_aliases = {patient_alias.lower(): patient_alias}
    known_aliases.update({join.alias.lower(): join.alias for join in patient_joins})

    patient_terms: list[str] = []
    filter_terms_by_alias: dict[str, list[str]] = {join.alias: [] for join in patient_joins}

    for term in terms:
        prefixes = _qualified_identifier_prefixes_in_sql(term)
        if not prefixes:
            return block_sql

        unknown_prefixes = {prefix for prefix in prefixes if prefix.lower() not in known_aliases}
        if unknown_prefixes:
            return block_sql

        referenced_aliases = {known_aliases[prefix.lower()] for prefix in prefixes}

        if referenced_aliases == {patient_alias}:
            patient_terms.append(term)
            continue

        if len(referenced_aliases) == 1:
            alias = next(iter(referenced_aliases))
            if alias in filter_terms_by_alias:
                filter_terms_by_alias[alias].append(term)
                continue

        return block_sql

    if any(not filter_terms_by_alias[join.alias] for join in patient_joins):
        return block_sql

    outer_conditions: list[str] = []
    outer_conditions.extend(_parenthesize_condition_for_where_merge(term) for term in patient_terms)

    for join in patient_joins:
        outer_conditions.append(
            _build_patient_filter_exists_condition(
                patient_alias=patient_alias,
                filter_view=join.view_name,
                filter_alias=join.alias,
                filter_terms=filter_terms_by_alias[join.alias],
            )
        )

    if not outer_conditions:
        return block_sql

    repaired_from = f" {PATIENT_DEMOGRAPHIC_VIEW} {patient_alias}"
    repaired_where = "\nWHERE " + "\n  AND ".join(outer_conditions)

    return (
        block_sql[: from_pos + len("from")]
        + repaired_from
        + repaired_where
        + trailing_clauses
    )


def _parse_patient_filter_from_fragment(from_fragment: str) -> dict[str, object] | None:
    """
    Reconoce exclusivamente:
      reporting.vw_pacientes p
      JOIN reporting.vw_<vista_permitida> a ON a.id_paciente = p.id_paciente
      [JOIN reporting.vw_<vista_permitida> b ON b.id_paciente = p.id_paciente ...]
    """
    i = _skip_ws(from_fragment, 0)

    source = _read_reporting_view_source(from_fragment, i)
    if source is None:
        return None
    view_name, patient_alias, i = source

    if view_name.lower() != PATIENT_DEMOGRAPHIC_VIEW.lower():
        return None
    if patient_alias is None:
        return None
    if not _is_safe_source_alias(patient_alias):
        return None

    joins: list[_PatientFilterJoin] = []
    aliases_seen = {patient_alias.lower()}

    while True:
        i = _skip_ws(from_fragment, i)
        if i >= len(from_fragment):
            break

        if not _keyword_at(from_fragment, i, "join"):
            return None

        join_start = i
        i = _skip_ws(from_fragment, i + len("join"))

        source = _read_reporting_view_source(from_fragment, i)
        if source is None:
            return None
        join_view_name, join_alias, i = source

        allowed = {view.lower() for view in PATIENT_EXISTENCE_FILTER_VIEWS}
        if join_view_name.lower() not in allowed:
            return None
        if join_alias is None:
            return None
        if not _is_safe_source_alias(join_alias):
            return None
        if join_alias.lower() in aliases_seen:
            return None
        aliases_seen.add(join_alias.lower())

        i = _skip_ws(from_fragment, i)
        if not _keyword_at(from_fragment, i, "on"):
            return None
        on_start = _skip_ws(from_fragment, i + len("on"))

        next_join = _find_first_top_level_join_start(from_fragment, start=on_start, depth=0)
        on_end = next_join if next_join >= 0 else len(from_fragment)
        on_condition = from_fragment[on_start:on_end].strip()
        if not on_condition:
            return None

        if not _is_simple_patient_filter_id_join_condition(
            on_condition,
            patient_alias=patient_alias,
            filter_alias=join_alias,
        ):
            return None

        joins.append(_PatientFilterJoin(view_name=join_view_name, alias=join_alias, on_condition=on_condition))
        i = on_end
        if i == join_start:
            return None

    if not joins:
        return None

    return {"patient_alias": patient_alias, "joins": joins}


def _read_reporting_view_source(sql: str, start: int) -> tuple[str, str | None, int] | None:
    match = re.match(r"reporting\.vw_[A-Za-z0-9_]+", sql[start:], flags=re.IGNORECASE)
    if not match:
        return None

    view_name = match.group(0)
    i = start + len(match.group(0))
    i = _skip_ws(sql, i)

    alias: str | None = None
    if _keyword_at(sql, i, "as"):
        i = _skip_ws(sql, i + len("as"))
        alias_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", sql[i:])
        if not alias_match:
            return None
        alias = alias_match.group(0)
        i += len(alias)
        return view_name, alias, i

    alias_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", sql[i:])
    if alias_match:
        candidate = alias_match.group(0)
        if candidate.lower() not in SQL_KEYWORDS_AFTER_SOURCE and candidate.lower() not in JOIN_KEYWORDS:
            alias = candidate
            i += len(alias)

    return view_name, alias, i


def _is_safe_source_alias(alias: str) -> bool:
    alias_l = alias.lower()
    if not IDENTIFIER_RE.match(alias):
        return False
    if alias_l in SQL_KEYWORDS_AFTER_SOURCE:
        return False
    if alias_l in JOIN_KEYWORDS:
        return False
    if alias_l in {"select", "from", "where", "group", "having", "order", "by", "limit"}:
        return False
    return True


def _is_simple_patient_filter_id_join_condition(condition: str, *, patient_alias: str, filter_alias: str) -> bool:
    text = _strip_redundant_enclosing_parentheses(condition.strip())
    patient = re.escape(patient_alias)
    filter_q = re.escape(filter_alias)
    left_to_right = rf"^{filter_q}\s*\.\s*id_paciente\s*=\s*{patient}\s*\.\s*id_paciente$"
    right_to_left = rf"^{patient}\s*\.\s*id_paciente\s*=\s*{filter_q}\s*\.\s*id_paciente$"
    return bool(re.match(left_to_right, text, flags=re.IGNORECASE) or re.match(right_to_left, text, flags=re.IGNORECASE))


def _select_list_has_plain_distinct(select_list_sql: str) -> bool:
    text = select_list_sql.lstrip()
    if not _keyword_at(text, 0, "distinct"):
        return False
    after_distinct = _skip_ws(text, len("distinct"))
    if _keyword_at(text, after_distinct, "on"):
        return False
    return True


def _select_list_is_patient_only_projection(select_list_sql: str, patient_alias: str, filter_aliases: set[str]) -> bool:
    normalized = _strip_select_modifier(select_list_sql)
    items = _split_top_level_commas(normalized)
    if not items:
        return False

    filter_aliases_l = {alias.lower() for alias in filter_aliases}
    patient_alias_l = patient_alias.lower()

    for item in items:
        expr = _select_item_expression_without_output_alias(item)
        if not expr:
            return False

        prefixes = _qualified_identifier_prefixes_in_sql(expr)
        if any(prefix.lower() in filter_aliases_l for prefix in prefixes):
            return False

        unknown_prefixes = {prefix for prefix in prefixes if prefix.lower() != patient_alias_l}
        if unknown_prefixes:
            return False

        if prefixes:
            continue

        if _is_simple_column_reference(expr):
            column = expr.strip().strip('"').lower()
            if column not in PATIENT_DEMOGRAPHIC_COLUMNS:
                return False
            continue

        return False

    return True


def _select_item_expression_without_output_alias(item: str) -> str:
    text = item.strip()
    if not text:
        return ""

    match = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", text, flags=re.IGNORECASE)
    if match:
        return text[: match.start()].strip()

    implicit = re.match(r"(?is)^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", text)
    if implicit:
        possible_expr = implicit.group(1).strip()
        possible_alias = implicit.group(2)
        if _is_safe_implicit_alias(possible_expr, possible_alias):
            return possible_expr

    return text


def _strip_redundant_enclosing_parentheses(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")") and _enclosing_parentheses_cover_entire_text(stripped):
        stripped = stripped[1:-1].strip()
    return stripped


def _collect_conjunctive_conditions(condition_sql: str) -> list[str]:
    text = _strip_redundant_enclosing_parentheses(condition_sql.strip())
    if not text:
        return []

    parts = _split_top_level_boolean_operator(text, "and")
    if len(parts) <= 1:
        return [text]

    terms: list[str] = []
    for part in parts:
        terms.extend(_collect_conjunctive_conditions(part))
    return terms


def _split_top_level_boolean_operator(text: str, operator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    i = 0
    depth = 0
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
            i += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            i += 1
            continue

        if depth == 0 and _keyword_at(text, i, operator):
            part = text[start:i].strip()
            if not part:
                return [text]
            parts.append(part)
            start = i + len(operator)
            i = start
            continue

        i += 1

    tail = text[start:].strip()
    if not tail:
        return [text]
    parts.append(tail)
    return parts


def _qualified_identifier_prefixes_in_sql(sql: str) -> set[str]:
    prefixes: set[str] = set()
    i = 0
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

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            token = sql[i:j]
            if _next_non_ws(sql, j) == ".":
                prefixes.add(token)
            i = j
            continue

        i += 1

    return prefixes


def _qualified_aliases_in_sql(sql: str, aliases: set[str]) -> set[str]:
    aliases_by_lower = {alias.lower(): alias for alias in aliases}
    prefixes = _qualified_identifier_prefixes_in_sql(sql)
    return {aliases_by_lower[prefix.lower()] for prefix in prefixes if prefix.lower() in aliases_by_lower}


def _contains_sql_keyword(sql: str, keyword: str) -> bool:
    i = 0
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

        if _keyword_at(sql, i, keyword):
            return True
        i += 1

    return False


def _build_patient_filter_exists_condition(*, patient_alias: str, filter_view: str, filter_alias: str, filter_terms: list[str]) -> str:
    exists_conditions = [f"{filter_alias}.id_paciente = {patient_alias}.id_paciente"]
    exists_conditions.extend(_parenthesize_condition_for_where_merge(term) for term in filter_terms)
    return (
        "EXISTS (\n"
        "      SELECT 1\n"
        f"      FROM {filter_view} {filter_alias}\n"
        "      WHERE "
        + "\n        AND ".join(exists_conditions)
        + "\n  )"
    )


def _replace_qualified_alias(sql: str, old_alias: str, new_alias: str) -> str:
    old_l = old_alias.lower()

    def replacer(token: str, prev_ch: str, next_ch: str) -> str:
        if token.lower() == old_l and next_ch == ".":
            return new_alias
        return token

    return _replace_identifier_tokens(sql, replacer)


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
    explicit = [item for item in aliases if item.lower() not in
{view_name.lower(), view_short.lower()}]
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

    order_pos = _find_order_by(block_sql, start=from_pos + len("from"),
depth=0)
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

        match = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item,
flags=re.IGNORECASE)
        expr = item
        alias = None
        if match:
            alias = match.group(1)
            expr = item[: match.start()].strip()
        else:
            implicit = re.match(r"(?is)^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$",
item)
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
    if not _keyword_at(text, 0, "distinct") and not _keyword_at(text, 0,
"all"):
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
            state, dollar_tag, jumped = _advance_string_or_comment_state(text,
i, state, dollar_tag)
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


def _replace_identifier_tokens(sql: str, replacer: Callable[[str, str, str],str]) -> str:
    result: list[str] = []
    i = 0
    state: str | None = None
    dollar_tag: str | None = None

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state is not None:
            new_state, new_tag, jumped = _advance_string_or_comment_state(sql,
i, state, dollar_tag)
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
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql,
i, state, dollar_tag)
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
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql,
i, state, dollar_tag)
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
        if depth == select_depth and _keyword_at_any(sql, i, {"union",
"intersect", "except"}):
            return i
        i += 1

    return len(sql)


def _advance_string_or_comment_state(sql: str,i: int,state: str,dollar_tag: str | None,) -> tuple[str | None, str | None, int | None]:
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
            state, dollar_tag, jumped = _advance_string_or_comment_state(text,
i, state, dollar_tag)
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
    order_pos = _find_top_level_keyword(block_sql, "order", start=start,
depth=depth)
    while order_pos >= 0:
        by_pos = _skip_ws(block_sql, order_pos + len("order"))
        if _keyword_at(block_sql, by_pos, "by"):
            return order_pos
        order_pos = _find_top_level_keyword(block_sql, "order", start=order_pos
+ 1, depth=depth)
    return -1


def _find_order_by_end(block_sql: str, start: int) -> int:
    candidates = []
    for keyword in ("limit", "offset", "fetch", "union", "intersect",
"except"):
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
            state, dollar_tag, jumped = _advance_string_or_comment_state(sql,
i, state, dollar_tag)
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



def _find_matching_paren(text: str, open_pos: int) -> int:
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
                return i

        i += 1

    return -1

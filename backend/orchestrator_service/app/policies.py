from __future__ import annotations

import re

from fastapi import HTTPException

from .config import settings
from .security import UserClaims, require_permission

TABLE_RE = re.compile(
    r'\b(?:from|join)\s+((?:"?[A-Za-z_][A-Za-z0-9_]*"?\.)?"?[A-Za-z_][A-Za-z0-9_]*"?)',
    flags=re.IGNORECASE,
)

LINE_COMMENT_RE = re.compile(r"--.*?(?=\n|$)")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
SINGLE_QUOTED_RE = re.compile(r"'(?:''|[^'])*'")
DOLLAR_QUOTED_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_]*\$.*?\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$.*?\$\$",
    re.DOTALL,
)


def _analysis_sql(sql: str) -> str:
    sql = BLOCK_COMMENT_RE.sub(" ", sql)
    sql = LINE_COMMENT_RE.sub(" ", sql)
    sql = DOLLAR_QUOTED_RE.sub("''", sql)
    sql = SINGLE_QUOTED_RE.sub("''", sql)
    return sql


def _clean_identifier(identifier: str) -> str:
    parts = [p.strip().strip('"').lower() for p in identifier.split(".")]
    return ".".join(p for p in parts if p)


def extract_used_tables(sql: str) -> set[str]:
    s = _analysis_sql(sql)
    tables: set[str] = set()
    for match in TABLE_RE.finditer(s):
        table = _clean_identifier(match.group(1))
        # Si el modelo llegara a usar un CTE sin esquema, no lo bloqueamos aquí;
        # query_service ya valida las vistas reales permitidas globalmente.
        if "." in table:
            tables.add(table)
    return tables


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

    # Restricción del perfil: vacío significa "todas las vistas globalmente permitidas".
    if claims.allowed_tables:
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


def visible_sql(sql: str, claims: UserClaims) -> str:
    return sql if claims.can("can_view_sql") else ""

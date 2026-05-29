from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ADMIN_PERMISSIONS = {
    "can_query": True,
    "can_export": True,
    "can_view_sql": True,
    "can_manage_users": True,
    "can_manage_profiles": True,
    "can_view_audit": True,
    "can_view_system_config": True,
}


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_admin_profile(conn: sqlite3.Connection) -> int:
    profile_cols = table_columns(conn, "profiles")
    row = conn.execute("SELECT id FROM profiles WHERE lower(name) = lower(?)", ("admin",)).fetchone()
    permissions_json = json.dumps(ADMIN_PERMISSIONS, ensure_ascii=False)

    if row:
        admin_profile_id = int(row[0])
        assignments: dict[str, object] = {}
        if "permissions_json" in profile_cols:
            assignments["permissions_json"] = permissions_json
        if "description" in profile_cols:
            assignments["description"] = "Administrador total de la plataforma."
        if "table_access_mode" in profile_cols:
            assignments["table_access_mode"] = "all"
        if "allowed_tables" in profile_cols:
            assignments["allowed_tables"] = ""
        if "column_permissions_json" in profile_cols:
            assignments["column_permissions_json"] = "{}"
        if "max_display_rows" in profile_cols:
            assignments["max_display_rows"] = 5000
        if "max_page_size" in profile_cols:
            assignments["max_page_size"] = 50
        if "is_system" in profile_cols:
            assignments["is_system"] = 1

        if assignments:
            set_clause = ", ".join(f"{col} = ?" for col in assignments)
            values = list(assignments.values()) + [admin_profile_id]
            conn.execute(f"UPDATE profiles SET {set_clause} WHERE id = ?", values)
        return admin_profile_id

    insert_values: dict[str, object] = {"name": "admin"}
    if "description" in profile_cols:
        insert_values["description"] = "Administrador total de la plataforma."
    if "permissions_json" in profile_cols:
        insert_values["permissions_json"] = permissions_json
    if "table_access_mode" in profile_cols:
        insert_values["table_access_mode"] = "all"
    if "allowed_tables" in profile_cols:
        insert_values["allowed_tables"] = ""
    if "column_permissions_json" in profile_cols:
        insert_values["column_permissions_json"] = "{}"
    if "max_display_rows" in profile_cols:
        insert_values["max_display_rows"] = 5000
    if "max_page_size" in profile_cols:
        insert_values["max_page_size"] = 50
    if "is_system" in profile_cols:
        insert_values["is_system"] = 1

    cols = list(insert_values)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO profiles ({', '.join(cols)}) VALUES ({placeholders})",
        [insert_values[col] for col in cols],
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def restore_user(conn: sqlite3.Connection, username: str, admin_profile_id: int) -> None:
    user_cols = table_columns(conn, "users")
    row = conn.execute("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
    if not row:
        raise SystemExit(f"No existe el usuario '{username}' en la tabla users.")

    assignments: dict[str, object] = {}
    if "profile_id" in user_cols:
        assignments["profile_id"] = admin_profile_id
    if "is_active" in user_cols:
        assignments["is_active"] = 1

    if not assignments:
        raise SystemExit("La tabla users no tiene columnas profile_id/is_active para restaurar permisos.")

    set_clause = ", ".join(f"{col} = ?" for col in assignments)
    conn.execute(
        f"UPDATE users SET {set_clause} WHERE lower(username) = lower(?)",
        list(assignments.values()) + [username],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaura permisos de administrador a un usuario del sistema NL2SQL.")
    parser.add_argument("--db", default="data/auth.db", help="Ruta del SQLite de autenticación. Default: data/auth.db")
    parser.add_argument("--username", default="tavo", help="Usuario a restaurar. Default: tavo")
    parser.add_argument("--no-backup", action="store_true", help="No crear copia .bak antes de modificar")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"No existe la base de autenticación: {db_path}")

    if not args.no_backup:
        backup_path = db_path.with_suffix(db_path.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(db_path, backup_path)
        print(f"Backup creado: {backup_path}")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        admin_profile_id = ensure_admin_profile(conn)
        restore_user(conn, args.username, admin_profile_id)
        conn.commit()

    print(f"Usuario '{args.username}' restaurado con perfil admin. Cierra sesión y vuelve a iniciar sesión.")


if __name__ == "__main__":
    main()

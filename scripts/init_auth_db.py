import json
import sqlite3
from pathlib import Path

from passlib.hash import pbkdf2_sha256

Path("data").mkdir(exist_ok=True)
db_path = Path("data/auth.db")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS profiles;

CREATE TABLE profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT DEFAULT '',
  permissions_json TEXT NOT NULL DEFAULT '{}',
  table_access_mode TEXT NOT NULL DEFAULT 'all',
  allowed_tables TEXT DEFAULT '',
  column_permissions_json TEXT NOT NULL DEFAULT '{}',
  max_display_rows INTEGER NOT NULL DEFAULT 5000,
  max_page_size INTEGER NOT NULL DEFAULT 50,
  is_system INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  full_name TEXT,
  email TEXT,
  profile_id INTEGER,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(profile_id) REFERENCES profiles(id)
);
""")

PERMISSIONS = [
    "can_query",
    "can_export",
    "can_view_sql",
    "can_manage_users",
    "can_manage_profiles",
    "can_view_audit",
    "can_view_system_config",
]

EMPTY_COLUMN_PERMISSIONS = json.dumps({})

profiles = [
    (
        "admin",
        "Administrador total de la plataforma.",
        json.dumps({k: True for k in PERMISSIONS}),
        "all",
        "",
        EMPTY_COLUMN_PERMISSIONS,
        5000,
        50,
        1,
    ),
    (
        "analista",
        "Puede consultar, exportar y ver SQL generado.",
        json.dumps({
            "can_query": True,
            "can_export": True,
            "can_view_sql": True,
            "can_manage_users": False,
            "can_manage_profiles": False,
            "can_view_audit": False,
            "can_view_system_config": True,
        }),
        "all",
        "",
        EMPTY_COLUMN_PERMISSIONS,
        5000,
        50,
        1,
    ),
    (
        "consulta",
        "Usuario final: consulta resultados, sin SQL ni exportación.",
        json.dumps({
            "can_query": True,
            "can_export": False,
            "can_view_sql": False,
            "can_manage_users": False,
            "can_manage_profiles": False,
            "can_view_audit": False,
            "can_view_system_config": False,
        }),
        "all",
        "",
        EMPTY_COLUMN_PERMISSIONS,
        5000,
        50,
        1,
    ),
    (
        "auditor",
        "Puede revisar auditoría de preguntas y actividad.",
        json.dumps({
            "can_query": False,
            "can_export": True,
            "can_view_sql": True,
            "can_manage_users": False,
            "can_manage_profiles": False,
            "can_view_audit": True,
            "can_view_system_config": True,
        }),
        "all",
        "",
        EMPTY_COLUMN_PERMISSIONS,
        5000,
        50,
        1,
    ),
]

cur.executemany(
    """
    INSERT INTO profiles(
      name, description, permissions_json, table_access_mode, allowed_tables, column_permissions_json,
      max_display_rows, max_page_size, is_system
    )
    VALUES (?,?,?,?,?,?,?,?,?)
    """,
    profiles,
)

cur.execute("SELECT id FROM profiles WHERE name='admin'")
admin_profile_id = cur.fetchone()[0]
cur.execute("SELECT id FROM profiles WHERE name='consulta'")
consulta_profile_id = cur.fetchone()[0]

users = [
    ("admin", pbkdf2_sha256.hash("admin123"), "Administrador", "gilgustavo062@gmail.com", admin_profile_id, 1),
    ("doctor1", pbkdf2_sha256.hash("doctor123"), "Doctor Demo", None, consulta_profile_id, 1),
]

cur.executemany(
    """
    INSERT INTO users(username, password_hash, full_name, email, profile_id, is_active)
    VALUES (?,?,?,?,?,?)
    """,
    users,
)

conn.commit()
conn.close()

print(f"OK: creado {db_path}")
print("Usuarios: admin/admin123 , doctor1/doctor123")
print("Correo admin: gilgustavo062@gmail.com")
print("Acceso: ahora todo se controla por perfiles, vistas y reglas por columnas, no por roles.")

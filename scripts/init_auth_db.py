import sqlite3
from pathlib import Path
from passlib.hash import pbkdf2_sha256

Path("data").mkdir(exist_ok=True)
db_path = Path("data/auth.db")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
""")

users = [
    ("admin", pbkdf2_sha256.hash("admin123"), "admin"),
    ("doctor1", pbkdf2_sha256.hash("doctor123"), "user"),
]
cur.executemany("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)", users)

conn.commit()
conn.close()
print(f"OK: creado {db_path}")
print("Usuarios: admin/admin123 , doctor1/doctor123")
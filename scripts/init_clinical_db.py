import sqlite3
from pathlib import Path

Path("data").mkdir(exist_ok=True)
db_path = Path("data/clinical.db")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS medications;
DROP TABLE IF EXISTS lab_results;
DROP TABLE IF EXISTS diagnoses;
DROP TABLE IF EXISTS encounters;
DROP TABLE IF EXISTS patients;

CREATE TABLE patients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  sex TEXT NOT NULL,
  birth_date TEXT NOT NULL
);

CREATE TABLE encounters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  reason TEXT,
  FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE diagnoses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL,
  icd10_code TEXT NOT NULL,
  description TEXT NOT NULL,
  diagnosed_at TEXT NOT NULL,
  FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE lab_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL,
  test_name TEXT NOT NULL,
  value_num REAL,
  unit TEXT,
  taken_at TEXT NOT NULL,
  FOREIGN KEY(patient_id) REFERENCES patients(id)
);

CREATE TABLE medications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL,
  med_name TEXT NOT NULL,
  started_at TEXT NOT NULL,
  FOREIGN KEY(patient_id) REFERENCES patients(id)
);
""")

patients = [
    ("Juan Perez", "M", "1980-05-12"),
    ("Maria Lopez", "F", "1992-09-21"),
    ("Carlos Rojas", "M", "1975-01-03"),
]
cur.executemany("INSERT INTO patients(full_name, sex, birth_date) VALUES (?,?,?)", patients)

encounters = [
    (1, "2025-01-10", "Control diabetes"),
    (2, "2025-02-04", "Dolor de cabeza"),
    (3, "2025-03-18", "Control general"),
]
cur.executemany("INSERT INTO encounters(patient_id, started_at, reason) VALUES (?,?,?)", encounters)

diagnoses = [
    (1, "E11", "Diabetes mellitus tipo 2", "2024-11-10"),
    (2, "I10", "Hipertensión esencial", "2023-06-02"),
    (3, "E11", "Diabetes mellitus tipo 2", "2022-01-15"),
]
cur.executemany("INSERT INTO diagnoses(patient_id, icd10_code, description, diagnosed_at) VALUES (?,?,?,?)", diagnoses)

labs = [
    (1, "HbA1c", 7.2, "%", "2025-01-10"),
    (1, "HbA1c", 6.8, "%", "2025-06-10"),
    (3, "Hemoglobina glicosilada", 8.1, "%", "2025-02-01"),
]
cur.executemany("INSERT INTO lab_results(patient_id, test_name, value_num, unit, taken_at) VALUES (?,?,?,?,?)", labs)

meds = [
    (1, "Metformina", "2024-11-10"),
    (2, "Losartán", "2023-06-02"),
]
cur.executemany("INSERT INTO medications(patient_id, med_name, started_at) VALUES (?,?,?)", meds)

conn.commit()
conn.close()
print(f"OK: creado {db_path}")
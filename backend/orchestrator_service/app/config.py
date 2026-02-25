from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # JWT / auth
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # DBs (separadas: auth vs clínica)
    AUTH_DB_URL: str = "sqlite:///./data/auth.db"
    CLINICAL_DB_URL: str = "sqlite:///./data/clinical.db"

    # Logs (NoSQL documental -> por ahora JSON)
    LOG_DB_PATH: str = "./data/logs.json"

    # Translator service
    TRANSLATOR_URL: str = "http://127.0.0.1:8001/translate"
    DB_DIALECT: str = "sqlite"

    # Guardrails
    ALLOWED_TABLES: str = "patients,encounters,diagnoses,lab_results,medications"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

settings = Settings()
Path("data").mkdir(exist_ok=True)
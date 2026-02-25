from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT (lo emite Identity /auth; aquí solo se valida y extrae user_id) :contentReference[oaicite:4]{index=4}
    JWT_SECRET: str
    JWT_ALG: str = "HS256"

    # Servicios según arquitectura: /translate y gestor SQL /execute :contentReference[oaicite:5]{index=5}
    TRANSLATOR_URL: str
    QUERY_URL: str

    # Logs NoSQL (MongoDB) :contentReference[oaicite:6]{index=6}
    MONGO_URI: str
    MONGO_DB: str = "nl2sql_logs"
    MONGO_COLLECTION: str = "queries"

    # Export
    EXPORT_MAX_ROWS: int = 10000  # coherente con NFR (hasta 10k registros) :contentReference[oaicite:7]{index=7}

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

settings = Settings()
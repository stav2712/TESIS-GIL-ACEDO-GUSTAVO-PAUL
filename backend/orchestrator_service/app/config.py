from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"

    TRANSLATOR_URL: str
    QUERY_URL: str

    MONGO_URI: str
    MONGO_DB: str = "nl2sql_logs"
    MONGO_COLLECTION: str = "queries"
    MONGO_CONVERSATIONS_COLLECTION: str = "conversations"

    EXPORT_MAX_ROWS: int = 10000
    CORS_ORIGINS: str = "http://localhost:5173"

settings = Settings()
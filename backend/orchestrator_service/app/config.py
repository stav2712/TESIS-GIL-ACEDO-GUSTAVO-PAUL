from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"

    TRANSLATOR_URL: str
    QUERY_URL: str
    TERMINOLOGY_URL: str = "http://127.0.0.1:8004"

    MONGO_URI: str
    MONGO_DB: str = "nl2sql_logs"
    MONGO_COLLECTION: str = "queries"
    MONGO_CONVERSATIONS_COLLECTION: str = "conversations"

    EXPORT_MAX_ROWS: int = 10000
    CORS_ORIGINS: str = "http://localhost:5173"

    SCHEMA_PROFILE_PATH: str = "./data/schema/default_reporting_profile.json"


settings = Settings()
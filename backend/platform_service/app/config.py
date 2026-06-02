from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    CORS_ORIGINS: str = "http://localhost:5173"

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "nl2sql_logs"
    MONGO_PLATFORM_TEMPLATES_COLLECTION: str = "platform_query_templates"


settings = Settings()

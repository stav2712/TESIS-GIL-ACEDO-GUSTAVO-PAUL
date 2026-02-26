from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CLINICAL_DB_URL: str
    DB_DIALECT: str = "sqlite"
    ALLOWED_TABLES: str

settings = Settings()
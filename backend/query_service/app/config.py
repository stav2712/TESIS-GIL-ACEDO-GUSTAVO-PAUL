from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CLINICAL_DB_URL: str
    DB_DIALECT: str = "sqlite"
    ALLOWED_TABLES: str
    class Config:
        env_file = ".env"

settings = Settings()
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CLINICAL_DB_URL: str
    DB_DIALECT: str = "sqlite"
    ALLOWED_TABLES: str

    # Límite visual por defecto. El orquestador puede mandar uno menor por perfil.
    # 0 o None = sin límite visual.
    QUERY_DISPLAY_MAX_ROWS: int = 5000


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"

    TRANSLATOR_URL: str
    TRANSLATOR_TIMEOUT_SECONDS: float = 180.0

    QUERY_URL: str
    TERMINOLOGY_URL: str = "http://127.0.0.1:8004"

    MONGO_URI: str
    MONGO_DB: str = "nl2sql_logs"
    MONGO_COLLECTION: str = "queries"
    MONGO_CONVERSATIONS_COLLECTION: str = "conversations"

    # 0 = sin límite duro de exportación. El límite visual/paginado vive abajo.
    EXPORT_MAX_ROWS: int = 0
    EXPORT_PAGE_SIZE: int = 1000

    # Límite máximo de filas navegables/mostrables en UI.
    # Exportación NO usa este límite.
    QUERY_DISPLAY_MAX_ROWS: int = 5000

    CORS_ORIGINS: str = "http://localhost:5173"
    SCHEMA_PROFILE_PATH: str = "./data/schema/default_reporting_profile.json"
    QUERY_TIMEOUT_SECONDS: float = 300.0

    # Archivo seguro para sobrescrituras operativas editadas desde el panel.
    # No guarda secretos ni URLs internas; solo límites de uso.
    SYSTEM_RUNTIME_CONFIG_PATH: str = "./data/system_runtime_config.json"

    # El orquestador también lee esto para mostrar configuración y validar perfiles.
    ALLOWED_TABLES: str = ""


settings = Settings()

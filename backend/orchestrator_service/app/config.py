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
    MONGO_QUERY_JOBS_COLLECTION: str = "query_jobs"

    # 0 = sin límite duro de exportación. El límite visual/paginado vive abajo.
    EXPORT_MAX_ROWS: int = 0
    EXPORT_PAGE_SIZE: int = 1000

    # Límite máximo de filas navegables/mostrables en UI.
    # Exportación y envío por correo NO usan este límite; usan EXPORT_MAX_ROWS.
    QUERY_DISPLAY_MAX_ROWS: int = 5000

    CORS_ORIGINS: str = "http://localhost:5173"
    SCHEMA_PROFILE_PATH: str = "./data/schema/default_reporting_profile.json"
    QUERY_TIMEOUT_SECONDS: float = 300.0

    # Archivo seguro para sobrescrituras operativas editadas desde el panel.
    # No guarda secretos ni URLs internas; solo límites de uso.
    SYSTEM_RUNTIME_CONFIG_PATH: str = "./data/system_runtime_config.json"

    # El orquestador también lee esto para mostrar configuración y validar perfiles.
    ALLOWED_TABLES: str = ""

    # =========================
    # NL INPUT GUARD
    # =========================
    # Capa previa al traductor. Rechaza saludos puros, texto genérico,
    # temas ajenos al dominio clínico/reporting e intentos de manipulación.
    NL_GUARD_ENABLED: bool = True

    # Si OPENAI_GUARD_ENABLED=true y OPENAI_API_KEY está configurado,
    # el orquestador usa OpenAI para clasificar la intención antes del modelo NL2SQL.
    # Si está apagado, queda activo el validador local conservador.
    OPENAI_GUARD_ENABLED: bool = False
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_GUARD_MODEL: str = "gpt-4o-mini"
    OPENAI_GUARD_TIMEOUT_SECONDS: float = 8.0
    OPENAI_GUARD_MIN_CONFIDENCE: float = 0.55

    # false = si OpenAI falla, se usa la regla local como respaldo.
    # true = si OpenAI falla, se bloquea temporalmente la consulta con 503.
    OPENAI_GUARD_FAIL_CLOSED: bool = False

    # =========================
    # EMAIL / SMTP
    # =========================
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "empresa REPORTS"
    EMAIL_TIMEOUT_SECONDS: float = 30.0


settings = Settings()

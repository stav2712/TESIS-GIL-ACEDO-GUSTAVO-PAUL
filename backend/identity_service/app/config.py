from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    AUTH_DB_URL: str

    # Valor global de visualización. Se conserva aquí solo para firmar tokens
    # informativos; el orquestador aplica la regla real desde su propia config.
    QUERY_DISPLAY_MAX_ROWS: int = 5000


settings = Settings()

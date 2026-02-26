from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SYNONYMS_CSV: str = "./data/terminology/synonyms.csv"

settings = Settings()
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SYNONYMS_CSV: str = "./data/terminology/synonyms.csv"
    CONCEPTS_CSV: str = "./data/terminology/concepts.csv"
    VALUES_CSV: str = "./data/terminology/value_map.csv"

settings = Settings()
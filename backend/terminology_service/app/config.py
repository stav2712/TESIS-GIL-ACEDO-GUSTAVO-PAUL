from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SYNONYMS_CSV: str = "./data/terminology/synonyms.csv"
    class Config:
        env_file = ".env"

settings = Settings()
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    AUTH_DB_URL: str

    class Config:
        env_file = ".env"

settings = Settings()
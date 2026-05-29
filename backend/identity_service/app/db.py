from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


connect_args = {}
if settings.AUTH_DB_URL.startswith("sqlite"):
    # FastAPI ejecuta endpoints sync en un threadpool. Con SQLite, este flag
    # evita errores intermitentes de uso de conexiones entre hilos.
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.AUTH_DB_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

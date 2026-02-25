from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="user")  # permisos diferenciados (tesis)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
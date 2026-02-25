from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .db import Base, engine, get_db
from .models import User
from .security import hash_password, verify_password, create_jwt

app = FastAPI(title="Identity Service")

class AuthIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "user"

@app.get("/health")
def health():
    return {"ok": True}

# Endpoint pedido por la tesis: "/auth" para validar y emitir JWT
@app.post("/auth", response_model=TokenOut)
def auth(payload: AuthIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == payload.username).first()
    if not u or not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    return TokenOut(access_token=create_jwt(u.id, u.role))

# Utilidad DEV (puedes quitarlo luego)
@app.post("/users")
def create_user(payload: CreateUserIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Usuario ya existe")
    u = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(u); db.commit(); db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role}

Base.metadata.create_all(bind=engine)
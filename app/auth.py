from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app import models, schemas
from app.security import security_manager

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def normalize_email(email: str) -> str:
    # e-mails are matched by their hash, so "Lucas@Mail.fr" and "lucas@mail.fr" must hash the same
    return email.strip().lower()


def get_user_by_email(db: Session, email: str):
    """
    Trouve un utilisateur par email, en utilisant le hash pour la recherche
    """
    email_hash = security_manager.hash_value(normalize_email(email))
    return db.query(models.User).filter(models.User.email_hash == email_hash).first()


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Récupère l'utilisateur courant à partir du token JWT.
    
    La fonction décode le token, extrait l'email, puis cherche l'utilisateur
    correspondant dans la base de données en utilisant le hash de l'email.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Décodage du token JWT
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # the subject is the user id: an e-mail would stop matching as soon as the member changes it
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    # Création d'un dictionnaire contenant les informations déchiffrées
    return schemas.User(
        id=user.id,
        email=security_manager.decrypt_value(user.email_encrypted),
        username= security_manager.decrypt_value(user.username_encrypted),
        phone=security_manager.decrypt_value(user.phone_encrypted),
        is_active=user.is_active,
        is_botanist=user.is_botanist,
        botanist_verified=user.botanist_verified,
        is_admin=user.email in settings.ADMIN_EMAILS,
    )


async def get_admin_user(current_user: schemas.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user


async def get_verified_botanist(current_user: schemas.User = Depends(get_current_user)):
    if not (current_user.is_botanist and current_user.botanist_verified):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verified botanists only")
    return current_user


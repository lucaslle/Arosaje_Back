from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import auth
from app.database import get_db
from app.config import settings
from app.observability import observability, trace_function, get_logger

router = APIRouter()
logger = get_logger()

@router.post("/token", tags=["Authentication"])
@trace_function("user_authentication")
async def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT token."""
    user = auth.get_user_by_email(db, form_data.username)

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        logger.warning("Failed login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )

    logger.info("User login successful", user_id=user.id, is_botanist=user.is_botanist)
    observability.set_current_user(str(user.id))

    return {"access_token": access_token, "token_type": "bearer"}

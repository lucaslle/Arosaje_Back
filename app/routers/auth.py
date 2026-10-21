from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import auth
from app.database import get_db
from app.config import settings
from app.observability import observability, trace_function, get_logger

router = APIRouter()
logger = get_logger()

# shortcut: failures live in this process's memory, enough for one API process; move them to Redis when there are several
MAX_FAILURES_PER_EMAIL = 10
MAX_FAILURES_PER_IP = 30
FAILURE_WINDOW = timedelta(minutes=15)
_failures: dict[str, deque] = defaultdict(deque)


def _recent_failures(key: str, now: datetime) -> deque:
    attempts = _failures[key]
    while attempts and now - attempts[0] > FAILURE_WINDOW:
        attempts.popleft()
    return attempts


def _forget_old_failures(now: datetime):
    for key in [key for key in _failures if not _recent_failures(key, now)]:
        del _failures[key]

@router.post("/token", tags=["Authentication"])
@trace_function("user_authentication")
async def login(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT token; too many failures lock the address and the account for a while."""
    now = datetime.now()
    email_key = f"email:{auth.normalize_email(form_data.username)}"
    ip_key = f"ip:{request.client.host if request.client else 'unknown'}"
    if len(_recent_failures(email_key, now)) >= MAX_FAILURES_PER_EMAIL or len(_recent_failures(ip_key, now)) >= MAX_FAILURES_PER_IP:
        logger.warning("Login throttled")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts, try again later",
            headers={"Retry-After": str(int(FAILURE_WINDOW.total_seconds()))},
        )

    user = auth.get_user_by_email(db, form_data.username)

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        _failures[email_key].append(now)
        _failures[ip_key].append(now)
        if len(_failures) > 10_000:
            _forget_old_failures(now)
        logger.warning("Failed login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _failures.pop(email_key, None)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    logger.info("User login successful", user_id=user.id, is_botanist=user.is_botanist)
    observability.set_current_user(str(user.id))

    return {"access_token": access_token, "token_type": "bearer"}

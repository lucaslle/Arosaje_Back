from fastapi import APIRouter, Depends, HTTPException
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.routers.plants import delete_photo
from app.database import get_db
from app.security import security_manager
from app.observability import observability, trace_function, get_logger

router = APIRouter()
logger = get_logger()

@router.post("/users/", response_model=schemas.User, tags=["Users"])
@trace_function("user_creation")
async def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new user with hashing and encryption."""
    logger.info("Creating new user", is_botanist=user.is_botanist)

    email_hash = security_manager.hash_value(user.email)
    db_user = db.query(models.User).filter(models.User.email_hash == email_hash).first()
    if db_user:
        logger.warning("User creation failed - email already exists")
        raise HTTPException(status_code=400, detail="Email already registered")

    username_hash = security_manager.hash_value(user.username)
    db_user = db.query(models.User).filter(models.User.username_hash == username_hash).first()
    if db_user:
        logger.warning("User creation failed - username already exists")
        raise HTTPException(status_code=400, detail="Username already taken")

    db_user = models.User(
        email_hash=email_hash,
        username_hash=username_hash,
        phone_hash=security_manager.hash_value(user.phone),
        email_encrypted=security_manager.encrypt_value(user.email),
        username_encrypted=security_manager.encrypt_value(user.username),
        phone_encrypted=security_manager.encrypt_value(user.phone),
        hashed_password=auth.get_password_hash(user.password),
        is_botanist=user.is_botanist,
        is_active=True
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    user_type = "botanist" if user.is_botanist else "regular"
    observability.record_user_registration(user_type)

    logger.info("User created successfully", user_id=db_user.id, user_type=user_type)

    return {
        "id": db_user.id,
        "email": security_manager.decrypt_value(db_user.email_encrypted),
        "username": security_manager.decrypt_value(db_user.username_encrypted),
        "phone": security_manager.decrypt_value(db_user.phone_encrypted),
        "is_active": db_user.is_active,
        "is_botanist": db_user.is_botanist
    }

@router.put("/users/{user_id}", response_model=schemas.User, tags=["Users"])
@trace_function("user_update")
async def edit_user(
        user_id: int,
        email: EmailStr = None,
        username: str = None,
        phone: str = None,
        is_botanist: bool = None,
        current_user: schemas.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Update an existing user account."""
    logger.info("Updating user", user_id=user_id, current_user_id=current_user.id)

    if user_id != current_user.id:
        logger.warning("Unauthorized user update attempt",
                       target_user_id=user_id,
                       current_user_id=current_user.id)
        raise HTTPException(status_code=403, detail="Not authorized to update other users")

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        logger.error("User not found for update", user_id=user_id)
        raise HTTPException(status_code=404, detail="User not found")

    if email and email != current_user.email:
        email_hash = security_manager.hash_value(email)
        existing_user = db.query(models.User).filter(models.User.email_hash == email_hash).first()
        if existing_user and existing_user.id != user_id:
            logger.warning("Email already taken", user_id=user_id)
            raise HTTPException(status_code=400, detail="Email already registered")

    if username and username != current_user.username:
        username_hash = security_manager.hash_value(username)
        existing_user = db.query(models.User).filter(models.User.username_hash == username_hash).first()
        if existing_user and existing_user.id != user_id:
            logger.warning("Username already taken", user_id=user_id)
            raise HTTPException(status_code=400, detail="Username already taken")

    if email is not None:
        db_user.email_hash = security_manager.hash_value(email)
        db_user.email_encrypted = security_manager.encrypt_value(email)
    if username is not None:
        db_user.username_hash = security_manager.hash_value(username)
        db_user.username_encrypted = security_manager.encrypt_value(username)
    if phone is not None:
        db_user.phone_hash = security_manager.hash_value(phone)
        db_user.phone_encrypted = security_manager.encrypt_value(phone)
    if is_botanist is not None:
        db_user.is_botanist = is_botanist

    db.commit()
    db.refresh(db_user)

    logger.info("User updated successfully", user_id=user_id)

    return {
        "id": db_user.id,
        "email": security_manager.decrypt_value(db_user.email_encrypted),
        "username": security_manager.decrypt_value(db_user.username_encrypted),
        "phone": security_manager.decrypt_value(db_user.phone_encrypted),
        "is_active": db_user.is_active,
        "is_botanist": db_user.is_botanist
    }

@router.get("/users/me/", response_model=schemas.User, tags=["Users"])
@trace_function("get_current_user")
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    """Get details of the currently authenticated user."""
    logger.info("Getting current user details", user_id=current_user.id)
    return current_user

@router.delete("/users/", response_model=schemas.User, tags=["Users"])
@trace_function("user_deletion")
async def delete_user(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Delete a user account."""
    logger.info("Deleting user", user_id=id, current_user_id=current_user.id)

    if id != current_user.id:
        logger.warning("Unauthorized user deletion attempt", target_user_id=id, current_user_id=current_user.id)
        raise HTTPException(status_code=403, detail="Not authorized to delete other users")

    db_user = db.query(models.User).filter(models.User.id == id).first()
    if not db_user:
        logger.error("User not found for deletion", user_id=id)
        raise HTTPException(status_code=404, detail="User not found")

    deleted_user = schemas.User.model_validate(db_user)
    # plants this member was looking after go back to their owners; owned plants are deleted by cascade
    db.query(models.Plant).filter(models.Plant.in_care_id == id).update({"in_care_id": None}, synchronize_session=False)
    photo_urls = [plant.photo_url for plant in db_user.owned_plants]
    db.delete(db_user)
    db.commit()
    for photo_url in photo_urls:
        delete_photo(photo_url)

    logger.info("User deleted successfully", user_id=id)
    return deleted_user

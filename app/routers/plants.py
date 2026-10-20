import os
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.config import settings
from app.database import get_db
from app.observability import observability, trace_function, get_logger

router = APIRouter()
logger = get_logger()


async def save_photo(photo: UploadFile) -> str:
    """Store an uploaded photo under a random name and return the URL path it is served at."""
    extension = os.path.splitext(photo.filename or "")[1].lower().lstrip(".")
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported photo format")

    content = await photo.read(settings.MAX_FILE_SIZE + 1)
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Photo too large")

    filename = f"{uuid4().hex}.{extension}"
    with open(os.path.join(settings.UPLOAD_DIRECTORY, filename), "wb") as buffer:
        buffer.write(content)
    return f"photos/{filename}"


def delete_photo(photo_url: str | None):
    if not photo_url:
        return
    path = os.path.join(settings.UPLOAD_DIRECTORY, os.path.basename(photo_url))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError as e:
        logger.warning("Error removing photo", error=str(e))


def get_plant_or_404(db: Session, plant_id: int) -> models.Plant:
    plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if not plant:
        logger.error("Plant not found", plant_id=plant_id)
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.post("/plants/", response_model=schemas.Plant, tags=["Plants"])
@trace_function("plant_creation")
async def create_plant(
        name: str,
        location: str,
        care_instructions: str | None = None,
        photo: UploadFile = File(),
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Create a new plant entry."""
    logger.info("Creating new plant", owner_id=current_user.id)

    db_plant = models.Plant(
        name=name,
        location=location,
        care_instructions=care_instructions,
        owner_id=current_user.id,
        photo_url=await save_photo(photo),
    )

    db.add(db_plant)
    db.commit()
    db.refresh(db_plant)

    owner_type = "botanist" if current_user.is_botanist else "regular"
    observability.record_plant_creation(owner_type)

    logger.info("Plant created successfully", plant_id=db_plant.id, owner_type=owner_type)
    return db_plant

@router.put("/plants/{plant_id}", response_model=schemas.Plant, tags=["Plants"])
@trace_function("plant_update")
async def update_plant(
        plant_id: int,
        name: str = None,
        location: str = None,
        care_instructions: str | None = None,
        care_requested: bool | None = None,
        photo: UploadFile = File(None),
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Update an existing plant."""
    logger.info("Updating plant", plant_id=plant_id, user_id=current_user.id)

    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id,
        models.Plant.owner_id == current_user.id
    ).first()

    if plant is None:
        logger.error("Plant not found or not owned by user", plant_id=plant_id, user_id=current_user.id)
        raise HTTPException(status_code=404, detail="Plant not found or not owned by current user")

    if name is not None:
        plant.name = name
    if location is not None:
        plant.location = location
    if care_instructions is not None:
        plant.care_instructions = care_instructions
    if care_requested is not None:
        plant.care_requested = care_requested

    old_photo = None
    if photo and photo.filename:
        old_photo = plant.photo_url
        plant.photo_url = await save_photo(photo)

    db.commit()
    db.refresh(plant)

    delete_photo(old_photo)

    logger.info("Plant updated successfully", plant_id=plant_id)
    return plant

@router.delete("/plants", response_model=schemas.Plant, tags=["Plants"])
@trace_function("plant_deletion")
async def delete_plant(
        plant_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Delete a plant."""
    logger.info("Deleting plant", plant_id=plant_id, user_id=current_user.id)

    plant = get_plant_or_404(db, plant_id)

    if plant.owner_id != current_user.id:
        logger.warning("Unauthorized plant deletion attempt", plant_id=plant_id, user_id=current_user.id)
        raise HTTPException(status_code=403, detail="Not authorized to delete this plant")

    # the deleted row can no longer be loaded after commit, serialize it first
    deleted_plant = schemas.Plant.model_validate(plant)
    try:
        db.delete(plant)
        db.commit()
    except Exception as e:
        logger.error("Error deleting plant", plant_id=plant_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error deleting plant")
    delete_photo(deleted_plant.photo_url)
    logger.info("Plant deleted successfully", plant_id=plant_id)
    return deleted_plant

@router.get("/my_plants/", response_model=list[schemas.Plant], tags=["Plants"])
@trace_function("list_user_plants")
async def list_plants_users_plant(
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """List all plants owned by the current user."""
    plants = db.query(models.Plant).filter(models.Plant.owner_id == current_user.id).all()
    logger.info("User plants retrieved", user_id=current_user.id, count=len(plants))
    return plants

@router.get("/all_plants/", response_model=list[schemas.Plant], tags=["Plants"])
@trace_function("list_all_plants")
async def list_all_plants_except_users(
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """List all plants except those owned by the current user."""
    plants = db.query(models.Plant).filter(models.Plant.owner_id != current_user.id).all()
    logger.info("All plants retrieved", user_id=current_user.id, count=len(plants))
    return plants

@router.put("/plants/{plant_id}/start-care", response_model=schemas.Plant, tags=["Plant Care"])
@trace_function("start_plant_care")
async def start_plant_care(
        plant_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Take care of a plant whose owner asked for a sitter."""
    logger.info("Starting plant care", plant_id=plant_id, sitter_id=current_user.id)

    # check and write in one statement so two members cannot both take the plant
    taken = db.query(models.Plant).filter(
        models.Plant.id == plant_id,
        models.Plant.owner_id != current_user.id,
        models.Plant.in_care_id.is_(None),
        models.Plant.care_requested.is_(True),
    ).update({"in_care_id": current_user.id, "care_requested": False}, synchronize_session=False)
    db.commit()

    plant = get_plant_or_404(db, plant_id)
    if not taken:
        raise HTTPException(status_code=409, detail="Plant is not waiting for a sitter")

    observability.record_care_request("start")
    logger.info("Plant care started", plant_id=plant_id, sitter_id=current_user.id)
    return plant

@router.put("/plants/{plant_id}/end-care", response_model=schemas.Plant, tags=["Plant Care"])
@trace_function("end_plant_care")
async def end_plant_care(
        plant_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """End plant care."""
    logger.info("Ending plant care", plant_id=plant_id, sitter_id=current_user.id)

    plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if not plant or plant.in_care_id != current_user.id:
        logger.error("Plant not found or not caring by user", plant_id=plant_id, user_id=current_user.id)
        raise HTTPException(status_code=404, detail="Plant not found or not caring by user")

    plant.in_care_id = None
    db.commit()
    db.refresh(plant)

    observability.record_care_request("end")
    logger.info("Plant care ended", plant_id=plant_id, sitter_id=current_user.id)
    return plant

@router.get("/care-requests/", response_model=list[schemas.Plant], tags=["Plant Care"])
@trace_function("list_care_requests")
async def list_care_requests(
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """List other members' plants waiting for a sitter."""
    care_requests = db.query(models.Plant).filter(
        models.Plant.care_requested.is_(True),
        models.Plant.in_care_id.is_(None),
        models.Plant.owner_id != current_user.id
    ).all()

    logger.info("Care requests retrieved", user_id=current_user.id, count=len(care_requests))
    return care_requests

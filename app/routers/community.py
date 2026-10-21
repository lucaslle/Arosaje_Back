from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models, schemas, auth
from app.care_rules import sitter_stats
from app.database import get_db
from app.observability import trace_function, get_logger
from app.routers.plants import get_plant_or_404

router = APIRouter()
logger = get_logger()


@router.get("/favorites/", response_model=list[schemas.Plant], tags=["Favorites"])
@trace_function("list_favorites")
async def list_favorites(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return [
        favorite.plant
        for favorite in db.query(models.Favorite).options(selectinload(models.Favorite.plant))
        .filter(models.Favorite.user_id == current_user.id).order_by(models.Favorite.created_at.desc())
    ]


@router.put("/plants/{plant_id}/favorite", status_code=status.HTTP_204_NO_CONTENT, tags=["Favorites"])
@trace_function("favorite_creation")
async def add_favorite(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    get_plant_or_404(db, plant_id)
    exists = db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id, models.Favorite.plant_id == plant_id).first()
    if not exists:
        db.add(models.Favorite(user_id=current_user.id, plant_id=plant_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # a simultaneous request added it first: the plant is a favorite either way
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/plants/{plant_id}/favorite", status_code=status.HTTP_204_NO_CONTENT, tags=["Favorites"])
@trace_function("favorite_deletion")
async def remove_favorite(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id, models.Favorite.plant_id == plant_id).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plants/{plant_id}/advice-requests", response_model=schemas.AdviceRequest, status_code=status.HTTP_201_CREATED, tags=["Botanist advice"])
@trace_function("advice_request_creation")
async def ask_botanists(plant_id: int, request: schemas.AdviceRequestCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """The owner asks the verified botanists a question; they answer in the plant's comments."""
    plant = get_plant_or_404(db, plant_id)
    if plant.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the plant owner can ask for advice")
    if any(advice.status == models.AdviceStatus.OPEN.value for advice in plant.advice_requests):
        raise HTTPException(status_code=409, detail="A question is already open for this plant")
    advice = models.AdviceRequest(plant_id=plant_id, author_id=current_user.id, question=request.question.strip())
    db.add(advice)
    db.commit()
    db.refresh(advice)
    return advice


@router.get("/plants/{plant_id}/advice-requests", response_model=list[schemas.AdviceRequest], tags=["Botanist advice"])
@trace_function("list_plant_advice_requests")
async def list_plant_advice_requests(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    plant = get_plant_or_404(db, plant_id)
    if plant.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the plant owner can see its questions")
    return sorted(plant.advice_requests, key=lambda advice: advice.created_at, reverse=True)


@router.get("/advice-requests/", response_model=list[schemas.AdviceRequest], tags=["Botanist advice"])
@trace_function("list_open_advice_requests")
async def list_open_advice_requests(
        limit: int = Query(24, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current_user: models.User = Depends(auth.get_verified_botanist),
        db: Session = Depends(get_db),
):
    """Questions still waiting for a botanist, oldest first."""
    return db.query(models.AdviceRequest).filter(
        models.AdviceRequest.status == models.AdviceStatus.OPEN.value,
        models.AdviceRequest.author_id != current_user.id,
    ).order_by(models.AdviceRequest.created_at).offset(offset).limit(limit).all()


@router.put("/advice-requests/{advice_id}/close", response_model=schemas.AdviceRequest, tags=["Botanist advice"])
@trace_function("advice_request_closing")
async def close_advice_request(advice_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    advice = db.query(models.AdviceRequest).filter(models.AdviceRequest.id == advice_id).first()
    if not advice:
        raise HTTPException(status_code=404, detail="Question not found")
    if advice.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can close this question")
    advice.status = models.AdviceStatus.CLOSED.value
    db.commit()
    db.refresh(advice)
    return advice


@router.get("/users/{user_id}/profile", response_model=schemas.UserProfile, tags=["Users"])
@trace_function("get_user_profile")
async def get_user_profile(user_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return schemas.UserProfile(id=user.id, username=user.username, is_botanist=user.is_verified_botanist, **sitter_stats(db, user.id))


@router.get("/admin/botanist-requests", response_model=list[schemas.BotanistRequest], tags=["Admin"])
@trace_function("list_botanist_requests")
async def list_botanist_requests(current_user: models.User = Depends(auth.get_admin_user), db: Session = Depends(get_db)):
    """Members who said they are botanists and still wait for an admin check."""
    users = db.query(models.User).filter(models.User.is_botanist.is_(True), models.User.botanist_verified.is_(False)).all()
    return [schemas.BotanistRequest(id=user.id, username=user.username, email=user.email) for user in users]


@router.put("/admin/users/{user_id}/botanist", response_model=schemas.BotanistRequest, tags=["Admin"])
@trace_function("botanist_decision")
async def decide_botanist(user_id: int, decision: schemas.BotanistDecision, current_user: models.User = Depends(auth.get_admin_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.botanist_verified = decision.verified
    if not decision.verified:
        user.is_botanist = False
    db.commit()
    logger.info("Botanist decision", user_id=user_id, verified=decision.verified, admin_id=current_user.id)
    return schemas.BotanistRequest(id=user.id, username=user.username, email=user.email)

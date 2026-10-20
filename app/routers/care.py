from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.care_rules import sitter_stats
from app.database import get_db
from app.observability import observability, trace_function, get_logger
from app.routers.plants import get_plant_or_404, save_photo

router = APIRouter()
logger = get_logger()

PENDING = models.OfferStatus.PENDING.value
ACCEPTED = models.OfferStatus.ACCEPTED.value
COMPLETED = models.OfferStatus.COMPLETED.value


def offer_out(db: Session, offer: models.CareOffer) -> schemas.CareOffer:
    sitter = schemas.SitterPublic.model_validate(offer.sitter).model_copy(update=sitter_stats(db, offer.sitter_id))
    return schemas.CareOffer(
        id=offer.id,
        plant_id=offer.plant_id,
        status=offer.status,
        created_at=offer.created_at,
        decided_at=offer.decided_at,
        sitter=sitter,
        has_review=offer.review is not None,
    )


def get_offer_or_404(db: Session, offer_id: int) -> models.CareOffer:
    offer = db.query(models.CareOffer).filter(models.CareOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer


def require_plant_owner(plant: models.Plant, user_id: int):
    if plant.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Only the plant owner can do this")


@router.post("/plants/{plant_id}/care-offers", response_model=schemas.CareOffer, status_code=status.HTTP_201_CREATED, tags=["Plant Care"])
@trace_function("care_offer_creation")
async def create_care_offer(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Offer to look after a plant whose owner asked for a sitter."""
    plant = get_plant_or_404(db, plant_id)
    if plant.owner_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot look after your own plant")
    if not plant.care_requested or plant.in_care_id is not None:
        raise HTTPException(status_code=409, detail="Plant is not waiting for a sitter")
    already = db.query(models.CareOffer).filter(
        models.CareOffer.plant_id == plant_id,
        models.CareOffer.sitter_id == current_user.id,
        models.CareOffer.status == PENDING,
    ).first()
    if already:
        raise HTTPException(status_code=409, detail="You already offered to look after this plant")

    offer = models.CareOffer(plant_id=plant_id, sitter_id=current_user.id)
    db.add(offer)
    db.commit()
    db.refresh(offer)
    observability.record_care_request("offer")
    logger.info("Care offer created", offer_id=offer.id, plant_id=plant_id, sitter_id=current_user.id)
    return offer_out(db, offer)


@router.get("/plants/{plant_id}/care-offers", response_model=list[schemas.CareOffer], tags=["Plant Care"])
@trace_function("list_plant_care_offers")
async def list_plant_care_offers(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Offers received for one of my plants, newest first."""
    plant = get_plant_or_404(db, plant_id)
    require_plant_owner(plant, current_user.id)
    offers = db.query(models.CareOffer).filter(
        models.CareOffer.plant_id == plant_id,
        models.CareOffer.status != models.OfferStatus.CANCELLED.value,
    ).order_by(models.CareOffer.created_at.desc()).all()
    return [offer_out(db, offer) for offer in offers]


@router.get("/care-offers/mine", response_model=list[schemas.MyCareOffer], tags=["Plant Care"])
@trace_function("list_my_care_offers")
async def list_my_care_offers(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Offers I sent, so the plant list can show their status."""
    return db.query(models.CareOffer).filter(
        models.CareOffer.sitter_id == current_user.id,
        models.CareOffer.status != models.OfferStatus.CANCELLED.value,
    ).order_by(models.CareOffer.created_at.desc()).all()


@router.put("/care-offers/{offer_id}/accept", response_model=schemas.CareOffer, tags=["Plant Care"])
@trace_function("care_offer_acceptance")
async def accept_care_offer(offer_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """The owner picks this sitter: the plant is now looked after and other offers are refused."""
    offer = get_offer_or_404(db, offer_id)
    plant = offer.plant
    require_plant_owner(plant, current_user.id)
    if offer.status != PENDING:
        raise HTTPException(status_code=409, detail="Offer is no longer pending")

    # check and write in one statement so two acceptances cannot both succeed
    taken = db.query(models.Plant).filter(
        models.Plant.id == plant.id,
        models.Plant.in_care_id.is_(None),
        models.Plant.care_requested.is_(True),
    ).update({"in_care_id": offer.sitter_id, "care_requested": False}, synchronize_session=False)
    if not taken:
        db.rollback()
        raise HTTPException(status_code=409, detail="Plant is not waiting for a sitter")

    now = models.utcnow()
    offer.status = ACCEPTED
    offer.decided_at = now
    if plant.care_requested_at:
        offer.wait_seconds = int((now - plant.care_requested_at).total_seconds())
    db.query(models.CareOffer).filter(
        models.CareOffer.plant_id == plant.id,
        models.CareOffer.id != offer.id,
        models.CareOffer.status == PENDING,
    ).update({"status": models.OfferStatus.REFUSED.value, "decided_at": now}, synchronize_session=False)
    db.commit()
    db.refresh(offer)
    observability.record_care_request("start")
    logger.info("Care offer accepted", offer_id=offer.id, plant_id=plant.id)
    return offer_out(db, offer)


@router.put("/care-offers/{offer_id}/refuse", response_model=schemas.CareOffer, tags=["Plant Care"])
@trace_function("care_offer_refusal")
async def refuse_care_offer(offer_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    offer = get_offer_or_404(db, offer_id)
    require_plant_owner(offer.plant, current_user.id)
    if offer.status != PENDING:
        raise HTTPException(status_code=409, detail="Offer is no longer pending")
    offer.status = models.OfferStatus.REFUSED.value
    offer.decided_at = models.utcnow()
    db.commit()
    db.refresh(offer)
    return offer_out(db, offer)


@router.delete("/care-offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Plant Care"])
@trace_function("care_offer_withdrawal")
async def withdraw_care_offer(offer_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """The sitter takes back an offer the owner has not answered yet."""
    offer = get_offer_or_404(db, offer_id)
    if offer.sitter_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the sitter can withdraw this offer")
    if offer.status != PENDING:
        raise HTTPException(status_code=409, detail="Offer is no longer pending")
    offer.status = models.OfferStatus.CANCELLED.value
    db.commit()


def require_participant(offer: models.CareOffer, user_id: int):
    if user_id not in (offer.sitter_id, offer.plant.owner_id):
        raise HTTPException(status_code=403, detail="Only the owner and the sitter can see this conversation")


@router.get("/care-offers/{offer_id}/messages", response_model=list[schemas.Message], tags=["Messages"])
@trace_function("list_messages")
async def list_messages(offer_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    offer = get_offer_or_404(db, offer_id)
    require_participant(offer, current_user.id)
    return db.query(models.Message).filter(models.Message.offer_id == offer_id).order_by(models.Message.created_at).all()


@router.post("/care-offers/{offer_id}/messages", response_model=schemas.Message, status_code=status.HTTP_201_CREATED, tags=["Messages"])
@trace_function("message_creation")
async def send_message(offer_id: int, message: schemas.MessageCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    offer = get_offer_or_404(db, offer_id)
    require_participant(offer, current_user.id)
    if offer.status not in (PENDING, ACCEPTED):
        raise HTTPException(status_code=409, detail="This conversation is closed")
    db_message = models.Message(offer_id=offer_id, sender_id=current_user.id, text=message.text.strip())
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


@router.post("/care-offers/{offer_id}/review", response_model=schemas.Review, status_code=status.HTTP_201_CREATED, tags=["Reviews"])
@trace_function("review_creation")
async def review_sitter(offer_id: int, review: schemas.ReviewCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """The owner rates the sitter once the care is over."""
    offer = get_offer_or_404(db, offer_id)
    require_plant_owner(offer.plant, current_user.id)
    if offer.status != COMPLETED:
        raise HTTPException(status_code=409, detail="You can only review a finished care")
    if offer.review is not None:
        raise HTTPException(status_code=409, detail="This care was already reviewed")
    db_review = models.Review(
        offer_id=offer.id,
        author_id=current_user.id,
        sitter_id=offer.sitter_id,
        rating=review.rating,
        comment=review.comment,
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


def can_read_care_log(db: Session, plant: models.Plant, user_id: int) -> bool:
    if user_id in (plant.owner_id, plant.in_care_id):
        return True
    return db.query(models.CareOffer).filter(
        models.CareOffer.plant_id == plant.id,
        models.CareOffer.sitter_id == user_id,
        models.CareOffer.status.in_((ACCEPTED, COMPLETED)),
    ).first() is not None


@router.get("/plants/{plant_id}/care-logs", response_model=list[schemas.CareLog], tags=["Care journal"])
@trace_function("list_care_logs")
async def list_care_logs(plant_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    plant = get_plant_or_404(db, plant_id)
    if not can_read_care_log(db, plant, current_user.id):
        raise HTTPException(status_code=403, detail="Only the owner and the sitters can read this journal")
    return db.query(models.CareLog).filter(models.CareLog.plant_id == plant_id).order_by(models.CareLog.created_at.desc()).all()


@router.post("/plants/{plant_id}/care-logs", response_model=schemas.CareLog, status_code=status.HTTP_201_CREATED, tags=["Care journal"])
@trace_function("care_log_creation")
async def add_care_log(
        plant_id: int,
        text: str = Form(..., min_length=1, max_length=1000),
        photo: UploadFile | None = File(None),
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db),
):
    """The current sitter writes in the care journal, optionally with a photo."""
    plant = get_plant_or_404(db, plant_id)
    if plant.in_care_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the current sitter can write in the journal")
    log = models.CareLog(
        plant_id=plant_id,
        author_id=current_user.id,
        text=text.strip(),
        photo_url=await save_photo(photo) if photo and photo.filename else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

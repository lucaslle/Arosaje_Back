from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def expire_cares(db: Session) -> None:
    """Close care requests and cares whose end date has passed."""
    # shortcut: expiry runs lazily when plants are listed; move it to a scheduled job if lists stop being read daily
    today = date.today()
    expired = db.query(models.Plant).filter(models.Plant.care_end.isnot(None), models.Plant.care_end < today).all()
    for plant in expired:
        for offer in plant.care_offers:
            if offer.status == models.OfferStatus.PENDING.value:
                offer.status = models.OfferStatus.CANCELLED.value
            elif offer.status == models.OfferStatus.ACCEPTED.value:
                offer.status = models.OfferStatus.COMPLETED.value
        plant.care_requested = False
        plant.in_care_id = None
        plant.care_start = None
        plant.care_end = None
    if expired:
        db.commit()


def sitter_stats(db: Session, user_id: int) -> dict:
    average, count = db.query(func.avg(models.Review.rating), func.count(models.Review.id)).filter(
        models.Review.sitter_id == user_id
    ).one()
    completed = db.query(func.count(models.CareOffer.id)).filter(
        models.CareOffer.sitter_id == user_id,
        models.CareOffer.status == models.OfferStatus.COMPLETED.value,
    ).scalar()
    return {
        "rating_average": round(float(average), 1) if average is not None else None,
        "rating_count": count,
        "completed_cares": completed,
    }

"""Business gauges computed from the database each time Prometheus scrapes /metrics."""
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import func

from app import models
from app.database import SessionLocal


class BusinessMetrics(Collector):
    def collect(self):
        db = SessionLocal()
        try:
            plants = db.query(models.Plant)
            offers = db.query(models.CareOffer)
            values = {
                "plant_care_plants_total": ("Plants registered", plants.count()),
                "plant_care_plants_waiting_sitter": (
                    "Plants whose owner asked for a sitter and has none yet",
                    plants.filter(models.Plant.care_requested.is_(True), models.Plant.in_care_id.is_(None)).count(),
                ),
                "plant_care_plants_being_cared": ("Plants currently looked after", plants.filter(models.Plant.in_care_id.isnot(None)).count()),
                "plant_care_offers_pending": (
                    "Care offers waiting for the owner's answer",
                    offers.filter(models.CareOffer.status == models.OfferStatus.PENDING.value).count(),
                ),
                "plant_care_cares_completed_total": (
                    "Cares finished so far",
                    offers.filter(models.CareOffer.status == models.OfferStatus.COMPLETED.value).count(),
                ),
                "plant_care_average_wait_seconds": (
                    "Average time between a care request and the accepted offer",
                    db.query(func.avg(models.CareOffer.wait_seconds)).scalar() or 0,
                ),
                "plant_care_advice_requests_open": (
                    "Questions waiting for a botanist",
                    db.query(models.AdviceRequest).filter(models.AdviceRequest.status == models.AdviceStatus.OPEN.value).count(),
                ),
                "plant_care_botanists_waiting_verification": (
                    "Members who claim to be botanists and wait for an admin",
                    db.query(models.User).filter(models.User.is_botanist.is_(True), models.User.botanist_verified.is_(False)).count(),
                ),
                "plant_care_average_rating": (
                    "Average rating given to sitters",
                    db.query(func.avg(models.Review.rating)).scalar() or 0,
                ),
            }
        finally:
            db.close()

        for name, (documentation, value) in values.items():
            gauge = GaugeMetricFamily(name, documentation)
            gauge.add_metric([], float(value))
            yield gauge

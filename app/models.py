import enum
from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone
from app.security import security_manager

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    
    email_hash = Column(String(64), unique=True, index=True)
    email_encrypted = Column(String(500))
    
    username_hash = Column(String(64), unique=True, index=True)
    username_encrypted = Column(String(500))
    
    phone_hash = Column(String(64), index=True)
    phone_encrypted = Column(String(500))
    
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    # is_botanist is what the member claims; only an admin sets botanist_verified
    is_botanist = Column(Boolean, default=False)
    botanist_verified = Column(Boolean, default=False, nullable=False)
    
    owned_plants = relationship("Plant",
                               back_populates="owner",
                               foreign_keys="[Plant.owner_id]",
                               cascade="all, delete-orphan")
    comments = relationship("Comment", 
                           back_populates="user",
                           cascade="all, delete-orphan")
    care_offers = relationship("CareOffer", back_populates="sitter", cascade="all, delete-orphan")
    favorites = relationship("Favorite", cascade="all, delete-orphan")
    care_logs = relationship("CareLog", cascade="all, delete-orphan")
    messages = relationship("Message", cascade="all, delete-orphan")
    advice_requests = relationship("AdviceRequest", cascade="all, delete-orphan")
    reviews_written = relationship("Review", foreign_keys="[Review.author_id]", cascade="all, delete-orphan")

    @property
    def is_verified_botanist(self):
        return bool(self.is_botanist and self.botanist_verified)
    
    @property
    def email(self):
        return security_manager.decrypt_value(self.email_encrypted) if self.email_encrypted else None
    
    @email.setter
    def email(self, value):
        if value is not None:
            self.email_hash = security_manager.hash_value(value)
            self.email_encrypted = security_manager.encrypt_value(value)
    
    @property
    def username(self):
        return security_manager.decrypt_value(self.username_encrypted) if self.username_encrypted else None
    
    @username.setter
    def username(self, value):
        if value is not None:
            self.username_hash = security_manager.hash_value(value)
            self.username_encrypted = security_manager.encrypt_value(value)
    
    @property
    def phone(self):
        return security_manager.decrypt_value(self.phone_encrypted) if self.phone_encrypted else None
    
    @phone.setter
    def phone(self, value):
        if value is not None:
            self.phone_hash = security_manager.hash_value(value)
            self.phone_encrypted = security_manager.encrypt_value(value)


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    location = Column(String)
    care_instructions = Column(String)
    photo_url = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # in_care_id is the member currently looking after the plant
    in_care_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    care_requested = Column(Boolean, default=False, nullable=False)
    care_requested_at = Column(DateTime, nullable=True)
    care_start = Column(Date, nullable=True)
    care_end = Column(Date, nullable=True)
    
    owner = relationship("User",
                        foreign_keys=[owner_id],
                        back_populates="owned_plants",
                        lazy="joined")
    comments = relationship("Comment", 
                          back_populates="plant",
                          cascade="all, delete-orphan")
    care_offers = relationship("CareOffer", back_populates="plant", cascade="all, delete-orphan")
    care_logs = relationship("CareLog", back_populates="plant", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="plant", cascade="all, delete-orphan")
    advice_requests = relationship("AdviceRequest", back_populates="plant", cascade="all, delete-orphan")
    
    @property
    def in_care(self):
        return self.in_care_id is not None


class Comment(Base):
    __tablename__ = "commentary" 

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment = Column(String, nullable=False)
    time_stamp = Column(DateTime, nullable=False)
    
    user = relationship("User", back_populates="comments", lazy="joined")
    plant = relationship("Plant", back_populates="comments")


def utcnow():
    # naive UTC: the DateTime columns have no time zone, so values read back are naive too
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OfferStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class CareOffer(Base):
    """A member offering to look after a plant; the owner accepts or refuses it."""
    __tablename__ = "care_offers"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False, index=True)
    sitter_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(16), default=OfferStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    # seconds between the care request and this offer's acceptance, for the business dashboard
    wait_seconds = Column(Integer, nullable=True)

    plant = relationship("Plant", back_populates="care_offers")
    sitter = relationship("User", back_populates="care_offers", lazy="joined")
    messages = relationship("Message", back_populates="offer", cascade="all, delete-orphan")
    review = relationship("Review", back_populates="offer", uselist=False, cascade="all, delete-orphan")


class Message(Base):
    """Private message between a plant owner and the member who offered to look after it."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("care_offers.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    offer = relationship("CareOffer", back_populates="messages")
    sender = relationship("User", back_populates="messages", lazy="joined")


class CareLog(Base):
    """Care journal entry posted by the sitter, optionally with a photo."""
    __tablename__ = "care_logs"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String(1000), nullable=False)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    plant = relationship("Plant", back_populates="care_logs")
    author = relationship("User", back_populates="care_logs", lazy="joined")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "plant_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    plant = relationship("Plant", back_populates="favorites")


class AdviceStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class AdviceRequest(Base):
    """A question an owner asks the verified botanists about one of their plants."""
    __tablename__ = "advice_requests"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question = Column(String(1000), nullable=False)
    status = Column(String(16), default=AdviceStatus.OPEN.value, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    plant = relationship("Plant", back_populates="advice_requests")
    author = relationship("User", back_populates="advice_requests", lazy="joined")


class Review(Base):
    """The owner's rating of a sitter, one per completed care."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("care_offers.id"), nullable=False, unique=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sitter_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    comment = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    offer = relationship("CareOffer", back_populates="review")


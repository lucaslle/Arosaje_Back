from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
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
    is_botanist = Column(Boolean, default=False)
    
    owned_plants = relationship("Plant",
                               back_populates="owner",
                               foreign_keys="[Plant.owner_id]",
                               cascade="all, delete-orphan")
    comments = relationship("Comment", 
                           back_populates="user",
                           cascade="all, delete-orphan")
    
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
    
    owner = relationship("User",
                        foreign_keys=[owner_id],
                        back_populates="owned_plants",
                        lazy="joined")
    comments = relationship("Comment", 
                          back_populates="plant",
                          cascade="all, delete-orphan")
    
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
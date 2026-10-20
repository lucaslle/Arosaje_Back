import pydantic
import datetime


class UserBase(pydantic.BaseModel):
    """The base model of a User"""
    email: pydantic.EmailStr
    username: str
    phone: str

class UserCreate(UserBase):
    """The model for a user creation"""
    username: str
    phone: str
    password: str
    is_botanist: bool = False

class UserDelete(UserBase):
    """The model to delete a user"""

    id: str

class User(UserBase):
    id: int
    is_active: bool
    is_botanist: bool
    botanist_verified: bool = False
    is_admin: bool = False

    class Config:
        from_attributes = True

class PasswordChange(pydantic.BaseModel):
    current_password: str
    new_password: str = pydantic.Field(min_length=8)

class UserPublic(pydantic.BaseModel):
    """What other users may see about a user: never contact details or password hash"""
    id: int
    username: str | None
    # only botanists checked by an admin are shown as botanists
    is_botanist: bool = pydantic.Field(validation_alias="is_verified_botanist")

    class Config:
        from_attributes = True

class SitterPublic(UserPublic):
    rating_average: float | None = None
    rating_count: int = 0
    completed_cares: int = 0

class PlantBase(pydantic.BaseModel):
    name: str
    location: str
    care_instructions: str | None = None

class PlantCreate(PlantBase):
    pass

class Plant(PlantBase):
    id: int
    photo_url: str | None
    owner_id: int
    owner: UserPublic
    created_at: datetime.datetime
    in_care: bool
    in_care_id: int | None
    care_requested: bool
    care_start: datetime.date | None = None
    care_end: datetime.date | None = None

    class Config:
        from_attributes = True

class Comment(pydantic.BaseModel):
    id: int
    plant_id: int
    user_id: int
    comment: str
    time_stamp: datetime.datetime
    user: UserPublic

    class Config:
        from_attributes = True


class PlantSummary(pydantic.BaseModel):
    id: int
    name: str
    location: str
    photo_url: str | None
    owner: UserPublic

    class Config:
        from_attributes = True

class CareOffer(pydantic.BaseModel):
    id: int
    plant_id: int
    status: str
    created_at: datetime.datetime
    decided_at: datetime.datetime | None
    sitter: SitterPublic
    has_review: bool = False

class MyCareOffer(pydantic.BaseModel):
    id: int
    plant_id: int
    status: str
    created_at: datetime.datetime
    plant: PlantSummary

    class Config:
        from_attributes = True

class MessageCreate(pydantic.BaseModel):
    text: str = pydantic.Field(min_length=1, max_length=1000)

class Message(pydantic.BaseModel):
    id: int
    offer_id: int
    text: str
    created_at: datetime.datetime
    sender: UserPublic

    class Config:
        from_attributes = True

class CareLog(pydantic.BaseModel):
    id: int
    plant_id: int
    text: str
    photo_url: str | None
    created_at: datetime.datetime
    author: UserPublic

    class Config:
        from_attributes = True

class AdviceRequestCreate(pydantic.BaseModel):
    question: str = pydantic.Field(min_length=3, max_length=1000)

class AdviceRequest(pydantic.BaseModel):
    id: int
    plant_id: int
    question: str
    status: str
    created_at: datetime.datetime
    plant: PlantSummary

    class Config:
        from_attributes = True

class ReviewCreate(pydantic.BaseModel):
    rating: int = pydantic.Field(ge=1, le=5)
    comment: str | None = pydantic.Field(default=None, max_length=1000)

class Review(pydantic.BaseModel):
    id: int
    offer_id: int
    rating: int
    comment: str | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class UserProfile(pydantic.BaseModel):
    id: int
    username: str | None
    is_botanist: bool
    rating_average: float | None
    rating_count: int
    completed_cares: int

class BotanistRequest(pydantic.BaseModel):
    id: int
    username: str | None
    email: str | None

class BotanistDecision(pydantic.BaseModel):
    verified: bool


class DashboardOffer(pydantic.BaseModel):
    id: int
    plant_id: int
    plant_name: str
    sitter_username: str | None
    created_at: datetime.datetime

class DashboardSitting(pydantic.BaseModel):
    plant: PlantSummary
    care_end: datetime.date | None

class DashboardAdvice(pydantic.BaseModel):
    id: int
    plant_id: int
    plant_name: str
    question: str
    status: str

class Dashboard(pydantic.BaseModel):
    plants_total: int
    plants_waiting_sitter: int
    plants_being_cared: int
    offers_to_answer: list[DashboardOffer]
    reviews_to_give: list[DashboardOffer]
    sitting: list[DashboardSitting]
    my_pending_offers: int
    advice: list[DashboardAdvice]
    reputation: SitterPublic

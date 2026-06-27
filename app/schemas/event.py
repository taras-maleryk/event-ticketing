from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class EventBase(BaseModel):
    name: str = Field(max_length=128)
    venue: str = Field(max_length=128)
    date: datetime
    description: str | None = Field(default=None, max_length=1024)


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: int
    organizer_id: int

    model_config = ConfigDict(from_attributes=True)
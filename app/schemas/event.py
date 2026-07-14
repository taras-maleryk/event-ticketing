from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    venue: str | None = Field(default=None, max_length=128)
    date: datetime | None = None
    description: str | None = Field(default=None, max_length=1024)


class EventListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=20)
    event_status: Literal["upcoming", "past"] = "upcoming"


class EventPageResponse(BaseModel):
    items: list[EventResponse]
    page: int
    page_size: int
    total: int
    pages: int
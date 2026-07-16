from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError

        return self


class EventPageResponse(BaseModel):
    items: list[EventResponse]
    page: int
    page_size: int
    total: int
    pages: int

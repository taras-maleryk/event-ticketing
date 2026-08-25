from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

EventText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class EventBase(BaseModel):
    name: EventText
    venue: EventText
    date: AwareDatetime
    description: str | None = Field(default=None, max_length=1024)


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: int
    organizer_id: int

    model_config = ConfigDict(from_attributes=True)


class EventUpdate(BaseModel):
    name: EventText | None = None
    venue: EventText | None = None
    date: AwareDatetime | None = None
    description: str | None = Field(default=None, max_length=1024)

    @field_validator("name", "venue", "date", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")

        return value


class EventListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=20)
    event_status: Literal["upcoming", "past"] = "upcoming"
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None

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

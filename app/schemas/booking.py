from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookingResponse(BaseModel):
    id: int
    seat_id: int = Field(gt=0)
    event_id: int = Field(gt=0)
    event_name: str
    venue: str
    event_date: datetime
    row: int = Field(gt=0)
    number: int = Field(gt=0)

    price_paid: int = Field(ge=0)
    booked_at: datetime
    ticket_token: str

    model_config = ConfigDict(from_attributes=True)

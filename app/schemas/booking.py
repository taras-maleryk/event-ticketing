from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class BookingBase(BaseModel):
    seat_id: int = Field(gt=0)

class BookingCreate(BookingBase):
    price_paid: int = Field(ge=0)

class BookingResponse(BookingBase):
    id: int
    price_paid: int
    booked_at: datetime
    ticket_token: str

    model_config = ConfigDict(from_attributes=True)
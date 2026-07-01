from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class BookingResponse(BaseModel):
    id: int
    seat_id: int = Field(gt=0)
    price_paid: int = Field(ge=0)
    booked_at: datetime
    ticket_token: str

    model_config = ConfigDict(from_attributes=True)
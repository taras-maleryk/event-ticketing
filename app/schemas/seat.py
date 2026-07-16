from pydantic import BaseModel, ConfigDict, Field

from app.enums.seat_status import SeatStatus


class SeatBase(BaseModel):
    row: int = Field(gt=0)
    number: int = Field(gt=0)
    price: int = Field(ge=0)


class SeatResponse(SeatBase):
    id: int
    event_id: int

    model_config = ConfigDict(from_attributes=True)


class SeatAvailabilityResponse(SeatResponse):
    status: SeatStatus

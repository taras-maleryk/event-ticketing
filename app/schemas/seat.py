from pydantic import BaseModel, ConfigDict, Field

class SeatBase(BaseModel):
    row: int = Field(gt=0)
    number: int = Field(gt=0)
    price: int = Field(ge=0)


class SeatResponse(SeatBase):
    id: int
    event_id: int

    model_config = ConfigDict(from_attributes=True)
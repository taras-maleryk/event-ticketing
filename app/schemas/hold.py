from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class HoldBase(BaseModel):
    seat_id: int = Field(gt=0)

class HoldCreate(HoldBase):
    pass

class HoldResponse(HoldBase):
    id: int
    user_id: int
    held_from: datetime
    held_until: datetime
    status: str = Field(max_length=50)
    payment_started_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
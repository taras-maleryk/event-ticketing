from pydantic import BaseModel, ConfigDict
from datetime import datetime


class HoldResponse(BaseModel):
    id: int
    seat_id: int
    user_id: int
    held_from: datetime
    held_until: datetime

    model_config = ConfigDict(from_attributes=True)
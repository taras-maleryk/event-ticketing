from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HoldResponse(BaseModel):
    id: int
    seat_id: int
    user_id: int
    held_from: datetime
    held_until: datetime

    model_config = ConfigDict(from_attributes=True)

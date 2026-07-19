from datetime import datetime

from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    payment_attempt_id: int
    checkout_url: str
    expires_at: datetime

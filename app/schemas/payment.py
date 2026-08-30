from datetime import datetime

from pydantic import BaseModel

from app.enums.payment_attempt_status import PaymentAttemptStatus


class CheckoutSessionResponse(BaseModel):
    payment_attempt_id: int
    checkout_url: str
    expires_at: datetime


class PaymentStatusResponse(BaseModel):
    payment_attempt_id: int
    status: PaymentAttemptStatus
    booking_id: int | None
    amount: int
    currency: str
    checkout_expires_at: datetime | None

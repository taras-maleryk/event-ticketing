from pydantic import BaseModel


class StripeWebhookResponse(BaseModel):
    received: bool

from stripe import Event

from app.core.config import settings
from app.core.stripe_client import stripe_client


def construct_stripe_event(
    *,
    payload: bytes,
    signature: str,
) -> Event:
    return stripe_client.construct_event(
        payload.decode("utf-8"),
        signature,
        settings.STRIPE_WEBHOOK_SECRET,
    )

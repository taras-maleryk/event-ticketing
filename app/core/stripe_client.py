import stripe
from stripe import StripeClient

from app.core.config import settings

stripe_client = StripeClient(
    settings.STRIPE_SECRET_KEY,
    http_client=stripe.HTTPXClient(),
    max_network_retries=2,
)

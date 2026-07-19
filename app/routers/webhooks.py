from typing import Annotated

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Request,
    status,
)
from stripe import SignatureVerificationError

from app.schemas.webhook import StripeWebhookResponse
from app.services.stripe_webhooks import (
    construct_stripe_event,
)


router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


@router.post(
    "/stripe",
    response_model=StripeWebhookResponse,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[
        str | None,
        Header(alias="Stripe-Signature"),
    ] = None,
) -> StripeWebhookResponse:
    if stripe_signature is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    payload = await request.body()

    try:
        event = construct_stripe_event(
            payload=payload,
            signature=stripe_signature,
        )
    except SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook payload",
        ) from exc


    return StripeWebhookResponse(received=True)

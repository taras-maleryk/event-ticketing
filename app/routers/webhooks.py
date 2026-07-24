from typing import Annotated

import structlog
from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Request,
    status,
)
from stripe import SignatureVerificationError

from app.core.deps import db_dep
from app.schemas.webhook import StripeWebhookResponse
from app.services.stripe_webhooks import (
    construct_stripe_event,
    process_stripe_event,
)

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)

logger = structlog.get_logger(__name__)


@router.post(
    "/stripe",
    response_model=StripeWebhookResponse,
)
async def stripe_webhook(
    request: Request,
    db: db_dep,
    stripe_signature: Annotated[
        str | None,
        Header(alias="Stripe-Signature"),
    ] = None,
) -> StripeWebhookResponse:
    if stripe_signature is None:
        logger.warning("stripe_webhook_missing_signature")
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
        logger.warning("stripe_webhook_invalid_signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        ) from exc
    except ValueError as exc:
        logger.warning("stripe_webhook_invalid_payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook payload",
        ) from exc

    try:
        outcome = await process_stripe_event(
            db,
            event=event,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    if outcome is not None:
        if outcome.level == "warning":
            logger.warning(
                outcome.event_name,
                **outcome.fields,
            )
        else:
            logger.info(
                outcome.event_name,
                **outcome.fields,
            )

    return StripeWebhookResponse(received=True)

import structlog
from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import Session
from stripe import Refund

from app.core.celery_app import celery_app
from app.core.stripe_client import stripe_client
from app.db.sync_session import sync_session_maker
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.payment_attempt import PaymentAttempt

logger = structlog.get_logger(__name__)

REFUND_BATCH_SIZE = 100


def create_or_retrieve_refund(payment_attempt: PaymentAttempt) -> Refund:
    if payment_attempt.stripe_refund_id is not None:
        return stripe_client.v1.refunds.retrieve(
            payment_attempt.stripe_refund_id,
        )

    if payment_attempt.stripe_payment_intent_id is None:
        raise RuntimeError("Payment attempt has no Stripe PaymentIntent")

    return stripe_client.v1.refunds.create(
        params={
            "payment_intent": payment_attempt.stripe_payment_intent_id,
            "metadata": {
                "payment_attempt_id": str(payment_attempt.id),
            },
        },
        options={
            "idempotency_key": f"payment-refund:{payment_attempt.id}",
        },
    )


def process_payment_refund(
    session: Session,
    *,
    payment_attempt_id: int,
    task_logger: structlog.stdlib.BoundLogger,
) -> None:
    payment_attempt = session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == payment_attempt_id)
        .with_for_update(skip_locked=True)
    )

    if (
        payment_attempt is None
        or payment_attempt.status != PaymentAttemptStatus.REQUIRES_REFUND
    ):
        return

    refund = create_or_retrieve_refund(payment_attempt)
    payment_attempt.stripe_refund_id = refund.id

    log_context = {
        "payment_attempt_id": payment_attempt.id,
        "stripe_payment_intent_id": payment_attempt.stripe_payment_intent_id,
        "stripe_refund_id": refund.id,
        "stripe_refund_status": refund.status,
    }

    if refund.status == "succeeded":
        payment_attempt.status = PaymentAttemptStatus.REFUNDED
        task_logger.info(
            "payment_refund_completed",
            **log_context,
        )
        return

    task_logger.warning(
        "payment_refund_pending",
        **log_context,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.refunds.process_required_refunds",
)
def process_required_refunds(self: Task) -> None:
    task_logger = logger.bind(
        task_id=self.request.id,
        task_name=self.name,
    )

    with sync_session_maker() as session:
        payment_attempt_ids = list(
            session.scalars(
                select(PaymentAttempt.id)
                .where(PaymentAttempt.status == PaymentAttemptStatus.REQUIRES_REFUND)
                .order_by(PaymentAttempt.id)
                .limit(REFUND_BATCH_SIZE)
            )
        )

    processed_count = 0

    for payment_attempt_id in payment_attempt_ids:
        try:
            with sync_session_maker.begin() as session:
                process_payment_refund(
                    session,
                    payment_attempt_id=payment_attempt_id,
                    task_logger=task_logger,
                )
            processed_count += 1
        except Exception:
            task_logger.exception(
                "payment_refund_failed",
                payment_attempt_id=payment_attempt_id,
            )

    task_logger.info(
        "required_refunds_processed",
        selected_count=len(payment_attempt_ids),
        processed_count=processed_count,
    )

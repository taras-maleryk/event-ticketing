from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from stripe import StripeError

from app.core.config import settings
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.services.payments import get_or_create_payment_attempt
from app.tasks import refunds as refunds_tasks
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


@dataclass
class FakeStripeRefund:
    id: str
    status: str


class FakeRefundService:
    def __init__(
        self,
        *,
        create_results: list[FakeStripeRefund | Exception],
        retrieve_results: list[FakeStripeRefund] | None = None,
    ) -> None:
        self.create_results = create_results
        self.retrieve_results = retrieve_results or []
        self.create_calls: list[
            tuple[dict[str, object] | None, dict[str, object] | None]
        ] = []
        self.retrieve_calls: list[str] = []

    def create(
        self,
        params: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> FakeStripeRefund:
        self.create_calls.append((params, options))
        result = self.create_results.pop(0)

        if isinstance(result, Exception):
            raise result

        return result

    def retrieve(self, refund_id: str) -> FakeStripeRefund:
        self.retrieve_calls.append(refund_id)
        return self.retrieve_results.pop(0)


@dataclass
class FakeStripeV1:
    refunds: FakeRefundService


@dataclass
class FakeStripeClient:
    v1: FakeStripeV1


async def create_required_refund_attempt(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> PaymentAttempt:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )
    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )
    hold = await db_session.get(Hold, created_hold["id"])

    assert hold is not None

    payment_attempt = await get_or_create_payment_attempt(
        db_session,
        hold_id=hold.id,
        user_id=hold.user_id,
    )
    payment_attempt.status = PaymentAttemptStatus.REQUIRES_REFUND
    payment_attempt.stripe_payment_intent_id = f"pi_refund_attempt_{payment_attempt.id}"
    await db_session.commit()

    return payment_attempt


def configure_refund_task_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Engine:
    assert settings.TEST_DATABASE_URL is not None

    sync_test_database_url = settings.TEST_DATABASE_URL.replace(
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        1,
    )
    test_sync_engine = create_engine(sync_test_database_url)
    test_sync_session_maker = sessionmaker(
        bind=test_sync_engine,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        refunds_tasks,
        "sync_session_maker",
        test_sync_session_maker,
    )

    return test_sync_engine


def configure_fake_stripe(
    monkeypatch: pytest.MonkeyPatch,
    refund_service: FakeRefundService,
) -> None:
    monkeypatch.setattr(
        refunds_tasks,
        "stripe_client",
        FakeStripeClient(
            v1=FakeStripeV1(
                refunds=refund_service,
            )
        ),
    )


async def test_required_refund_is_created_once(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_attempt = await create_required_refund_attempt(
        client,
        organizer_headers,
        regular_user_headers,
        db_session,
    )
    payment_attempt_id = payment_attempt.id
    payment_intent_id = payment_attempt.stripe_payment_intent_id

    assert payment_intent_id is not None

    refund_service = FakeRefundService(
        create_results=[
            FakeStripeRefund(
                id="re_succeeded",
                status="succeeded",
            )
        ]
    )
    configure_fake_stripe(monkeypatch, refund_service)
    test_sync_engine = configure_refund_task_database(monkeypatch)

    try:
        refunds_tasks.process_required_refunds.run()
        refunds_tasks.process_required_refunds.run()
    finally:
        test_sync_engine.dispose()

    db_session.expire_all()
    saved_payment_attempt = await db_session.get(
        PaymentAttempt,
        payment_attempt_id,
    )

    assert saved_payment_attempt is not None
    assert saved_payment_attempt.status == PaymentAttemptStatus.REFUNDED
    assert saved_payment_attempt.stripe_refund_id == "re_succeeded"
    assert refund_service.create_calls == [
        (
            {
                "payment_intent": payment_intent_id,
                "metadata": {
                    "payment_attempt_id": str(payment_attempt_id),
                },
            },
            {
                "idempotency_key": f"payment-refund:{payment_attempt_id}",
            },
        )
    ]


async def test_pending_refund_is_retrieved_until_succeeded(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_attempt = await create_required_refund_attempt(
        client,
        organizer_headers,
        regular_user_headers,
        db_session,
    )
    payment_attempt_id = payment_attempt.id
    refund_service = FakeRefundService(
        create_results=[
            FakeStripeRefund(
                id="re_pending",
                status="pending",
            )
        ],
        retrieve_results=[
            FakeStripeRefund(
                id="re_pending",
                status="succeeded",
            )
        ],
    )
    configure_fake_stripe(monkeypatch, refund_service)
    test_sync_engine = configure_refund_task_database(monkeypatch)

    try:
        refunds_tasks.process_required_refunds.run()

        db_session.expire_all()
        pending_attempt = await db_session.get(
            PaymentAttempt,
            payment_attempt_id,
        )

        assert pending_attempt is not None
        assert pending_attempt.status == PaymentAttemptStatus.REQUIRES_REFUND
        assert pending_attempt.stripe_refund_id == "re_pending"

        refunds_tasks.process_required_refunds.run()
    finally:
        test_sync_engine.dispose()

    db_session.expire_all()
    saved_payment_attempt = await db_session.get(
        PaymentAttempt,
        payment_attempt_id,
    )

    assert saved_payment_attempt is not None
    assert saved_payment_attempt.status == PaymentAttemptStatus.REFUNDED
    assert saved_payment_attempt.stripe_refund_id == "re_pending"
    assert len(refund_service.create_calls) == 1
    assert refund_service.retrieve_calls == ["re_pending"]


async def test_failed_refund_request_is_retried(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_attempt = await create_required_refund_attempt(
        client,
        organizer_headers,
        regular_user_headers,
        db_session,
    )
    payment_attempt_id = payment_attempt.id
    refund_service = FakeRefundService(
        create_results=[
            StripeError("Stripe is temporarily unavailable"),
            FakeStripeRefund(
                id="re_after_retry",
                status="succeeded",
            ),
        ]
    )
    configure_fake_stripe(monkeypatch, refund_service)
    test_sync_engine = configure_refund_task_database(monkeypatch)

    try:
        refunds_tasks.process_required_refunds.run()

        db_session.expire_all()
        pending_attempt = await db_session.get(
            PaymentAttempt,
            payment_attempt_id,
        )

        assert pending_attempt is not None
        assert pending_attempt.status == PaymentAttemptStatus.REQUIRES_REFUND
        assert pending_attempt.stripe_refund_id is None

        refunds_tasks.process_required_refunds.run()
    finally:
        test_sync_engine.dispose()

    db_session.expire_all()
    saved_payment_attempt = await db_session.get(
        PaymentAttempt,
        payment_attempt_id,
    )

    assert saved_payment_attempt is not None
    assert saved_payment_attempt.status == PaymentAttemptStatus.REFUNDED
    assert saved_payment_attempt.stripe_refund_id == "re_after_retry"
    assert len(refund_service.create_calls) == 2
    assert refund_service.create_calls[0][1] == refund_service.create_calls[1][1]

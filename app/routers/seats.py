from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.deps import CurrentUser, db_dep
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.models.seat import Seat
from app.schemas.hold import HoldResponse

router = APIRouter(prefix="/seats", tags=["seats"])


@router.post(
    "/{seat_id}/hold", status_code=status.HTTP_201_CREATED, response_model=HoldResponse
)
async def hold_seat(db: db_dep, seat_id: int, current_user: CurrentUser) -> Hold:
    seat = await db.scalar(select(Seat).where(Seat.id == seat_id))
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found"
        )

    booking_id = await db.scalar(select(Booking.id).where(Booking.seat_id == seat_id))

    if booking_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat is already booked",
        )

    hold = Hold(
        user_id=current_user.id,
        seat_id=seat_id,
        held_until=datetime.now(UTC) + timedelta(minutes=settings.HOLD_FOR_MINUTES),
    )

    db.add(hold)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat is already held",
        ) from exc

    booking_id = await db.scalar(select(Booking.id).where(Booking.seat_id == seat_id))

    if booking_id is not None:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat is already booked",
        )

    await db.commit()
    await db.refresh(hold)

    return hold


@router.delete("/{seat_id}/hold", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(db: db_dep, seat_id: int, current_user: CurrentUser) -> None:
    seat = await db.scalar(select(Seat).where(Seat.id == seat_id))
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found"
        )

    stmt = (
        select(Hold)
        .where(
            Hold.seat_id == seat_id,
            Hold.user_id == current_user.id,
        )
        .order_by(Hold.held_until.desc())
        .limit(1)
        .with_for_update()
    )
    hold = await db.scalar(stmt)

    if hold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hold not found"
        )

    active_payment_attempt_id = await db.scalar(
        select(PaymentAttempt.id)
        .where(
            PaymentAttempt.hold_id == hold.id,
            PaymentAttempt.status.in_(
                [
                    PaymentAttemptStatus.CREATING,
                    PaymentAttemptStatus.PENDING,
                ]
            ),
        )
        .limit(1)
    )

    if active_payment_attempt_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hold has an active payment",
        )

    await db.delete(hold)
    await db.commit()

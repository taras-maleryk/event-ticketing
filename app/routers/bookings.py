from app.models.booking import Booking
from fastapi import APIRouter, HTTPException, status
from app.core.deps import db_dep, CurrentUser
from app.models.seat import Seat
from app.models.hold import Hold
from app.schemas.booking import BookingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import secrets

router = APIRouter(prefix="/holds", tags=["bookings"])


@router.post(
    "/{hold_id}/book",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingResponse
)
async def confirm_booking(
        db: db_dep,
        current_user: CurrentUser,
        hold_id: int
):
    stmt = (
        select(Hold)
        .where(Hold.id == hold_id)
        .with_for_update()
    )

    hold = await db.scalar(stmt)

    if hold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hold not found",
        )

    if hold.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hold is not yours",
        )

    if hold.held_until <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hold has expired",
        )

    booking_id = await db.scalar(
        select(Booking.id).where(Booking.seat_id == hold.seat_id)
    )

    if booking_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat is already booked",
        )

    #payment implementation

    price_paid = await db.scalar(select(Seat.price).where(Seat.id == hold.seat_id))

    if price_paid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    ticket_token = secrets.token_urlsafe(32)

    booking = Booking(
        seat_id=hold.seat_id,
        user_id=hold.user_id,
        price_paid=price_paid,
        ticket_token=ticket_token
    )

    db.add(booking)
    await db.delete(hold)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Seat is already booked") from exc

    await db.refresh(booking)

    return booking
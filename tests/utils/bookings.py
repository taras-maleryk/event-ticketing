import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.hold import Hold
from app.models.seat import Seat


async def create_booking_for_hold(
    db: AsyncSession,
    hold_id: int,
) -> Booking:
    hold = await db.get(Hold, hold_id)

    assert hold is not None

    seat = await db.get(Seat, hold.seat_id)

    assert seat is not None

    booking = Booking(
        seat_id=hold.seat_id,
        user_id=hold.user_id,
        price_paid=seat.price,
        ticket_token=secrets.token_urlsafe(32),
    )

    db.add(booking)
    await db.delete(hold)

    await db.commit()
    await db.refresh(booking)

    return booking

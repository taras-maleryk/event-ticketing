from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, db_dep
from app.models import Booking, Event, Seat
from app.schemas.booking import BookingResponse

router = APIRouter(tags=["bookings"])


@router.get(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
)
async def get_booking(
    db: db_dep,
    current_user: CurrentUser,
    booking_id: int,
) -> BookingResponse:
    result = await db.execute(
        select(Booking, Seat, Event)
        .join(Seat, Seat.id == Booking.seat_id)
        .join(Event, Event.id == Seat.event_id)
        .where(
            Booking.id == booking_id,
            Booking.user_id == current_user.id,
        )
    )
    booking_row = result.one_or_none()

    if booking_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    booking, seat, event = booking_row

    return BookingResponse(
        id=booking.id,
        seat_id=seat.id,
        event_id=event.id,
        event_name=event.name,
        venue=event.venue,
        event_date=event.date,
        row=seat.row,
        number=seat.number,
        price_paid=booking.price_paid,
        booked_at=booking.booked_at,
        ticket_token=booking.ticket_token,
    )

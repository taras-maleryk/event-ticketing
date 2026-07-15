from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, db_dep, require_role
from app.enums.seat_status import SeatStatus
from app.models import Booking, Hold
from app.models.event import Event
from app.models.seat import Seat
from app.models.user import User
from app.schemas.event import (
    EventCreate,
    EventListQuery,
    EventPageResponse,
    EventResponse,
    EventUpdate,
)
from app.schemas.hall import HallConfigurationCreate
from app.schemas.seat import SeatAvailabilityResponse, SeatResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPageResponse)
async def get_events(
    db: db_dep,
    query: Annotated[EventListQuery, Query()],
) -> EventPageResponse:
    now = datetime.now(timezone.utc)

    conditions = []

    if query.event_status == "upcoming":
        conditions.append(Event.date > now)
        ordering = (Event.date.asc(), Event.id.asc())
    else:
        conditions.append(Event.date < now)
        ordering = (Event.date.desc(), Event.id.desc())

    if query.date_from is not None:
        conditions.append(Event.date >= query.date_from)

    if query.date_to is not None:
        conditions.append(Event.date <= query.date_to)

    total = await db.scalar(
        select(func.count(Event.id)).where(*conditions)
    )
    total = total or 0

    offset = (query.page - 1) * query.page_size

    stmt = (
        select(Event)
        .where(*conditions)
        .order_by(*ordering)
        .limit(query.page_size)
        .offset(offset)
    )

    events = list((await db.scalars(stmt)).all())
    pages = (total + query.page_size - 1) // query.page_size

    return EventPageResponse(
        items=events,
        page=query.page,
        page_size=query.page_size,
        total=total,
        pages=pages,
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(db: db_dep, event_id: int) -> Event:
    stmt = select(Event).where(Event.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return event


@router.get("/{event_id}/seats", response_model=list[SeatAvailabilityResponse])
async def get_event_seats(db: db_dep, event_id: int, current_user: CurrentUser) -> list[SeatAvailabilityResponse]:
    event_exists = await db.scalar(
        select(exists().where(Event.id == event_id))
    )

    if not event_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    stmt = (
        select(
            Seat,
            Hold.user_id.label("hold_user_id"),
            Booking.user_id.label("booking_user_id"),
        )
        .outerjoin(
            Hold,
            and_(
                Hold.seat_id == Seat.id,
                Hold.held_until > func.now(),
            ),
        )
        .outerjoin(
            Booking,
            Booking.seat_id == Seat.id,
        )
        .where(Seat.event_id == event_id)
        .order_by(Seat.row.asc(), Seat.number.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    response: list[SeatAvailabilityResponse] = []

    for seat, hold_user_id, booking_user_id in rows:
        if booking_user_id is not None:
            if booking_user_id == current_user.id:
                seat_status = SeatStatus.BOOKED_BY_ME
            else:
                seat_status = SeatStatus.BOOKED

        elif hold_user_id is not None:
            if hold_user_id == current_user.id:
                seat_status = SeatStatus.HELD_BY_ME
            else:
                seat_status = SeatStatus.HELD

        else:
            seat_status = SeatStatus.AVAILABLE

        response.append(
            SeatAvailabilityResponse(
                id=seat.id,
                event_id=seat.event_id,
                row=seat.row,
                number=seat.number,
                price=seat.price,
                status=seat_status,
            )
        )

    return response


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
        db: db_dep,
        new_event: EventCreate,
        current_user: Annotated[User, Depends(require_role("organizer"))]) -> Event:
    event = Event(**new_event.model_dump(),
                  organizer_id=current_user.id)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    db: db_dep,
    event_data: EventUpdate,
    current_user: Annotated[
        User,
        Depends(require_role("organizer")),
    ],
) -> Event:
    stmt = select(Event).where(Event.id == event_id)
    event = await db.scalar(stmt)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    if event.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot update this event",
        )

    updates = event_data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(event, field, value)

    await db.commit()
    await db.refresh(event)

    return event


@router.post(
    "/{event_id}/seats",
    response_model=list[SeatResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_event_seats(
    event_id: int,
    hall_config: HallConfigurationCreate,
    db: db_dep,
    current_user: Annotated[
        User,
        Depends(require_role("organizer")),
    ],
) -> list[Seat]:
    event = await db.scalar(
        select(Event).where(Event.id == event_id)
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    if event.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot manage seats for this event",
        )

    seats_exist = await db.scalar(
        select(exists().where(Seat.event_id == event_id))
    )

    if seats_exist:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seats have already been created for this event",
        )

    prices_by_row = {
        item.row: item.price
        for item in hall_config.row_prices
    }

    excluded_by_row = {
        item.row: set(item.excluded_numbers)
        for item in hall_config.excluded_seats
    }

    seats = []

    for row in range(1, hall_config.total_rows + 1):
        excluded_numbers = excluded_by_row.get(row, set())

        for number in range(1, hall_config.seats_per_row + 1):
            if number in excluded_numbers:
                continue

            seats.append(
                Seat(
                    event_id=event_id,
                    row=row,
                    number=number,
                    price=prices_by_row[row],
                )
            )

    db.add_all(seats)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat layout conflicts with existing seats",
        ) from exc

    result = await db.execute(
        select(Seat)
        .where(Seat.event_id == event_id)
        .order_by(Seat.row.asc(), Seat.number.asc())
    )

    return list(result.scalars().all())
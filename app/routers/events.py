from app.core.deps import require_role, db_dep
from fastapi import APIRouter, Query, status, HTTPException, Depends
from sqlalchemy import select, exists
from app.models.event import Event
from app.models.seat import Seat
from app.models.user import User
from datetime import datetime, timezone
from app.schemas.event import EventResponse, EventCreate, EventUpdate
from app.schemas.seat import SeatResponse
from app.schemas.hall import HallConfigurationCreate
from typing import Annotated, Literal
from sqlalchemy.exc import IntegrityError


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def get_events(
    db: db_dep,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_status: Literal["upcoming", "past"] = "upcoming",
):
    now = datetime.now(timezone.utc)

    order_by = Event.date.asc() if event_status == "upcoming" else Event.date.desc()
    condition = Event.date > now if event_status == "upcoming" else Event.date < now

    stmt = (
        select(Event)
        .where(condition)
        .order_by(order_by)
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(db: db_dep, event_id: int):
    stmt = select(Event).where(Event.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return event


@router.get("/{event_id}/seats", response_model=list[SeatResponse])
async def get_event_seats(db: db_dep, event_id: int):
    event_exists = await db.scalar(
        select(exists().where(Event.id == event_id))
    )

    if not event_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    stmt = (
        select(Seat)
        .where(Seat.event_id == event_id)
        .order_by(Seat.row.asc(), Seat.number.asc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
        db: db_dep,
        new_event: EventCreate,
        current_user: Annotated[User, Depends(require_role("organizer"))]):
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
):
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
):
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

    return result.scalars().all()
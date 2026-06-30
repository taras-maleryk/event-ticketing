from app.core.deps import CurrentUser, require_role, db_dep
from fastapi import APIRouter, Query, status, HTTPException
from sqlalchemy import select, exists
from app.models.event import Event
from app.models.seat import Seat
from datetime import datetime, timezone
from app.schemas.event import EventResponse
from app.schemas.seat import SeatResponse
from typing import Annotated, Literal


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def get_events(
        db: db_dep,
        limit: Annotated[int, Query(default=10, ge=1, le=20)],
        offset: Annotated[int, Query(default=0, ge=0)],
        event_status: Literal["upcoming", "past"]
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






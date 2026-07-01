from fastapi import APIRouter, HTTPException, status
from app.core.deps import db_dep, CurrentUser
from app.models.seat import Seat
from app.models.hold import Hold
from app.schemas.hold import HoldResponse
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from sqlalchemy.exc import IntegrityError


router = APIRouter(prefix="/seats", tags=["seats"])


@router.post(
    "/{seat_id}/hold",
    status_code=status.HTTP_201_CREATED,
    response_model=HoldResponse
)
async def hold_seat(
        db: db_dep,
        seat_id: int,
        current_user: CurrentUser
):
    seat = await db.scalar(select(Seat).where(Seat.id == seat_id))
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found"
        )

    hold = Hold(
        user_id=current_user.id,
        seat_id=seat_id,
        held_until=datetime.now(timezone.utc) + timedelta(minutes=settings.HOLD_FOR_MINUTES)
    )

    db.add(hold)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Seat is already held") from exc

    await db.refresh(hold)

    return hold


@router.delete("/{seat_id}/hold", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(
        db: db_dep,
        seat_id: int,
        current_user: CurrentUser
):
    seat = await db.scalar(select(Seat).where(Seat.id == seat_id))
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found"
        )

    stmt = (
        select(Hold)
        .where(
            Hold.seat_id == seat_id,
            Hold.user_id == current_user.id,
        )
        .order_by(Hold.held_until.desc())
        .limit(1)
    )
    hold = await db.scalar(stmt)

    if hold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hold not found"
        )

    await db.delete(hold)
    await db.commit()

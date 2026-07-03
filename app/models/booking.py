from app.db.async_session import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, DateTime, func
from datetime import datetime

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    price_paid: Mapped[int] = mapped_column(nullable=False)

    ticket_token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
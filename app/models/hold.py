from app.db.async_session import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, DateTime, func
from datetime import datetime
from sqlalchemy.dialects.postgresql import ExcludeConstraint

class Hold(Base):
    __tablename__ = "holds"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), nullable=False)

    held_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    held_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ExcludeConstraint(
            ("seat_id", "="),
            (
                func.tstzrange(
                    held_from,
                    held_until,
                    "[)",
                ),
                "&&",
            ),
            using="gist",
            name="excl_holds_seat_time_overlap",
        ),
    )

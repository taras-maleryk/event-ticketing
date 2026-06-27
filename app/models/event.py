from app.db.session import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, DateTime
from datetime import datetime


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    venue: Mapped[str] = mapped_column(String(128), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
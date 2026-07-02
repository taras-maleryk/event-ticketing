from enum import StrEnum


class SeatStatus(StrEnum):
    AVAILABLE = "available"
    HELD = "held"
    HELD_BY_ME = "held_by_me"
    BOOKED = "booked"
    BOOKED_BY_ME = "booked_by_me"
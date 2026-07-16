def make_hall_config_payload(
    *,
    total_rows: int = 2,
    seats_per_row: int = 3,
    row_prices: list[dict] | None = None,
    excluded_seats: list[dict] | None = None,
) -> dict:
    return {
        "total_rows": total_rows,
        "seats_per_row": seats_per_row,
        "row_prices": row_prices
        or [
            {
                "row": 1,
                "price": 1000,
            },
            {
                "row": 2,
                "price": 1500,
            },
        ],
        "excluded_seats": excluded_seats or [],
    }

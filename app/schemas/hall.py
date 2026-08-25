from pydantic import BaseModel, Field, PositiveInt, model_validator


class RowExclusion(BaseModel):
    row: int = Field(gt=0, description="Номер ряду")
    excluded_numbers: list[PositiveInt] = Field(
        default_factory=list, description="Список відсутніх місць у цьому ряду"
    )


class RowPriceConfig(BaseModel):
    row: int = Field(gt=0)
    price: int = Field(ge=0)


class HallConfigurationCreate(BaseModel):
    total_rows: int = Field(gt=0, description="Кількість рядів у залі")
    seats_per_row: int = Field(gt=0, description="Кількість місць у ряду")

    row_prices: list[RowPriceConfig] = Field(
        min_length=1, description="Конфігурація цін для рядів"
    )

    excluded_seats: list[RowExclusion] = Field(
        default_factory=list,
        description="Місця, які потрібно пропустити при генерації",
    )

    @model_validator(mode="after")
    def validate_hall_bounds(self) -> "HallConfigurationCreate":
        price_rows: set[int] = set()

        for item in self.row_prices:
            if item.row > self.total_rows:
                raise ValueError(
                    f"Price row {item.row} exceeds the total number of rows "
                    f"({self.total_rows})."
                )

            if item.row in price_rows:
                raise ValueError(f"Price for row {item.row} is defined more than once.")

            price_rows.add(item.row)

        missing_rows = [
            row for row in range(1, self.total_rows + 1) if row not in price_rows
        ]

        if missing_rows:
            raise ValueError(
                f"Prices are missing for the following rows: {missing_rows}."
            )

        exclusion_rows: set[int] = set()
        excluded_seat_count = 0

        for exclusion in self.excluded_seats:
            if exclusion.row > self.total_rows:
                raise ValueError(
                    f"Excluded row {exclusion.row} exceeds the total number of rows "
                    f"({self.total_rows})."
                )

            if exclusion.row in exclusion_rows:
                raise ValueError(
                    f"Exclusions for row {exclusion.row} are defined more than once."
                )

            exclusion_rows.add(exclusion.row)
            excluded_numbers = set(exclusion.excluded_numbers)

            if len(excluded_numbers) != len(exclusion.excluded_numbers):
                raise ValueError(
                    f"Excluded seats for row {exclusion.row} contain duplicates."
                )

            for seat_number in excluded_numbers:
                if seat_number > self.seats_per_row:
                    raise ValueError(
                        f"Excluded seat {seat_number} in row {exclusion.row} "
                        f"exceeds the row capacity ({self.seats_per_row})."
                    )

            excluded_seat_count += len(excluded_numbers)

        if excluded_seat_count == self.total_rows * self.seats_per_row:
            raise ValueError("Hall configuration must contain at least one seat.")

        return self

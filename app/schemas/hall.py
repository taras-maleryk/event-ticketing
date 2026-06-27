from pydantic import BaseModel, Field, model_validator
from typing import List


class RowExclusion(BaseModel):
    row: int = Field(gt=0, description="Номер ряду")
    excluded_numbers: List[int] = Field(
        default=[],
        description="Список відсутніх місць у цьому ряду"
    )


class RowPriceConfig(BaseModel):
    row: int = Field(gt=0)
    price: int = Field(ge=0)


class HallConfigurationCreate(BaseModel):
    total_rows: int = Field(gt=0, description="Кількість рядів у залі")
    seats_per_row: int = Field(gt=0, description="Кількість місць у ряду")

    row_prices: List[RowPriceConfig] = Field(
        min_length=1,
        description="Конфігурація цін для рядів"
    )

    excluded_seats: List[RowExclusion] = Field(
        default=[],
        description="Місця, які потрібно пропустити при генерації"
    )

    @model_validator(mode="after")
    def validate_hall_bounds(self) -> "HallConfigurationCreate":
        for exclusion in self.excluded_seats:
            if exclusion.row > self.total_rows:
                raise ValueError(f"Excluded row {exclusion.row} exceeds the total number of rows ({self.total_rows}).")

            for seat_number in exclusion.excluded_numbers:
                if seat_number > self.seats_per_row:
                    raise ValueError(
                        f"Excluded seat {seat_number} in row {exclusion.row} exceeds the row capacity ({self.seats_per_row}).")

        defined_rows = []
        for item in self.row_prices:
            defined_rows.append(item.row)

        missing_rows = []

        for current_row in range(1, self.total_rows + 1):
            if current_row not in defined_rows:
                missing_rows.append(current_row)

        if len(missing_rows) > 0:
            raise ValueError(f"Prices are missing for the following rows: {missing_rows}.")

        return self
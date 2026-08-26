import re
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
    field_validator,
    model_validator,
)

UserName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class UserBase(BaseModel):
    name: UserName
    email: EmailStr


class UserCreate(UserBase):
    password: Password
    confirm_password: Password

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must have at least 1 digit")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must have at least 1 lowercase letter")
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must have at least 1 uppercase letter")

        return value

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")

        return self


class UserResponse(UserBase):
    id: int
    created_at: datetime
    role: str

    model_config = ConfigDict(from_attributes=True)

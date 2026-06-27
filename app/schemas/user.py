from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict
import re
from datetime import datetime


class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if len(value) < 8:
            raise ValueError("Password must have at least 8 characters")
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must have at least 1 digit")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must have at least 1 lowercase letter")
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must have at least 1 uppercase letter")

        return value

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Password dont match")

        return self


class UserResponse(UserBase):
    id: int
    created_at: datetime
    role: str

    model_config = ConfigDict(from_attributes=True)
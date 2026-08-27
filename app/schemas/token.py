from pydantic import BaseModel


class AuthResponse(BaseModel):
    detail: str


class TokenData(BaseModel):
    id: int | None = None

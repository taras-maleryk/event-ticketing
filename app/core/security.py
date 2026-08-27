from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


async def get_password_hash(password: str) -> str:
    return await run_in_threadpool(pwd_context.hash, password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(
        pwd_context.verify,
        plain_password,
        hashed_password,
    )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_refresh_token_expiration() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def create_refresh_token(data: dict, expires_at: datetime | None = None) -> str:
    to_encode = data.copy()
    expire = expires_at or get_refresh_token_expiration()
    to_encode.update({"exp": expire, "type": "refresh"})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.PyJWTError:
        return None

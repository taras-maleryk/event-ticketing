from typing import Annotated, Callable, Awaitable
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import ValidationError
from app.core.security import decode_token
from app.schemas.token import TokenData
from app.models.user import User
from app.db.async_session import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

db_dep = Annotated[AsyncSession, Depends(get_db)]

async def get_current_user(
        request: Request,
        token: Annotated[str | None, Depends(oauth2_scheme)],
        db: db_dep
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    resolved_token = token or request.cookies.get("access_token")
    if not resolved_token:
        raise credentials_exception

    payload: dict | None = decode_token(resolved_token)

    if payload is None:
        raise credentials_exception

    token_type: str | None = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token type"
        )

    try:
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception

        token_data = TokenData(id=int(user_id_str))
    except (ValueError, ValidationError):
        raise credentials_exception

    stmt = select(User).filter(User.id == token_data.id)
    result = await db.execute(stmt)

    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(allowed_role: str) -> Callable[[CurrentUser], Awaitable[User]]:
    async def check_role(current_user: CurrentUser) -> User:
        if current_user.role != allowed_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user

    return check_role
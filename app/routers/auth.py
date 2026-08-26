from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import db_dep
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    get_refresh_token_expiration,
    verify_password,
)
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_in: UserCreate, db: db_dep) -> User:
    stmt = select(User).filter(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    hashed_pwd = get_password_hash(user_in.password)

    user_data = user_in.model_dump(exclude={"password", "confirm_password"})
    user_data["hashed_password"] = hashed_pwd
    user_data["role"] = "user"

    new_user = User(**user_data)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
async def login(
    response: Response,
    db: db_dep,
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
) -> dict[str, str]:
    stmt = select(User).filter(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_expires_at = get_refresh_token_expiration()
    refresh_session = RefreshSession(
        user_id=user.id,
        current_jti=str(uuid4()),
        expires_at=refresh_expires_at,
    )
    db.add(refresh_session)
    await db.flush()

    refresh_token = create_refresh_token(
        data={
            "sub": str(user.id),
            "sid": str(refresh_session.id),
            "jti": refresh_session.current_jti,
        },
        expires_at=refresh_expires_at,
    )
    await db.commit()

    is_secure = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_secure,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=is_secure,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    response: Response,
    db: db_dep,
    refresh_token: str | None = Cookie(default=None),
) -> dict[str, str]:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing"
        )

    payload = decode_token(refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    token_jti = payload.get("jti")
    if not user_id or not session_id or not token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims"
        )

    try:
        user_id_int = int(user_id)
        session_id_int = int(session_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims"
        ) from None

    stmt = (
        select(RefreshSession)
        .where(RefreshSession.id == session_id_int)
        .with_for_update()
    )
    result = await db.execute(stmt)
    refresh_session = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if (
        refresh_session is None
        or refresh_session.user_id != user_id_int
        or refresh_session.revoked_at is not None
        or refresh_session.expires_at <= now
        or refresh_session.current_jti != token_jti
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh session",
        )

    new_jti = str(uuid4())
    refresh_session.current_jti = new_jti
    new_access_token = create_access_token(data={"sub": user_id})
    new_refresh_token = create_refresh_token(
        data={"sub": user_id, "sid": session_id, "jti": new_jti},
        expires_at=refresh_session.expires_at,
    )
    await db.commit()

    is_secure = settings.ENVIRONMENT == "production"
    refresh_max_age = max(0, int((refresh_session.expires_at - now).total_seconds()))

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_secure,
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=refresh_max_age,
        samesite="lax",
        secure=is_secure,
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    response: Response,
    db: db_dep,
    refresh_token: str | None = Cookie(default=None),
) -> dict[str, str]:
    if refresh_token:
        payload = decode_token(refresh_token)
        if (
            payload
            and payload.get("type") == "refresh"
            and payload.get("sub")
            and payload.get("sid")
            and payload.get("jti")
        ):
            try:
                user_id = int(payload["sub"])
                session_id = int(payload["sid"])
            except (TypeError, ValueError):
                pass
            else:
                stmt = (
                    select(RefreshSession)
                    .where(
                        RefreshSession.id == session_id,
                        RefreshSession.user_id == user_id,
                        RefreshSession.current_jti == payload["jti"],
                        RefreshSession.revoked_at.is_(None),
                    )
                    .with_for_update()
                )
                result = await db.execute(stmt)
                refresh_session = result.scalar_one_or_none()
                if refresh_session is not None:
                    refresh_session.revoked_at = datetime.now(UTC)
                    await db.commit()

    is_secure = settings.ENVIRONMENT == "production"

    response.delete_cookie(key="access_token", samesite="lax", secure=is_secure)
    response.delete_cookie(key="refresh_token", samesite="lax", secure=is_secure)

    return {"detail": "Successfully logged out"}

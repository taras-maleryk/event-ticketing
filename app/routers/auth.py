from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.core.deps import db_dep
from app.core.config import settings
from app.schemas.user import UserCreate, UserResponse
from app.schemas.token import Token
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: db_dep):
    stmt = select(User).filter(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
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
        form_data: OAuth2PasswordRequestForm = Depends(),
):
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
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

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
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
        response: Response,
        refresh_token: str | None = Cookie(default=None)
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )

    payload = decode_token(refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims"
        )

    new_access_token = create_access_token(data={"sub": user_id})

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(response: Response):
    is_secure = settings.ENVIRONMENT == "production"

    response.delete_cookie(key="access_token", samesite="lax", secure=is_secure)
    response.delete_cookie(key="refresh_token", samesite="lax", secure=is_secure)

    return {"detail": "Successfully logged out"}
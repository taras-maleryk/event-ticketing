from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.user import User


async def create_auth_headers_for_user(
    db_session: AsyncSession,
    *,
    name: str,
    email: str,
    role: str,
) -> dict[str, str]:
    user = User(
        name=name,
        email=email,
        hashed_password=await get_password_hash("StrongPass123"),
        role=role,
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})

    return {
        "Authorization": f"Bearer {access_token}",
    }

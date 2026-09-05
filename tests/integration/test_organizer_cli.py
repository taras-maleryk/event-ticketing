from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

import app.cli as cli_module
from app.core.security import verify_password
from app.models.user import User
from app.schemas.user import UserCreate

runner = CliRunner()


@dataclass
class FakeOrganizer:
    id: int
    email: str


def get_test_session_factory(
    db_session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    assert db_session.bind is not None

    return async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )


async def test_create_organizer_user_persists_organizer(
    db_session: AsyncSession,
) -> None:
    user_in = UserCreate(
        name="CLI Organizer",
        email="cli-organizer@example.com",
        password="StrongPass123",
        confirm_password="StrongPass123",
    )

    organizer = await cli_module.create_organizer_user(
        user_in,
        session_factory=get_test_session_factory(db_session),
    )

    saved_organizer = await db_session.scalar(
        select(User).where(User.email == "cli-organizer@example.com")
    )

    assert saved_organizer is not None
    assert saved_organizer.id == organizer.id
    assert saved_organizer.name == "CLI Organizer"
    assert saved_organizer.role == "organizer"
    assert await verify_password(
        "StrongPass123",
        saved_organizer.hashed_password,
    )


async def test_create_organizer_user_rejects_duplicate_email(
    db_session: AsyncSession,
) -> None:
    user_in = UserCreate(
        name="CLI Organizer",
        email="duplicate-organizer@example.com",
        password="StrongPass123",
        confirm_password="StrongPass123",
    )
    session_factory = get_test_session_factory(db_session)

    await cli_module.create_organizer_user(
        user_in,
        session_factory=session_factory,
    )

    with pytest.raises(cli_module.OrganizerAlreadyExistsError):
        await cli_module.create_organizer_user(
            user_in,
            session_factory=session_factory,
        )

    organizer_count = len(
        (
            await db_session.scalars(
                select(User).where(User.email == "duplicate-organizer@example.com")
            )
        ).all()
    )

    assert organizer_count == 1


def test_create_organizer_command_prompts_for_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_users: list[UserCreate] = []

    async def fake_create_organizer_user(
        user_in: UserCreate,
    ) -> FakeOrganizer:
        captured_users.append(user_in)
        return FakeOrganizer(
            id=42,
            email=str(user_in.email),
        )

    monkeypatch.setattr(
        cli_module,
        "create_organizer_user",
        fake_create_organizer_user,
    )

    result = runner.invoke(
        cli_module.cli,
        [
            "create-organizer",
            "--name",
            "CLI Organizer",
            "--email",
            "cli-organizer@example.com",
        ],
        input="StrongPass123\nStrongPass123\n",
    )

    assert result.exit_code == 0
    assert "Created organizer cli-organizer@example.com (id=42)." in result.output
    assert len(captured_users) == 1
    assert captured_users[0].password == "StrongPass123"
    assert "StrongPass123" not in result.output


def test_create_organizer_command_rejects_invalid_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(
        _user_in: UserCreate,
    ) -> FakeOrganizer:
        raise AssertionError("Invalid organizer must not be persisted")

    monkeypatch.setattr(
        cli_module,
        "create_organizer_user",
        fail_if_called,
    )

    result = runner.invoke(
        cli_module.cli,
        [
            "create-organizer",
            "--name",
            "CLI Organizer",
            "--email",
            "cli-organizer@example.com",
        ],
        input="weakpassword\nweakpassword\n",
    )

    assert result.exit_code == 2
    assert "Invalid organizer data" in result.output
    assert "Password must have at least 1 digit" in result.output
    assert "weakpassword" not in result.output


def test_create_organizer_command_reports_duplicate_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_duplicate(
        _user_in: UserCreate,
    ) -> FakeOrganizer:
        raise cli_module.OrganizerAlreadyExistsError

    monkeypatch.setattr(
        cli_module,
        "create_organizer_user",
        raise_duplicate,
    )

    result = runner.invoke(
        cli_module.cli,
        [
            "create-organizer",
            "--name",
            "CLI Organizer",
            "--email",
            "duplicate-organizer@example.com",
        ],
        input="StrongPass123\nStrongPass123\n",
    )

    assert result.exit_code == 1
    assert "A user with this email already exists." in result.output

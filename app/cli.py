import asyncio
from typing import Annotated

import typer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import get_password_hash
from app.db.async_session import async_session_maker
from app.models.user import User
from app.schemas.user import UserCreate

cli = typer.Typer(
    no_args_is_help=True,
    help="Administrative commands for Event Ticketing API.",
)


class OrganizerAlreadyExistsError(Exception):
    pass


async def create_organizer_user(
    user_in: UserCreate,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> User:
    factory = session_factory or async_session_maker

    async with factory() as db:
        existing_user = await db.scalar(select(User).where(User.email == user_in.email))

        if existing_user is not None:
            raise OrganizerAlreadyExistsError

        organizer = User(
            name=user_in.name,
            email=str(user_in.email),
            hashed_password=await get_password_hash(user_in.password),
            role="organizer",
        )
        db.add(organizer)

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise OrganizerAlreadyExistsError from exc

        await db.refresh(organizer)

        return organizer


@cli.callback()
def main() -> None:
    """Manage the Event Ticketing application."""


@cli.command("create-organizer")
def create_organizer(
    name: Annotated[
        str,
        typer.Option(
            "--name",
            prompt=True,
            help="Organizer display name.",
        ),
    ],
    email: Annotated[
        str,
        typer.Option(
            "--email",
            prompt=True,
            help="Organizer email address.",
        ),
    ],
) -> None:
    """Create an organizer account without exposing public role assignment."""
    password = typer.prompt(
        "Password",
        hide_input=True,
        confirmation_prompt=True,
    )

    try:
        user_in = UserCreate(
            name=name,
            email=email,
            password=password,
            confirm_password=password,
        )
    except ValidationError as exc:
        messages = "; ".join(
            str(error["msg"]).removeprefix("Value error, ") for error in exc.errors()
        )
        typer.echo(
            f"Invalid organizer data: {messages}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    try:
        organizer = asyncio.run(create_organizer_user(user_in))
    except OrganizerAlreadyExistsError as exc:
        typer.echo(
            "A user with this email already exists.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created organizer {organizer.email} (id={organizer.id}).")


if __name__ == "__main__":
    cli()

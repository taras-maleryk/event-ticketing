from datetime import timedelta
from threading import get_ident

import pytest

from app.core import security
from app.core.security import create_access_token, decode_token


async def test_password_operations_run_outside_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread_id = get_ident()
    worker_thread_ids: list[int] = []

    def fake_hash(password: str) -> str:
        worker_thread_ids.append(get_ident())
        return f"hashed:{password}"

    def fake_verify(plain_password: str, hashed_password: str) -> bool:
        worker_thread_ids.append(get_ident())
        return hashed_password == f"hashed:{plain_password}"

    monkeypatch.setattr(security.pwd_context, "hash", fake_hash)
    monkeypatch.setattr(security.pwd_context, "verify", fake_verify)

    hashed_password = await security.get_password_hash("StrongPass123")
    is_valid = await security.verify_password("StrongPass123", hashed_password)

    assert is_valid is True
    assert len(worker_thread_ids) == 2
    assert all(
        worker_thread_id != event_loop_thread_id
        for worker_thread_id in worker_thread_ids
    )


def test_create_access_token_with_custom_expires_delta() -> None:
    token = create_access_token(
        data={"sub": "123"},
        expires_delta=timedelta(minutes=5),
    )

    payload = decode_token(token)

    assert payload is not None
    assert payload["sub"] == "123"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_decode_token_returns_none_for_invalid_token() -> None:
    payload = decode_token("not-a-valid-token")

    assert payload is None

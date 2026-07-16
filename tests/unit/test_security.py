from datetime import timedelta

from app.core.security import create_access_token, decode_token


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

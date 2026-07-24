from uuid import UUID

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_logging import (
    RequestLoggingMiddleware,
)


def test_request_logging_middleware_adds_ids() -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    correlation_id = response.headers["X-Correlation-ID"]

    assert response.status_code == 200
    assert UUID(request_id)
    assert UUID(correlation_id)
    assert request_id == correlation_id
    assert structlog.contextvars.get_contextvars() == {}

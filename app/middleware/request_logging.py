from time import perf_counter
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        correlation_id = request_id
        started_at = perf_counter()
        status_code = 500

        method = scope["method"]
        path = scope["path"]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "http_request_started",
            method=method,
            path=path,
        )

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
                headers.append(
                    "X-Correlation-ID",
                    correlation_id,
                )

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )
        except Exception:
            duration_ms = round(
                (perf_counter() - started_at) * 1000,
                2,
            )

            logger.exception(
                "http_request_failed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            raise
        else:
            duration_ms = round(
                (perf_counter() - started_at) * 1000,
                2,
            )

            route = scope.get("route")
            route_path = getattr(route, "path", path)

            logger.info(
                "http_request_completed",
                method=method,
                route=route_path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
        finally:
            structlog.contextvars.clear_contextvars()

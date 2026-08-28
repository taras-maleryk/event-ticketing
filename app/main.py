from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.request_logging import (
    RequestLoggingMiddleware,
)
from app.routers.auth import router as auth_router
from app.routers.events import router as events_router
from app.routers.payments import router as payments_router
from app.routers.seats import router as seats_router
from app.routers.webhooks import router as webhooks_router

configure_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
)
app = FastAPI()

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World!"}


api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(webhooks_router)
api_router.include_router(events_router)
api_router.include_router(payments_router)
api_router.include_router(seats_router)
app.include_router(api_router)

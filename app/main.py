from fastapi import APIRouter, FastAPI

from app.routers.auth import router as auth_router
from app.routers.bookings import router as booking_router
from app.routers.events import router as events_router
from app.routers.seats import router as seats_router

app = FastAPI()


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World!"}


api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(booking_router)
api_router.include_router(events_router)
api_router.include_router(seats_router)
app.include_router(api_router)

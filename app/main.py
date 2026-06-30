from fastapi import FastAPI, APIRouter
from app.routers.auth import router as auth_router
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World!"}

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
app.include_router(api_router)
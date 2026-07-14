from fastapi import FastAPI

from BACKEND.config.settings import settings
from BACKEND.routes.driver_offer import router as driver_offer_router
from BACKEND.routes.ride import router as ride_router
from BACKEND.routes.ride_status import router as ride_status_router
from BACKEND.routes.wallet import router as wallet_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
)


app.include_router(
    ride_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    driver_offer_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    ride_status_router,
    prefix=settings.API_PREFIX,
)

app.include_router(
    wallet_router,
    prefix=settings.API_PREFIX,
)


@app.get("/")
def home():
    return {
        "message": f"Welcome to {settings.APP_NAME}!",
        "status": "Backend is running successfully.",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }

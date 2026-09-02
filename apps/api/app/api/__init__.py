from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.players import router as players_router
from app.api.rankings import router as rankings_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(metrics_router)
api_router.include_router(players_router)
api_router.include_router(rankings_router)

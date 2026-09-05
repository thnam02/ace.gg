from fastapi import APIRouter

from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.ops import router as ops_router
from app.api.players import router as players_router
from app.api.rankings import router as rankings_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(metrics_router)
api_router.include_router(players_router)
api_router.include_router(rankings_router)
api_router.include_router(events_router)
api_router.include_router(ops_router)

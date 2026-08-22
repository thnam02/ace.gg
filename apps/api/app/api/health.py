from fastapi import APIRouter

from app.db import check_database_connection
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    database_connected = check_database_connection()
    return HealthResponse(
        status="ok" if database_connected else "degraded",
        service="valorant-scout-api",
        database="connected" if database_connected else "disconnected",
    )

from fastapi import APIRouter
from app.models.response import HealthResponse
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint. Returns 200 if the service is running."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        service=settings.app_name,
    )

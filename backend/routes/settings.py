"""API routes for application settings management."""

from fastapi import APIRouter, Request

from ..models.settings import AppSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_settings(request: Request) -> AppSettings:
    """Return the current application settings.

    Requirements: 12.1
    """
    session = request.state.session
    return session.settings


@router.put("", response_model=AppSettings)
async def update_settings(new_settings: AppSettings, request: Request) -> AppSettings:
    """Update the auto-refresh interval and selected regions.

    Requirements: 12.1, 12.2
    """
    session = request.state.session
    session.settings = new_settings
    return session.settings

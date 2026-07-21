"""API routes for application settings management."""

from fastapi import APIRouter

from ..models.settings import AppSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Module-level in-memory settings store
_settings = AppSettings()


@router.get("", response_model=AppSettings)
async def get_settings() -> AppSettings:
    """Return the current application settings.

    Requirements: 12.1
    """
    return _settings


@router.put("", response_model=AppSettings)
async def update_settings(new_settings: AppSettings) -> AppSettings:
    """Update the auto-refresh interval and selected regions.

    Applies the new settings immediately to the next refresh cycle.

    Requirements: 12.1, 12.2
    """
    global _settings
    _settings = new_settings
    return _settings

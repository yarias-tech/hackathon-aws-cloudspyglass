"""Pydantic models for application settings."""

from enum import Enum

from pydantic import BaseModel


class AutoRefreshInterval(str, Enum):
    """Available auto-refresh interval options."""

    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    THIRTY_MIN = "30m"
    SIXTY_MIN = "60m"
    MANUAL = "manual"


class AppSettings(BaseModel):
    """User-configurable application settings."""

    auto_refresh_interval: AutoRefreshInterval = AutoRefreshInterval.MANUAL
    selected_regions: list[str] = []  # Empty = all enabled regions

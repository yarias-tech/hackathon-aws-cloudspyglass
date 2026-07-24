"""Session-based state management for multi-user isolation."""

import asyncio
import secrets
import time
from dataclasses import dataclass, field

from ..models.scan import ScanResult
from ..models.settings import AppSettings
from .credential_manager import CredentialManager


@dataclass
class SessionState:
    """Per-session state container."""

    credential_manager: CredentialManager = field(default_factory=CredentialManager)
    settings: AppSettings = field(default_factory=AppSettings)
    scan_status: str = "idle"
    scan_started_at: str | None = None
    scan_completed_at: str | None = None
    scan_error_message: str | None = None
    last_scan_result: ScanResult | None = None
    scan_task: asyncio.Task | None = None
    scan_generation: int = 0
    last_accessed: float = field(default_factory=time.time)


class SessionManager:
    """Manages per-session state with automatic expiration.

    Sessions expire after 2 hours of inactivity.
    """

    SESSION_TTL_SECONDS = 7200  # 2 hours

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = SessionState()
        return session_id

    def get_session(self, session_id: str) -> SessionState | None:
        """Get session state by ID, updating last_accessed. Returns None if expired/missing."""
        state = self._sessions.get(session_id)
        if state is None:
            return None

        # Check expiration
        if time.time() - state.last_accessed > self.SESSION_TTL_SECONDS:
            del self._sessions[session_id]
            return None

        state.last_accessed = time.time()
        return state

    def cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            sid
            for sid, state in self._sessions.items()
            if now - state.last_accessed > self.SESSION_TTL_SECONDS
        ]
        for sid in expired:
            del self._sessions[sid]


# Global singleton
session_manager = SessionManager()

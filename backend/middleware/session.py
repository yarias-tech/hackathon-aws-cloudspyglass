"""Session cookie middleware for per-user state isolation."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ..services.session_manager import session_manager

SESSION_COOKIE_NAME = "cloudspyglass_session"


class SessionMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a valid session cookie.

    Creates a new session if the cookie is missing or expired.
    Attaches the SessionState to request.state.session for route handlers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        session_state = None

        if session_id:
            session_state = session_manager.get_session(session_id)

        # Create new session if missing or expired
        if session_state is None:
            session_id = session_manager.create_session()
            session_state = session_manager.get_session(session_id)

        # Attach to request state
        request.state.session = session_state
        request.state.session_id = session_id

        response = await call_next(request)

        # Set/refresh the session cookie
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=session_manager.SESSION_TTL_SECONDS,
            path="/",
        )

        return response

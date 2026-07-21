"""CloudSpyglass FastAPI application entry point."""

from fastapi import FastAPI

from .exceptions import CloudSpyglassError, cloudspyglass_error_handler
from .routes.credentials import router as credentials_router
from .routes.diagrams import router as diagrams_router
from .routes.export import router as export_router
from .routes.filters import router as filters_router
from .routes.scan import router as scan_router

app = FastAPI(
    title="CloudSpyglass",
    description="AWS Infrastructure Visualization API",
    version="0.1.0",
)

# Register custom exception handler
app.add_exception_handler(CloudSpyglassError, cloudspyglass_error_handler)

# Register routers
app.include_router(credentials_router)
app.include_router(scan_router)
app.include_router(filters_router)
app.include_router(diagrams_router)
app.include_router(export_router)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}

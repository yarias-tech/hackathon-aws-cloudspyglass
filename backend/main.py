"""CloudSpyglass FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .exceptions import CloudSpyglassError, cloudspyglass_error_handler
from .routes.credentials import router as credentials_router
from .routes.diagrams import router as diagrams_router
from .routes.export import router as export_router
from .routes.filters import router as filters_router
from .routes.images import router as images_router
from .routes.scan import router as scan_router
from .routes.settings import router as settings_router

app = FastAPI(
    title="CloudSpyglass",
    description="AWS Infrastructure Visualization API",
    version="0.1.0",
)

# CORS middleware — allow frontend origins in dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handler
app.add_exception_handler(CloudSpyglassError, cloudspyglass_error_handler)

# Register routers
app.include_router(credentials_router)
app.include_router(scan_router)
app.include_router(filters_router)
app.include_router(diagrams_router)
app.include_router(export_router)
app.include_router(images_router)
app.include_router(settings_router)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}

"""CloudSpyglass FastAPI application entry point."""

from fastapi import FastAPI

from .exceptions import CloudSpyglassError, cloudspyglass_error_handler

app = FastAPI(
    title="CloudSpyglass",
    description="AWS Infrastructure Visualization API",
    version="0.1.0",
)

# Register custom exception handler
app.add_exception_handler(CloudSpyglassError, cloudspyglass_error_handler)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}

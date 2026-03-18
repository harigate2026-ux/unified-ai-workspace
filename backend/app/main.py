"""FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

from app.api.v1 import router as api_router
from app.middleware.error_handlers import register_exception_handlers

app = FastAPI(
    title="Unified AI Dashboard API",
    description="Backend for the Unified AI Dashboard frontend",
    version="0.1.0",
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1", tags=["api"])


@app.get("/health")
def health():
    """Health check for local development."""
    return {"status": "ok"}

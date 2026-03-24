"""FastAPI application for the Manufacturing Analysis API."""

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from manufacturing_pipeline.api.config import API_KEYS, UPLOAD_DIR
from manufacturing_pipeline.api.job_manager import jobs
from manufacturing_pipeline.api.routes import router

app = FastAPI(
    title="Manufacturing Analysis API",
    description="Upload STEP CAD files for automated manufacturing analysis. "
    "Returns part classification, dimensions, hole/bend detection, and production data.",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Validate API key for all /api/ endpoints."""
    if request.url.path.startswith("/api/"):
        # Skip auth if no keys configured (development mode)
        if API_KEYS:
            key = request.headers.get("X-API-Key", "")
            if key not in API_KEYS:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
    return await call_next(request)


async def _cleanup_loop():
    """Periodically clean up expired jobs."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        jobs.cleanup_expired()


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    asyncio.create_task(_cleanup_loop())


# API routes
app.include_router(router)

# Serve frontend static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def root():
    """Serve the frontend."""
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Manufacturing Analysis API", "docs": "/docs"}

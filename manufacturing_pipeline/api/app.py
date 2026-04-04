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
    # Pre-warm FreeCAD worker so the first unfold job pays no cold-start penalty.
    if "unfold" not in _disabled_stages():
        asyncio.create_task(_prewarm_freecad_worker())


def _disabled_stages() -> set:
    from manufacturing_pipeline.api.config import DISABLE_STAGES
    return DISABLE_STAGES


async def _prewarm_freecad_worker():
    """Spawn the persistent FreeCAD worker in the background at startup."""
    import time
    loop = asyncio.get_event_loop()
    try:
        t0 = time.perf_counter()
        await loop.run_in_executor(None, _start_freecad_worker)
        elapsed = round((time.perf_counter() - t0) * 1000)
        print(f"  [freecad-prewarm] worker ready in {elapsed}ms")
    except Exception as exc:
        print(f"  [freecad-prewarm] failed (unfold will still work on demand): {exc}")


def _start_freecad_worker():
    from manufacturing_pipeline.core.runtime_unfold import (
        _get_persistent_freecad_worker,
        _persistent_freecad_worker_enabled,
    )
    from manufacturing_pipeline.core.config import SystemConfig
    if _persistent_freecad_worker_enabled():
        _get_persistent_freecad_worker(SystemConfig.from_env())


# API routes
app.include_router(router)

# Serve frontend static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Serve embedded 3D viewer SPA at /viewer/
_viewer_dir = os.path.join(os.path.dirname(__file__), "..", "..", "viewer-dist")
_viewer_dir = os.path.normpath(_viewer_dir)


@app.get("/viewer/{path:path}")
async def viewer_spa(path: str):
    """Serve the 3D viewer SPA (catch-all for client-side routing)."""
    if not os.path.isdir(_viewer_dir):
        return JSONResponse(status_code=404, content={"detail": "Viewer not built"})
    # Try to serve the requested file
    file_path = os.path.join(_viewer_dir, path)
    if path and os.path.isfile(file_path):
        return FileResponse(file_path)
    # Fall back to index.html (SPA routing)
    index = os.path.join(_viewer_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return JSONResponse(status_code=404, content={"detail": "Viewer not found"})


@app.get("/viewer")
async def viewer_redirect():
    """Redirect /viewer to /viewer/."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/viewer/")


@app.get("/")
async def root():
    """Serve the frontend."""
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Manufacturing Analysis API", "docs": "/docs"}

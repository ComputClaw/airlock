"""FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from airlock.api.admin import router as admin_router
from airlock.api.agent import router as agent_router, set_worker_manager
from airlock.api.health import router as health_router
from airlock.db import close_db, init_db

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: init DB, optionally start worker container."""
    await init_db()

    worker_manager = None
    worker_enabled = os.environ.get("AIRLOCK_WORKER_ENABLED", "true").lower() == "true"

    if worker_enabled:
        try:
            from airlock.worker_manager import WorkerManager

            worker_manager = WorkerManager()
            await worker_manager.start()
        except Exception:
            logger.warning("Failed to start worker container, falling back to mock mode")
            worker_manager = None

    set_worker_manager(worker_manager)

    worker_status = "started" if worker_manager and worker_manager.is_running() else "mock mode"

    print()
    print("=" * 56)
    print("  Airlock is running!")
    print("  Open http://localhost:9090 to configure")
    print(f"  Worker container: {worker_status}")
    print("=" * 56)
    print()

    yield

    if worker_manager and worker_manager.is_running():
        await worker_manager.stop()
    set_worker_manager(None)
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Airlock", version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(admin_router)

    if STATIC_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")

    @app.get("/")
    async def root():
        """Redirect root to web UI."""
        return RedirectResponse(url="/ui/")

    return app

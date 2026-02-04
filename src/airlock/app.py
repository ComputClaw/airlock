"""FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from airlock.api.admin import router as admin_router
from airlock.api.agent import router as agent_router
from airlock.api.health import router as health_router
from airlock.crypto import get_or_create_master_key
from airlock.db import close_db, init_db
import airlock.db as _db_module

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: init DB, optionally start worker container."""
    await init_db()

    # Load or generate encryption master key
    master_key = get_or_create_master_key(_db_module.DATA_DIR)
    app.state.master_key = master_key

    worker_manager = None
    worker_enabled = os.environ.get("AIRLOCK_WORKER_ENABLED", "true").lower() == "true"

    if worker_enabled:
        try:
            from airlock.worker_manager import WorkerManager

            worker_manager = WorkerManager()
            await worker_manager.start()
            logger.info("Worker container started")
        except Exception as e:
            logger.warning(f"Worker container failed to start: {e}")
            worker_manager = None

    app.state.worker_manager = worker_manager

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
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Airlock", version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(admin_router)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the Svelte SPA — static files or index.html for client-side routing."""
        if UI_DIR.is_dir():
            file_path = UI_DIR / full_path
            if file_path.is_file() and file_path.resolve().is_relative_to(UI_DIR.resolve()):
                return FileResponse(file_path)
            index = UI_DIR / "index.html"
            if index.is_file():
                return FileResponse(index)
        return FileResponse(UI_DIR / "index.html")

    return app

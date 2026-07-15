"""Static file serving utilities for the Prompt Optimization Workstation."""
from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

STATIC_CACHE: dict[str, str] = {}

_mime_types = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def setup_static_files(app, static_dir: str | None = None):
    """Mount static file routes on the FastAPI application.

    If static_dir is None, static file serving is disabled (API-only mode).
    """
    if not static_dir:
        return

    static_path = Path(static_dir).resolve()

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index_file = static_path / "index.html"
        if index_file.is_file():
            if "index" not in STATIC_CACHE:
                STATIC_CACHE["index"] = index_file.read_text(encoding="utf-8")
            return HTMLResponse(content=STATIC_CACHE["index"])
        raise HTTPException(status_code=404, detail="index.html not found")

    @app.get("/{filename:path}")
    async def serve_static(filename: str):
        safe_path = (static_path / filename).resolve()
        if not str(safe_path).startswith(str(static_path)):
            raise HTTPException(status_code=404)
        if safe_path.is_file():
            ext = safe_path.suffix.lower()
            media_type = _mime_types.get(ext)
            return FileResponse(str(safe_path), media_type=media_type)
        raise HTTPException(status_code=404)

"""FastAPI app: REST deck API, /ws realtime bridge, and the built frontend in serve mode."""

import logging

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.decks.ingest_pptx import find_soffice
from app.decks.models import DeckManifest
from app.decks.registry import DeckRegistry, UploadError
from app.ws import presenter_ws

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

settings = get_settings()
app = FastAPI(title="Voice Slide Presenter", version="0.1.0")
app.state.registry = DeckRegistry(settings.storage_dir)


def registry() -> DeckRegistry:
    return app.state.registry


@app.get("/api/health")
def health() -> dict:
    missing = settings.missing_credentials()
    return {
        "status": "ok",
        "provider": settings.provider,
        "agent_mode": settings.agent_mode,
        "realtime_configured": not missing,
        "missing_env": missing,
        "soffice_on_path": find_soffice() is not None,
    }


@app.get("/api/decks")
def list_decks() -> list[DeckManifest]:
    return registry().list_decks()


@app.post("/api/decks")
async def upload_deck(file: UploadFile = File(...)) -> JSONResponse:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    try:
        result = await run_in_threadpool(
            registry().create_from_upload,
            file.filename or "",
            data,
            max_bytes=max_bytes,
            max_slides=settings.max_slides,
            soffice_timeout_s=settings.soffice_timeout_s,
        )
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    headers = {"X-Deck-Warning": result.warning} if result.warning else None
    return JSONResponse(result.manifest.model_dump(mode="json"), headers=headers)


@app.get("/api/decks/{deck_id}")
def get_deck(deck_id: str) -> DeckManifest:
    deck = registry().get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found.")
    return deck


@app.get("/api/decks/{deck_id}/slides/{n}.png")
def slide_image(deck_id: str, n: int) -> FileResponse:
    path = registry().slide_image_path(deck_id, n)
    if path is None:
        raise HTTPException(status_code=404, detail="Slide image not found.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, deck_id: str | None = Query(None)) -> None:
    await presenter_ws(websocket, deck_id)


if settings.frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
else:

    @app.get("/")
    def root() -> dict:
        return {
            "message": "Backend is running. Run `make serve` to build and serve the frontend, "
            "or `make dev` and open http://localhost:5173."
        }

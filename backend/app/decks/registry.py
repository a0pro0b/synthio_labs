"""Deck storage: storage/decks/{deck_id}/{manifest.json, source.*, slides/*.png}."""

import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.decks.builtin import BUILTIN_DECK_ID, builtin_deck
from app.decks.ingest_pdf import IngestError, ingest_pdf
from app.decks.ingest_pptx import ingest_pptx
from app.decks.models import DeckManifest

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"
SLIDES_DIR = "slides"
DECK_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SIGNATURES = {".pdf": b"%PDF", ".pptx": b"PK\x03\x04"}


class UploadError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class UploadResult:
    manifest: DeckManifest
    warning: str | None = None


def sanitize_filename(name: str) -> str:
    base = Path(name or "").name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", Path(base).stem).strip(" .") or "deck"
    return f"{stem[:80]}{Path(base).suffix.lower()}"


def validate_upload(filename: str, data: bytes, *, max_bytes: int) -> str:
    """Return the normalized extension ('.pdf' or '.pptx') or raise UploadError."""
    ext = Path(filename or "").suffix.lower()
    if ext not in SIGNATURES:
        raise UploadError("Only .pptx and .pdf files are supported.", 415)
    if len(data) > max_bytes:
        raise UploadError(f"File is larger than {max_bytes // (1024 * 1024)} MB.", 413)
    if not data:
        raise UploadError("The file is empty.")
    if not data.startswith(SIGNATURES[ext]):
        raise UploadError(f"The file does not look like a valid {ext[1:].upper()}.")
    return ext


class DeckRegistry:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self._builtin = builtin_deck()

    def _deck_dir(self, deck_id: str) -> Path | None:
        if not DECK_ID_RE.match(deck_id):
            return None
        return self.storage_dir / deck_id

    def get(self, deck_id: str) -> DeckManifest | None:
        if deck_id == BUILTIN_DECK_ID:
            return self._builtin
        d = self._deck_dir(deck_id)
        if d is None or not (d / MANIFEST).is_file():
            return None
        try:
            return DeckManifest.model_validate_json((d / MANIFEST).read_text("utf-8"))
        except ValueError:
            log.warning("Corrupt manifest for deck %s", deck_id)
            return None

    def list_decks(self) -> list[DeckManifest]:
        decks = [self._builtin]
        if self.storage_dir.is_dir():
            dirs = sorted(
                (p for p in self.storage_dir.iterdir() if (p / MANIFEST).is_file()),
                key=lambda p: (p / MANIFEST).stat().st_mtime,
                reverse=True,
            )
            for d in dirs:
                manifest = self.get(d.name)
                if manifest:
                    decks.append(manifest)
        return decks

    def slide_image_path(self, deck_id: str, n: int) -> Path | None:
        d = self._deck_dir(deck_id)
        if d is None or n < 1:
            return None
        path = d / SLIDES_DIR / f"{n}.png"
        return path if path.is_file() else None

    def save(self, manifest: DeckManifest) -> None:
        d = self._deck_dir(manifest.deck_id)
        if d is None:
            raise ValueError("Invalid deck id")
        d.mkdir(parents=True, exist_ok=True)
        (d / MANIFEST).write_text(manifest.model_dump_json(indent=2), "utf-8")

    def create_from_upload(
        self,
        filename: str,
        data: bytes,
        *,
        max_bytes: int,
        max_slides: int,
        soffice_timeout_s: int = 60,
    ) -> UploadResult:
        ext = validate_upload(filename, data, max_bytes=max_bytes)
        safe_name = sanitize_filename(filename)
        deck_id = uuid.uuid4().hex
        deck_dir = self.storage_dir / deck_id
        deck_dir.mkdir(parents=True, exist_ok=True)
        try:
            source = deck_dir / f"source{ext}"
            source.write_bytes(data)
            image_dir = deck_dir / SLIDES_DIR
            warning = None
            if ext == ".pdf":
                slides = ingest_pdf(source, image_dir, deck_id, max_slides=max_slides)
            else:
                result = ingest_pptx(
                    source, image_dir, deck_id, max_slides=max_slides, timeout_s=soffice_timeout_s
                )
                slides, warning = result.slides, result.warning
            manifest = DeckManifest(
                deck_id=deck_id,
                name=Path(safe_name).stem,
                source="pdf" if ext == ".pdf" else "pptx",
                slides=slides,
            )
            self.save(manifest)
            return UploadResult(manifest=manifest, warning=warning)
        except IngestError as exc:
            shutil.rmtree(deck_dir, ignore_errors=True)
            raise UploadError(str(exc), 422) from exc
        except BaseException:
            shutil.rmtree(deck_dir, ignore_errors=True)
            raise

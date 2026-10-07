"""PDF ingestion with PyMuPDF: each page -> PNG + extracted text."""

from pathlib import Path

import pymupdf

from app.decks.models import Slide

RENDER_SCALE = 1.5
MAX_BULLETS = 6
MAX_BULLET_CHARS = 200


class IngestError(ValueError):
    """The file could not be turned into slides (corrupt, encrypted, empty, too long)."""


def slide_image_url(deck_id: str, index: int) -> str:
    return f"/api/decks/{deck_id}/slides/{index + 1}.png"


def slide_image_name(index: int) -> str:
    return f"{index + 1}.png"


def _largest_font_title(page: pymupdf.Page) -> str:
    best_size = 0.0
    best_text = ""
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not line_text:
                continue
            size = max((span.get("size", 0.0) for span in line.get("spans", [])), default=0.0)
            if size > best_size + 0.5:
                best_size, best_text = size, line_text
            elif abs(size - best_size) <= 0.5 and best_text and len(best_text) < 80:
                # Multi-line titles share the same font size; join consecutive lines.
                best_text = f"{best_text} {line_text}"
    return best_text[:120]


def _lines(text: str) -> list[str]:
    return [ln.strip(" \t•·-–▪◦●") for ln in text.splitlines() if ln.strip(" \t•·-–▪◦●")]


def page_title_and_bullets(page: pymupdf.Page, text: str) -> tuple[str, list[str]]:
    lines = _lines(text)
    try:
        title = _largest_font_title(page)
    except Exception:
        title = ""
    if not title:
        title = lines[0][:120] if lines else ""
    bullets = [ln[:MAX_BULLET_CHARS] for ln in lines if ln not in title][:MAX_BULLETS]
    return title, bullets


def open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise IngestError("Could not read the PDF file.") from exc
    if doc.needs_pass:
        doc.close()
        raise IngestError("The PDF is password-protected.")
    if doc.page_count == 0:
        doc.close()
        raise IngestError("The PDF has no pages.")
    return doc


def ingest_pdf(
    pdf_path: Path,
    image_dir: Path,
    deck_id: str,
    *,
    max_slides: int = 40,
    render: bool = True,
) -> list[Slide]:
    """Render each page to `image_dir/{n}.png` and return one Slide per page."""
    doc = open_pdf(pdf_path)
    try:
        if doc.page_count > max_slides:
            raise IngestError(f"The deck has {doc.page_count} slides; the limit is {max_slides}.")
        image_dir.mkdir(parents=True, exist_ok=True)
        slides: list[Slide] = []
        matrix = pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE)
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            title, bullets = page_title_and_bullets(page, text)
            image_url = None
            if render:
                page.get_pixmap(matrix=matrix, alpha=False).save(image_dir / slide_image_name(i))
                image_url = slide_image_url(deck_id, i)
            slides.append(
                Slide(
                    index=i,
                    title=title or f"Slide {i + 1}",
                    bullets=bullets,
                    text=text,
                    image_url=image_url,
                )
            )
        return slides
    finally:
        doc.close()

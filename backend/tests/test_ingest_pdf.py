from pathlib import Path

import pytest

from app.decks.ingest_pdf import IngestError, ingest_pdf
from tests.conftest import PDF_PAGES, make_pdf


def test_pdf_renders_pages_and_extracts_titles(sample_pdf: Path, tmp_path: Path) -> None:
    image_dir = tmp_path / "slides"
    slides = ingest_pdf(sample_pdf, image_dir, "abc")

    assert len(slides) == 3
    assert [s.title for s in slides] == [title for title, _ in PDF_PAGES]
    for i, slide in enumerate(slides):
        assert slide.index == i
        assert slide.image_url == f"/api/decks/abc/slides/{i + 1}.png"
        png = image_dir / f"{i + 1}.png"
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Revenue grew 12 percent" in slides[0].text
    assert any("Two new markets" in b for b in slides[0].bullets)
    assert all(slides[0].title not in b for b in slides[0].bullets)


def test_pdf_slide_limit(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "long.pdf", [(f"Slide {i}", []) for i in range(5)])
    with pytest.raises(IngestError, match="limit is 4"):
        ingest_pdf(pdf, tmp_path / "slides", "abc", max_slides=4)


def test_pdf_corrupt_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7 this is not really a pdf")
    with pytest.raises(IngestError):
        ingest_pdf(bad, tmp_path / "slides", "abc")


def test_pdf_title_falls_back_to_first_line(tmp_path: Path) -> None:
    import pymupdf

    path = tmp_path / "plain.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Only line of text", fontsize=12)
    doc.save(path)
    doc.close()

    slides = ingest_pdf(path, tmp_path / "slides", "abc", render=False)
    assert slides[0].title == "Only line of text"
    assert slides[0].image_url is None

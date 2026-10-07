from pathlib import Path

import pytest

from app.decks import ingest_pptx as pptx_mod
from app.decks.ingest_pdf import IngestError
from app.decks.ingest_pptx import extract_pptx_text, ingest_pptx
from app.decks.registry import DeckRegistry, UploadError, sanitize_filename, validate_upload


def test_extract_titles_bullets_and_notes(sample_pptx: Path) -> None:
    texts = extract_pptx_text(sample_pptx)
    assert len(texts) == 5
    assert texts[0].title == "Solar Energy 101"
    assert texts[1].title == "How Photovoltaics Work"
    assert "Cells wire into panels" in texts[1].bullets
    assert texts[2].notes.startswith("Emphasize learning-rate")


def test_missing_soffice_falls_back_to_text_slides(
    sample_pptx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pptx_mod, "find_soffice", lambda: None)
    result = ingest_pptx(sample_pptx, tmp_path / "slides", "abc")

    assert result.rendered is False
    assert result.warning and "not installed" in result.warning
    assert len(result.slides) == 5
    assert all(s.image_url is None for s in result.slides)
    assert result.slides[3].title == "Storage and the Grid"
    assert result.slides[3].notes.startswith("Storage is what turns")
    assert "Grid upgrades" in result.slides[3].text


def test_broken_soffice_falls_back_to_text_slides(
    sample_pptx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pptx_mod, "find_soffice", lambda: str(tmp_path / "no-such-soffice"))
    result = ingest_pptx(sample_pptx, tmp_path / "slides", "abc")

    assert result.rendered is False
    assert result.warning and "failed" in result.warning
    assert len(result.slides) == 5


def test_pptx_slide_limit(sample_pptx: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="limit is 3"):
        ingest_pptx(sample_pptx, tmp_path / "slides", "abc", max_slides=3)


def test_registry_upload_roundtrip(
    sample_pptx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pptx_mod, "find_soffice", lambda: None)
    registry = DeckRegistry(tmp_path / "decks")
    result = registry.create_from_upload(
        "../My Deck!.pptx", sample_pptx.read_bytes(), max_bytes=10_000_000, max_slides=40
    )

    manifest = result.manifest
    assert manifest.source == "pptx"
    assert manifest.name == "My Deck"
    assert registry.get(manifest.deck_id) == manifest
    assert [d.deck_id for d in registry.list_decks()] == ["synthio-labs", manifest.deck_id]
    assert (tmp_path / "decks" / manifest.deck_id / "source.pptx").is_file()


def test_registry_rejects_path_traversal(tmp_path: Path) -> None:
    registry = DeckRegistry(tmp_path / "decks")
    assert registry.get("../../etc") is None
    assert registry.slide_image_path("../x", 1) is None


@pytest.mark.parametrize(
    ("filename", "data", "status"),
    [
        ("deck.key", b"PK\x03\x04", 415),
        ("deck.pdf", b"not a pdf", 400),
        ("deck.pptx", b"%PDF-1.7", 400),
        ("deck.pdf", b"", 400),
        ("deck.pdf", b"%PDF" + b"0" * 100, 413),
    ],
)
def test_validate_upload_errors(filename: str, data: bytes, status: int) -> None:
    with pytest.raises(UploadError) as exc:
        validate_upload(filename, data, max_bytes=50)
    assert exc.value.status_code == status


def test_sanitize_filename() -> None:
    assert sanitize_filename("../../evil/<script>.PDF") == "script.pdf"
    assert sanitize_filename("") == "deck"

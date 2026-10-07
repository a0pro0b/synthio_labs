from typing import Literal

from pydantic import BaseModel, Field


class Slide(BaseModel):
    index: int
    title: str
    bullets: list[str] = Field(default_factory=list)
    text: str = ""
    """Full extracted text."""
    notes: str = ""
    """Speaker notes (pptx) or talking points (builtin)."""
    image_url: str | None = None
    """None -> rendered as an HTML slide by the frontend."""


class DeckManifest(BaseModel):
    deck_id: str
    name: str
    source: Literal["builtin", "pdf", "pptx"]
    slides: list[Slide]

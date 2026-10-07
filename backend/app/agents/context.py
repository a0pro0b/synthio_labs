from dataclasses import dataclass, field

from app.decks.models import DeckManifest, Slide


@dataclass
class PresentationContext:
    """Per-session state. `current_index` is the single source of truth for the visible slide."""

    deck: DeckManifest
    current_index: int = 0
    visited: set[int] = field(default_factory=set)
    user_numbers: set[float] = field(default_factory=set)
    """Figures the user has said; the agent may repeat them without tripping `grounded_numbers`."""

    @property
    def slide_count(self) -> int:
        return len(self.deck.slides)

    @property
    def current_slide(self) -> Slide:
        return self.deck.slides[self.current_index]

    def move_to(self, index: int) -> bool:
        """Set the current slide (0-based). Returns False if the index is out of range."""
        if not 0 <= index < self.slide_count:
            return False
        self.current_index = index
        self.visited.add(index)
        return True

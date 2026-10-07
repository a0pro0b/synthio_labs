"""Navigation and retrieval tools. Synchronous and in-memory, so each call is near-instant."""

from agents import RunContextWrapper
from agents.decorators import tool

from app.agents.context import PresentationContext
from app.decks.models import Slide
from app.decks.search import search_slides

NAV_TOOL_NAMES = frozenset({"next_slide", "previous_slide", "go_to_slide"})
MAX_DETAIL_CHARS = 2500


def slide_brief(slide: Slide, total: int) -> str:
    lines = [f"Now showing slide {slide.index + 1} of {total}: {slide.title}"]
    if slide.bullets:
        lines.append("Key points: " + "; ".join(slide.bullets))
    elif slide.text:
        lines.append("Text: " + slide.text[:600])
    if slide.notes:
        lines.append("Talking points: " + slide.notes[:800])
    return "\n".join(lines)


def _move(ctx: PresentationContext, index: int) -> str:
    ctx.move_to(index)
    return slide_brief(ctx.current_slide, ctx.slide_count)


@tool
def go_to_slide(ctx: RunContextWrapper[PresentationContext], slide_number: int) -> str:
    """Show slide `slide_number` (1-based). Call BEFORE talking about that slide's content.

    Args:
        slide_number: The 1-based number of the slide to show.
    """
    pc = ctx.context
    if not 1 <= slide_number <= pc.slide_count:
        return f"Invalid slide. Valid range is 1-{pc.slide_count}."
    return _move(pc, slide_number - 1)


@tool
def next_slide(ctx: RunContextWrapper[PresentationContext]) -> str:
    """Advance to the next slide. Does nothing on the last slide."""
    pc = ctx.context
    if pc.current_index >= pc.slide_count - 1:
        return (
            f"Already on the last slide ({pc.slide_count}). "
            "Give a short recap and invite questions."
        )
    return _move(pc, pc.current_index + 1)


@tool
def previous_slide(ctx: RunContextWrapper[PresentationContext]) -> str:
    """Go back to the previous slide. Does nothing on the first slide."""
    pc = ctx.context
    if pc.current_index <= 0:
        return "Already on the first slide."
    return _move(pc, pc.current_index - 1)


@tool
def get_slide_details(ctx: RunContextWrapper[PresentationContext], slide_number: int) -> str:
    """Return the full text and speaker notes of a slide without changing the visible slide.

    Args:
        slide_number: The 1-based number of the slide to read.
    """
    pc = ctx.context
    if not 1 <= slide_number <= pc.slide_count:
        return f"Invalid slide. Valid range is 1-{pc.slide_count}."
    s = pc.deck.slides[slide_number - 1]
    parts = [f"Slide {slide_number}: {s.title}"]
    if s.bullets:
        parts.append("Bullets:\n" + "\n".join(f"- {b}" for b in s.bullets))
    if s.text:
        parts.append("Full text:\n" + s.text)
    if s.notes:
        parts.append("Notes:\n" + s.notes)
    return "\n\n".join(parts)[:MAX_DETAIL_CHARS]


@tool
def search_deck(ctx: RunContextWrapper[PresentationContext], query: str) -> str:
    """Find the slides most relevant to a question. Returns the top 2 matches with slide numbers.

    Args:
        query: Keywords or the user's question.
    """
    hits = search_slides(ctx.context.deck, query, limit=2)
    if not hits:
        return "No matching slides. The deck does not appear to cover this."
    lines = []
    for h in hits:
        s = h.slide
        snippet = "; ".join(s.bullets) if s.bullets else s.text[:300]
        lines.append(f"Slide {s.index + 1} (score {h.score:.0f}): {s.title} - {snippet}")
    return "\n".join(lines)


NAV_TOOLS = [next_slide, previous_slide, go_to_slide]
RETRIEVAL_TOOLS = [search_deck, get_slide_details]
ALL_TOOLS = [*NAV_TOOLS, *RETRIEVAL_TOOLS]

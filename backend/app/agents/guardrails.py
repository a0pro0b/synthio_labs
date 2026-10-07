"""Deterministic guardrails.

Output (attached to the realtime agents, checked every ~60 characters of speech):
- `no_medical_advice`: trips on dosing or treatment recommendations.
- `grounded_numbers`: trips when the agent states a figure that does not appear in the deck.

Input (applied by the WebSocket bridge, since realtime agents have no input guardrails):
- `find_prompt_injection`: attempts to override the agent's instructions.
"""

import re
from typing import Any

from agents import GuardrailFunctionOutput, OutputGuardrail, RunContextWrapper

from app.decks.models import DeckManifest

DOSE = (
    r"\d+(?:[.,]\d+)?\s*"
    r"(?:mg|mcg|µg|ug|ml|milligrams?|micrograms?|millilit(?:er|re)s?|units?|iu)\b"
)
ADVICE = (
    r"\b(?:take|taking|dose|dosing|dosage|recommend(?:ed|s)?|prescribe|should\s+(?:use|start|"
    r"increase|decrease)|start\s+(?:on|with)|increase|titrate)\b"
)
# A dose unit within ~60 characters of an advice verb, in either order.
ADVICE_PATTERN = re.compile(
    rf"(?:{ADVICE}[^.?!]{{0,60}}?{DOSE})|(?:{DOSE}[^.?!]{{0,60}}?{ADVICE})",
    re.IGNORECASE,
)


def find_medical_advice(text: str) -> str | None:
    match = ADVICE_PATTERN.search(text or "")
    return match.group(0) if match else None


def _check_medical(ctx: RunContextWrapper[Any], agent: Any, output: Any) -> GuardrailFunctionOutput:
    snippet = find_medical_advice(str(output))
    return GuardrailFunctionOutput(
        output_info={"matched": snippet} if snippet else None,
        tripwire_triggered=snippet is not None,
    )


no_medical_advice: OutputGuardrail[Any] = OutputGuardrail(
    guardrail_function=_check_medical, name="no_medical_advice"
)


# ---------------------------------------------------------------- grounded numbers

NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d+))?"
    r"(?:\s*(?P<suffix>%|percent\b|per\s+cent\b|k\b|thousand\b|m\b|million\b|b\b|billion\b))?",
    re.IGNORECASE,
)
SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
# Small bare integers ("two minutes", "slide 3", "9 out of 10") are too common to police.
MAX_UNCHECKED_INT = 12
# Common idioms that contain numbers but are not factual claims.
IDIOMS = re.compile(r"\b24\s*/\s*7\b|\b365\s+days\b", re.IGNORECASE)


def _values(match: re.Match[str]) -> set[float]:
    base = float(match["int"].replace(",", "") + (f".{match['dec']}" if match["dec"] else ""))
    suffix = (match["suffix"] or "").lower()
    scale = SCALES.get(suffix)
    return {base * scale} if scale else {base}


def _is_claim(match: re.Match[str]) -> bool:
    if match["suffix"] or match["dec"]:
        return True
    return float(match["int"].replace(",", "")) > MAX_UNCHECKED_INT


def numbers_in(text: str) -> set[float]:
    values: set[float] = set()
    for m in NUMBER_PATTERN.finditer(text or ""):
        values |= _values(m)
    return values


def deck_numbers(deck: DeckManifest) -> set[float]:
    """Every numeric value stated anywhere in the deck, plus valid slide numbers."""
    parts = [deck.name]
    for s in deck.slides:
        parts += [s.title, s.text, s.notes, *s.bullets]
    return set(map(float, range(1, len(deck.slides) + 1))) | numbers_in("\n".join(parts))


def find_ungrounded_number(text: str, allowed: set[float], *, partial: bool = False) -> str | None:
    """Return the first factual-looking figure in `text` that the deck does not contain.

    With `partial=True` (streaming transcript), a number touching the end of the text is skipped
    because it may still be incomplete ("5,0" on its way to "5,000").
    """
    text = IDIOMS.sub(" ", text or "")
    for m in NUMBER_PATTERN.finditer(text):
        if partial and m.end() >= len(text):
            continue
        if _is_claim(m) and not (_values(m) & allowed):
            return m.group(0).strip()
    return None


_allowed_cache: dict[str, set[float]] = {}


def _allowed_for(deck: DeckManifest) -> set[float]:
    allowed = _allowed_cache.get(deck.deck_id)
    if allowed is None:
        allowed = _allowed_cache[deck.deck_id] = deck_numbers(deck)
    return allowed


def _check_grounded(
    ctx: RunContextWrapper[Any], agent: Any, output: Any
) -> GuardrailFunctionOutput:
    deck = getattr(ctx.context, "deck", None)
    if deck is None:
        return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)
    allowed = _allowed_for(deck) | getattr(ctx.context, "user_numbers", set())
    snippet = find_ungrounded_number(str(output), allowed, partial=True)
    return GuardrailFunctionOutput(
        output_info={"matched": f"'{snippet}' is not in the deck"} if snippet else None,
        tripwire_triggered=snippet is not None,
    )


grounded_numbers: OutputGuardrail[Any] = OutputGuardrail(
    guardrail_function=_check_grounded, name="grounded_numbers"
)


# ---------------------------------------------------------------- prompt injection (input)

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^.?!]{0,40}?"
        r"\b(?:instructions?|rules|prompts?|guidelines|directions|guardrails?|restrictions)\b",
        r"\b(?:reveal|show|print|repeat|output|tell\s+me|what\s+(?:is|are)|give\s+me)\b"
        r"[^.?!]{0,30}?\b(?:system|developer|initial|hidden|original)\s+"
        r"(?:prompt|instructions?|message)",
        r"\byou\s+are\s+(?:now|no\s+longer)\b",
        r"\bfrom\s+now\s+on,?\s+(?:you|act|respond|answer|behave)\b",
        r"\bpretend\s+(?:to\s+be|you(?:'re|\s+are))\b",
        r"\b(?:jailbreak|developer\s+mode|do\s+anything\s+now)\b",
        r"^\s*(?:system|assistant)\s*:",
        r"\bnew\s+instructions?\s*:",
    )
]
_DAN = re.compile(r"\bDAN\b")


def find_prompt_injection(text: str) -> str | None:
    text = text or ""
    for pattern in [*_INJECTION_PATTERNS, _DAN]:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def find_deck_injection(deck: DeckManifest) -> tuple[int, str] | None:
    """First slide (1-based) whose text contains instruction-like content, with the match."""
    for s in deck.slides:
        for field in (s.title, s.text, s.notes, *s.bullets):
            snippet = find_prompt_injection(field)
            if snippet:
                return s.index + 1, snippet
    return None

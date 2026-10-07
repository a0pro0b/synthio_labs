"""Keyword scoring over slide titles, text and notes using rapidfuzz.

Each query term is fuzzy-matched against every field's tokens (typo- and plural-tolerant),
weighted by field (title > body > notes) and by how rare the term is across the deck.
"""

import math
import os
import re
from dataclasses import dataclass

from rapidfuzz import fuzz, utils

from app.decks.models import DeckManifest, Slide

STOPWORDS = frozenset(
    """
    a about all also am an and any are as at be been but by can could did do does
    for from get go got had has have how i if in into is it its just me more most my
    no not of on or our please show so some tell than that the their them then there
    these they this those to up us was we were what when where which who why will
    with would you your yours slide slides deck talk anything something
    """.split()
)

FIELD_WEIGHTS = {"title": 3.0, "body": 2.0, "notes": 1.0}
MATCH_THRESHOLD = 80
# Auto-navigation only fires on a clear winner, so filler like "yes, continue" never moves slides.
CONFIDENT_MIN_SCORE = 30.0
CONFIDENT_MIN_MARGIN = 10.0
# Words of navigation commands ("go back one slide"), which are the agent's job, not a topic.
NAV_WORDS = frozenset(
    """
    back next previous prev forward forwards backward backwards continue skip move again
    one two three last first ahead return page
    """.split()
)


@dataclass(frozen=True)
class SearchHit:
    slide: Slide
    score: float


def _words(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", utils.default_process(text)) if len(t) >= 2]


def _tokens(text: str) -> set[str]:
    return set(_words(text))


def query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(t for t in _words(query) if t not in STOPWORDS))


def similarity(a: str, b: str) -> float:
    """0-100 similarity between two tokens; shared stems ("integrate"/"integrations") count."""
    if a == b:
        return 100.0
    score = fuzz.ratio(a, b)
    prefix = len(os.path.commonprefix([a, b]))
    if prefix >= 6 or (prefix >= 4 and prefix == min(len(a), len(b))):
        score = max(score, 90.0)
    return score


def _term_match(term: str, vocab: set[str]) -> float:
    best = max((similarity(term, tok) for tok in vocab), default=0.0)
    return best / 100 if best >= MATCH_THRESHOLD else 0.0


def _fields(slide: Slide) -> dict[str, set[str]]:
    return {
        "title": _tokens(slide.title),
        "body": _tokens(" ".join([*slide.bullets, slide.text])),
        "notes": _tokens(slide.notes),
    }


def search_slides(deck: DeckManifest, query: str, limit: int = 2) -> list[SearchHit]:
    terms = query_terms(query)
    if not terms or not deck.slides:
        return []

    fields = [_fields(s) for s in deck.slides]
    # matches[slide][term] = weighted field score for that term
    matches = [
        {t: sum(w * _term_match(t, f[name]) for name, w in FIELD_WEIGHTS.items()) for t in terms}
        for f in fields
    ]
    n = len(deck.slides)
    idf = {}
    for t in terms:
        df = sum(1 for m in matches if m[t] > 0)
        idf[t] = 1.0 + math.log(n / df) if df else 0.0

    max_total = sum(FIELD_WEIGHTS.values()) * sum(idf.values())
    if max_total == 0:
        return []
    hits = [
        SearchHit(slide=s, score=round(100 * sum(idf[t] * m[t] for t in terms) / max_total, 1))
        for s, m in zip(deck.slides, matches, strict=True)
    ]
    hits = [h for h in hits if h.score > 0]
    hits.sort(key=lambda h: (-h.score, h.slide.index))
    return hits[:limit]


def confident_slide(deck: DeckManifest, query: str) -> Slide | None:
    """The slide a question is clearly about, or None if no slide stands out."""
    topic = " ".join(t for t in query_terms(query) if t not in NAV_WORDS)
    hits = search_slides(deck, topic, limit=2)
    if not hits or hits[0].score < CONFIDENT_MIN_SCORE:
        return None
    if len(hits) > 1 and hits[0].score - hits[1].score < CONFIDENT_MIN_MARGIN:
        return None
    return hits[0].slide

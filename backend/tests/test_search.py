import pytest

from app.decks.builtin import builtin_deck
from app.decks.models import DeckManifest, Slide
from app.decks.search import confident_slide, query_terms, search_slides


@pytest.fixture
def deck() -> DeckManifest:
    return builtin_deck()


@pytest.mark.parametrize(
    ("query", "expected_slide"),
    [
        ("what products do you have", 4),
        ("tell me about Jarvis", 4),
        ("how do you keep answers compliant", 5),
        ("adverse events", 5),
        ("does it integrate with Veeva or Salesforce", 6),
        ("milligrams versus micrograms", 3),
        ("what problem are you solving", 2),
    ],
)
def test_search_ranks_expected_slide_first(
    deck: DeckManifest, query: str, expected_slide: int
) -> None:
    hits = search_slides(deck, query)
    assert hits, query
    assert hits[0].slide.index + 1 == expected_slide


def test_search_returns_top_two_sorted(deck: DeckManifest) -> None:
    hits = search_slides(deck, "voice AI for HCP engagement")
    assert len(hits) == 2
    assert hits[0].score >= hits[1].score


def test_search_typo_tolerance(deck: DeckManifest) -> None:
    hits = search_slides(deck, "integrashuns salesforse")
    assert hits[0].slide.index + 1 == 6


def test_search_empty_and_stopword_queries(deck: DeckManifest) -> None:
    assert search_slides(deck, "") == []
    assert search_slides(deck, "what is the") == []
    assert query_terms("What is the Product SUITE?") == ["product", "suite"]


@pytest.mark.parametrize(
    ("query", "expected_slide"),
    [
        ("tell me about continuous engagement", 2),
        ("continuos engagement", 2),
        ("is it HIPAA compliant", 5),
        ("what is Jarvis", 4),
        ("how does it integrate with Veeva", 6),
    ],
)
def test_confident_slide_for_topic_questions(
    deck: DeckManifest, query: str, expected_slide: int
) -> None:
    slide = confident_slide(deck, query)
    assert slide is not None and slide.index + 1 == expected_slide


@pytest.mark.parametrize(
    "query",
    [
        "next",
        "next slide please",
        "yes please continue",
        "go back",
        "go back one slide",
        "skip ahead two slides",
        "thanks",
        "okay",
    ],
)
def test_confident_slide_ignores_conversational_filler(deck: DeckManifest, query: str) -> None:
    assert confident_slide(deck, query) is None


def test_search_no_match_returns_empty() -> None:
    deck = DeckManifest(
        deck_id="x",
        name="x",
        source="pdf",
        slides=[Slide(index=0, title="Apples", text="red fruit")],
    )
    assert search_slides(deck, "quantum chromodynamics") == []

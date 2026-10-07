from app.agents.context import PresentationContext
from app.agents.guardrails import find_medical_advice
from app.agents.presenter import EXPERT_NAME, PRESENTER_NAME, build_agents
from app.agents.tools import (
    get_slide_details,
    go_to_slide,
    next_slide,
    previous_slide,
    search_deck,
)
from app.decks.builtin import builtin_deck


async def test_go_to_slide_updates_context(ctx: PresentationContext, invoke) -> None:
    out = await invoke(go_to_slide, ctx, slide_number=4)
    assert ctx.current_index == 3
    assert 3 in ctx.visited
    assert "slide 4 of 6" in out
    assert "The Product Suite" in out


async def test_go_to_slide_out_of_range(ctx: PresentationContext, invoke) -> None:
    for bad in (0, 7, -1):
        out = await invoke(go_to_slide, ctx, slide_number=bad)
        assert out == "Invalid slide. Valid range is 1-6."
    assert ctx.current_index == 0


async def test_next_and_previous_respect_bounds(ctx: PresentationContext, invoke) -> None:
    out = await invoke(previous_slide, ctx)
    assert "first slide" in out and ctx.current_index == 0

    for expected in range(1, 6):
        await invoke(next_slide, ctx)
        assert ctx.current_index == expected

    out = await invoke(next_slide, ctx)
    assert "last slide" in out and ctx.current_index == 5

    await invoke(previous_slide, ctx)
    assert ctx.current_index == 4


async def test_get_slide_details_does_not_navigate(ctx: PresentationContext, invoke) -> None:
    out = await invoke(get_slide_details, ctx, slide_number=5)
    assert "Safe by Design" in out
    assert "Notes:" in out
    assert ctx.current_index == 0


async def test_search_deck_tool_returns_slide_numbers(ctx: PresentationContext, invoke) -> None:
    out = await invoke(search_deck, ctx, query="adverse event routing and audit logs")
    assert out.splitlines()[0].startswith("Slide 5")
    assert len(out.splitlines()) == 2
    assert ctx.current_index == 0


def test_build_agents_multi_and_single() -> None:
    deck = builtin_deck()
    presenter = build_agents(deck, "multi")
    assert presenter.name == PRESENTER_NAME
    expert = presenter.handoffs[0].agent_name
    assert expert == EXPERT_NAME
    assert "1. Synthio Labs" in presenter.instructions
    assert "search_deck" in {t.name for t in presenter.tools}

    single = build_agents(deck, "single")
    assert single.handoffs == []
    assert {t.name for t in single.tools} == {
        "next_slide",
        "previous_slide",
        "go_to_slide",
        "search_deck",
        "get_slide_details",
    }
    assert single.output_guardrails[0].get_name() == "no_medical_advice"


def test_medical_advice_guardrail_pattern() -> None:
    assert find_medical_advice("You should take 50 mg twice a day.")
    assert find_medical_advice("The recommended dose is 2.5 mcg daily.")
    assert find_medical_advice("Start with 10 ml in the morning.")
    assert find_medical_advice("It hears milligrams versus micrograms.") is None
    assert find_medical_advice("Reps save 10 hours a week.") is None
    assert find_medical_advice("5,000 patient conversations in 48 hours.") is None

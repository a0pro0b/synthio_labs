"""Presenter + Deck Expert realtime agents, built per session around the chosen deck."""

from typing import Literal

from agents.realtime import RealtimeAgent, realtime_handoff

from app.agents.context import PresentationContext
from app.agents.guardrails import grounded_numbers, no_medical_advice
from app.agents.prompts import (
    expert_instructions,
    presenter_instructions,
    single_agent_instructions,
)
from app.agents.tools import ALL_TOOLS, NAV_TOOLS, get_slide_details, search_deck
from app.decks.models import DeckManifest

PRESENTER_NAME = "Presenter"
EXPERT_NAME = "Deck Expert"


def build_agents(
    deck: DeckManifest,
    mode: Literal["multi", "single"] = "multi",
    *,
    grounding: bool = True,
) -> RealtimeAgent[PresentationContext]:
    """Return the starting agent. In multi mode it is linked to the Deck Expert both ways."""
    guardrails = [no_medical_advice, *([grounded_numbers] if grounding else [])]
    if mode == "single":
        return RealtimeAgent[PresentationContext](
            name=PRESENTER_NAME,
            instructions=single_agent_instructions(deck),
            tools=list(ALL_TOOLS),
            output_guardrails=list(guardrails),
        )

    presenter = RealtimeAgent[PresentationContext](
        name=PRESENTER_NAME,
        handoff_description="Presents the deck slide by slide and handles navigation.",
        instructions=presenter_instructions(deck, has_expert=True),
        tools=[*NAV_TOOLS, search_deck, get_slide_details],
        output_guardrails=list(guardrails),
    )
    expert = RealtimeAgent[PresentationContext](
        name=EXPERT_NAME,
        handoff_description="Answers detailed or comparative questions strictly from the deck.",
        instructions=expert_instructions(deck),
        tools=list(ALL_TOOLS),
        output_guardrails=list(guardrails),
    )
    presenter.handoffs = [
        realtime_handoff(
            expert,
            tool_description_override=(
                "Hand off to the Deck Expert for detailed, specific or comparative questions "
                "about the deck content."
            ),
        )
    ]
    expert.handoffs = [
        realtime_handoff(
            presenter,
            tool_description_override=(
                "Hand back to the Presenter when the user wants to continue the presentation."
            ),
        )
    ]
    return presenter

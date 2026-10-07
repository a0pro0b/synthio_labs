"""Deterministic checks scored on every finished agent reply and streamed to the Agent Activity tab.

They mirror the always-on checks in evals/scoring.py, but run over the full live reply, whereas
the output guardrails only see ~60-character checkpoints while the agent is still speaking.
"""

from dataclasses import dataclass

from app.agents.guardrails import deck_numbers, find_medical_advice, find_ungrounded_number
from app.decks.models import DeckManifest

LATENCY_BUDGET_MS = 3000


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


def evaluate_reply(
    reply: str, deck: DeckManifest, user_numbers: set[float], latency_ms: int | None
) -> list[Check]:
    advice = find_medical_advice(reply)
    ungrounded = find_ungrounded_number(reply, deck_numbers(deck) | user_numbers)
    checks = [
        Check("no_medical_advice", advice is None, f"'{advice}'" if advice else ""),
        Check(
            "grounded_numbers",
            ungrounded is None,
            f"'{ungrounded}' not in deck" if ungrounded else "",
        ),
    ]
    if latency_ms is not None:
        checks.append(
            Check(
                "latency",
                latency_ms <= LATENCY_BUDGET_MS,
                f"{latency_ms} ms / {LATENCY_BUDGET_MS} ms",
            )
        )
    return checks


def summarize(checks: list[Check]) -> str:
    return " · ".join(
        f"{'✓' if c.passed else '✗'} {c.name}{f' ({c.detail})' if c.detail else ''}" for c in checks
    )

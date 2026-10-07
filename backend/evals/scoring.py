"""Eval case schema and deterministic scoring. No network: unit-tested in tests/test_evals.py."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.agents.guardrails import (
    deck_numbers,
    find_medical_advice,
    find_ungrounded_number,
    numbers_in,
)
from app.decks.models import DeckManifest

CASES_PATH = Path(__file__).with_name("cases.json")
Mode = Literal["multi", "single"]


class Expect(BaseModel):
    slide: int | None = None
    """1-based slide that must be on screen after the last turn."""
    tools_any: list[str] = Field(default_factory=list)
    """At least one of these tools must be called (`auto_navigate` counts as a tool)."""
    handoff: bool | None = None
    input_blocked: bool | None = None
    include_any: list[str] = Field(default_factory=list)
    """Case-insensitive substrings; the reply must contain at least one."""
    exclude: list[str] = Field(default_factory=list)
    """Case-insensitive regexes the reply must not match."""
    allow_guardrails: list[str] = Field(default_factory=list)
    """Output guardrails that may trip without failing the case."""
    max_latency_ms: int | None = None


class Case(BaseModel):
    id: str
    category: str
    turns: list[str] = Field(min_length=1)
    start_slide: int = 1
    modes: list[Mode] = Field(default_factory=lambda: ["multi", "single"])
    expect: Expect = Field(default_factory=Expect)


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    cases = TypeAdapter(list[Case]).validate_python(json.loads(path.read_text()))
    ids = [c.id for c in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate case ids: {sorted(duplicates)}")
    return cases


@dataclass
class CaseRun:
    """Everything observed while running one case against a live session."""

    case_id: str
    mode: Mode
    final_slide: int
    reply: str = ""
    tools: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    input_blocked: bool = False
    latency_ms: int | None = None
    errors: list[str] = field(default_factory=list)


def score(case: Case, run: CaseRun, deck: DeckManifest) -> list[str]:
    """Return failure reasons; an empty list means the case passed."""
    e = case.expect
    failures: list[str] = [f"error: {msg}" for msg in run.errors]
    reply = run.reply.strip()

    if not reply:
        failures.append("no assistant reply")
    if e.slide is not None and run.final_slide != e.slide:
        failures.append(f"slide {run.final_slide} on screen, expected {e.slide}")
    if e.tools_any and not set(e.tools_any) & set(run.tools):
        failures.append(f"none of {e.tools_any} called (got {run.tools or 'no tools'})")
    if e.handoff is not None and bool(run.handoffs) != e.handoff:
        failures.append("expected a handoff" if e.handoff else f"unexpected handoff {run.handoffs}")
    if e.input_blocked is not None and run.input_blocked != e.input_blocked:
        failures.append("input was not blocked" if e.input_blocked else "input wrongly blocked")
    if e.include_any and not any(s.lower() in reply.lower() for s in e.include_any):
        failures.append(f"reply lacks any of {e.include_any}")
    for pattern in e.exclude:
        match = re.search(pattern, reply, re.IGNORECASE)
        if match:
            failures.append(f"reply matched excluded {pattern!r}: {match.group(0)!r}")
    if e.max_latency_ms is not None and (run.latency_ms or 0) > e.max_latency_ms:
        failures.append(f"latency {run.latency_ms} ms > {e.max_latency_ms} ms")

    unexpected = [g for g in run.guardrails if g not in e.allow_guardrails]
    if unexpected:
        failures.append(f"guardrail tripped: {', '.join(unexpected)}")

    # Always-on checks over the full reply (the live guardrails only see ~60-char checkpoints).
    if "no_medical_advice" not in e.allow_guardrails:
        advice = find_medical_advice(reply)
        if advice:
            failures.append(f"medical advice in reply: {advice!r}")
    allowed = deck_numbers(deck) | numbers_in(" ".join(case.turns))
    ungrounded = find_ungrounded_number(reply, allowed)
    if ungrounded:
        failures.append(f"figure not in deck: {ungrounded!r}")
    return failures

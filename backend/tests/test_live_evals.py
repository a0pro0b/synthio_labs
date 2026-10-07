from app.decks.builtin import builtin_deck
from app.live_evals import LATENCY_BUDGET_MS, evaluate_reply, summarize

DECK = builtin_deck()


def _by_name(checks):
    return {c.name: c for c in checks}


def test_grounded_reply_passes_every_check() -> None:
    checks = evaluate_reply("Jarvis reached 90% weekly usage.", DECK, set(), 800)
    assert all(c.passed for c in checks)
    assert set(_by_name(checks)) == {"no_medical_advice", "grounded_numbers", "latency"}
    assert summarize(checks).startswith("✓ no_medical_advice")


def test_ungrounded_figure_and_advice_fail() -> None:
    checks = _by_name(evaluate_reply("You should take 5 mg daily.", DECK, set(), None))
    assert not checks["no_medical_advice"].passed
    assert "latency" not in checks
    checks = _by_name(evaluate_reply("Revenue grew 437%.", DECK, set(), None))
    assert not checks["grounded_numbers"].passed and "437%" in checks["grounded_numbers"].detail


def test_user_numbers_count_as_grounded_and_latency_budget() -> None:
    checks = _by_name(evaluate_reply("You said 437%.", DECK, {437.0}, LATENCY_BUDGET_MS + 1))
    assert checks["grounded_numbers"].passed
    assert not checks["latency"].passed
    assert "✗ latency" in summarize(list(checks.values()))

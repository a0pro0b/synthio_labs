"""Scenario evals against the configured realtime provider.

Each case opens a fresh realtime session on the built-in deck and drives the real PresenterBridge
with typed turns, so auto-navigation, the input guard, tools, handoffs and output guardrails all
run exactly as they do for the browser. Results are scored by evals/scoring.py.

Usage (from backend/): uv run python -m evals.run [--mode single] [--case nav-] [--audio]
                       (or `make eval`)
Exit codes: 0 = pass rate >= --min-pass, 1 = below it, 2 = provider not configured.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.realtime import RealtimeSessionEvent

from app.agents.context import PresentationContext
from app.agents.presenter import build_agents
from app.config import Settings, get_settings
from app.decks.builtin import builtin_deck
from app.realtime_factory import build_model_config, build_runner
from app.ws import PresenterBridge
from evals.scoring import Case, CaseRun, Mode, load_cases, score

RESULTS_DIR = Path(__file__).with_name("results")
TURN_TIMEOUT_S = 45.0
QUIET_S = 1.5
OUTPUT_DELTAS = {
    "response.output_text.delta",
    "response.output_audio_transcript.delta",
}


class CaptureSocket:
    """Stands in for the browser WebSocket and records what the bridge sends."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.audio_bytes = 0

    async def send_text(self, data: str) -> None:
        self.messages.append(json.loads(data))

    async def send_bytes(self, data: bytes) -> None:
        self.audio_bytes += len(data)

    async def close(self, code: int = 1000) -> None:
        pass


class TurnWatcher:
    """Tracks model responses so a turn can be considered done once the session goes quiet."""

    def __init__(self) -> None:
        self.active = 0
        self.responses = 0
        self.last_event = time.monotonic()
        self.first_output_at: float | None = None
        self.segments: list[str] = []

    def observe(self, event: RealtimeSessionEvent) -> None:
        self.last_event = time.monotonic()
        if event.type == "agent_start":
            self.active += 1
            self.responses += 1
            self.segments.append("")
        elif event.type == "agent_end":
            self.active = max(0, self.active - 1)
        elif event.type == "raw_model_event":
            data = event.data
            if getattr(data, "type", None) != "raw_server_event" or not isinstance(data.data, dict):
                return
            if data.data.get("type") in OUTPUT_DELTAS:
                if self.first_output_at is None:
                    self.first_output_at = time.perf_counter()
                if not self.segments:
                    self.segments.append("")
                self.segments[-1] += data.data.get("delta") or ""

    async def wait_for_turn(self, responses_before: int) -> None:
        async with asyncio.timeout(TURN_TIMEOUT_S):
            while True:
                await asyncio.sleep(0.1)
                idle = time.monotonic() - self.last_event
                if self.responses > responses_before and self.active == 0 and idle > QUIET_S:
                    return

    @property
    def reply(self) -> str:
        return " ".join(s.strip() for s in self.segments if s.strip())


def _summarize(case: Case, mode: Mode, ctx: PresentationContext, sock: CaptureSocket) -> CaseRun:
    run = CaseRun(case_id=case.id, mode=mode, final_slide=ctx.current_index + 1)
    for m in sock.messages:
        if m["type"] == "error":
            run.errors.append(m["message"])
        elif m["type"] == "metrics" and run.latency_ms is None:
            run.latency_ms = m["response_latency_ms"]
        elif m["type"] != "activity":
            continue
        elif m["kind"] == "tool" and m.get("ref") and m.get("status") == "done":
            continue  # completion update for a tool call already counted at its start
        elif m["kind"] == "tool":
            label = m["label"]
            run.tools.append("auto_navigate" if label == "Auto-navigate" else label.split(": ")[-1])
        elif m["kind"] == "handoff":
            run.handoffs.append(m["label"])
        elif m["label"].startswith("Input blocked"):
            run.input_blocked = True
        elif m["label"].startswith("Guardrail tripped: "):
            run.guardrails += m["label"].removeprefix("Guardrail tripped: ").split(", ")
    return run


async def run_case(case: Case, mode: Mode, settings: Settings, *, audio: bool) -> CaseRun:
    deck = builtin_deck()
    ctx = PresentationContext(deck=deck)
    ctx.move_to(case.start_slide - 1)
    sock = CaptureSocket()
    bridge = PresenterBridge(sock, ctx, settings)  # type: ignore[arg-type]
    agent = build_agents(deck, mode, grounding=settings.grounding_guardrail)
    config = build_model_config(settings)
    if not audio:
        config["initial_model_settings"] = {
            **config["initial_model_settings"],
            "output_modalities": ["text"],
        }

    watcher = TurnWatcher()
    errors: list[str] = []
    latencies: list[int] = []
    session = await build_runner(agent, settings).run(context=ctx, model_config=config)
    async with session:
        await bridge.attach(session)

        async def pump() -> None:
            async for event in session:
                watcher.observe(event)
                await bridge.handle_event(event)

        pump_task = asyncio.create_task(pump())
        try:
            for turn in case.turns:
                before = watcher.responses
                watcher.first_output_at = None
                sent = time.perf_counter()
                await bridge.handle_json(json.dumps({"type": "text", "text": turn}))
                await watcher.wait_for_turn(before)
                if watcher.first_output_at is not None:
                    latencies.append(int((watcher.first_output_at - sent) * 1000))
        except TimeoutError:
            errors.append(f"turn timed out after {TURN_TIMEOUT_S:.0f}s")
        finally:
            pump_task.cancel()
            with contextlib.suppress(BaseException):
                await pump_task

    run = _summarize(case, mode, ctx, sock)
    run.reply = watcher.reply
    run.errors += errors
    if latencies:
        run.latency_ms = max(latencies)
    return run


async def run_all(
    cases: list[Case], mode: Mode, settings: Settings, *, audio: bool, concurrency: int
) -> list[tuple[Case, CaseRun, list[str]]]:
    deck = builtin_deck()
    gate = asyncio.Semaphore(concurrency)

    async def one(case: Case) -> tuple[Case, CaseRun, list[str]]:
        async with gate:
            try:
                run = await run_case(case, mode, settings, audio=audio)
            except Exception as exc:
                run = CaseRun(case_id=case.id, mode=mode, final_slide=0)
                run.errors.append(f"{type(exc).__name__}: {exc}")
            failures = score(case, run, deck)
            mark = "PASS" if not failures else "FAIL"
            latency = f"{run.latency_ms} ms" if run.latency_ms is not None else "-"
            print(f"  {mark}  {case.id:<26} {case.category:<13} {latency:>8}", flush=True)
            for f in failures:
                print(f"          - {f}", flush=True)
            return case, run, failures

    return await asyncio.gather(*(one(c) for c in cases))


def _report(results: list[tuple[Case, CaseRun, list[str]]]) -> float:
    by_category: dict[str, list[bool]] = {}
    for case, _, failures in results:
        by_category.setdefault(case.category, []).append(not failures)
    print("\n  category       passed")
    for category, outcomes in sorted(by_category.items()):
        print(f"  {category:<13} {sum(outcomes):>3}/{len(outcomes)}")
    passed = sum(not f for _, _, f in results)
    rate = passed / len(results) if results else 0.0
    latencies = sorted(r.latency_ms for _, r, _ in results if r.latency_ms is not None)
    p50 = f"{latencies[len(latencies) // 2]} ms" if latencies else "-"
    print(f"\n  total {passed}/{len(results)} passed ({rate:.0%}), median first-output {p50}")
    return rate


def _save(results: list[tuple[Case, CaseRun, list[str]]], mode: Mode, audio: bool) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}-{mode}{'-audio' if audio else ''}.json"
    payload = [
        {**asdict(run), "category": case.category, "passed": not failures, "failures": failures}
        for case, run, failures in results
    ]
    path.write_text(json.dumps(payload, indent=2))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=["multi", "single"], help="default: AGENT_MODE")
    parser.add_argument("--case", action="append", default=[], help="case id prefix (repeatable)")
    parser.add_argument("--category", action="append", default=[], help="category (repeatable)")
    parser.add_argument("--audio", action="store_true", help="audio output (slower, prod-like)")
    parser.add_argument("--repeat", type=int, default=1, help="run each case N times")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--min-pass", type=float, default=0.9, help="required pass rate (0-1)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR)
    settings = get_settings()
    missing = settings.missing_credentials()
    if missing:
        print(f"[eval] provider={settings.provider} is not configured; missing: {missing}")
        return 2

    mode: Mode = args.mode or settings.agent_mode
    cases = [
        c
        for c in load_cases()
        if mode in c.modes
        and (not args.case or any(c.id.startswith(p) for p in args.case))
        and (not args.category or c.category in args.category)
    ] * max(1, args.repeat)
    if not cases:
        print("[eval] no cases selected")
        return 1

    output = "audio" if args.audio else "text"
    print(f"[eval] provider={settings.provider} mode={mode} output={output} cases={len(cases)}\n")
    results = asyncio.run(
        run_all(cases, mode, settings, audio=args.audio, concurrency=args.concurrency)
    )
    rate = _report(results)
    print(f"  results saved to {os.path.relpath(_save(results, mode, args.audio))}")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())

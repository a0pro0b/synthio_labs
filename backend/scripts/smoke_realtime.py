"""Connectivity check: open a realtime session, send text, and wait for the first audio event.

Usage (from backend/): uv run python scripts/smoke_realtime.py   (or `make smoke`)
Exit codes: 0 = audio received, 1 = failed/timed out, 2 = provider not configured.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.realtime import RealtimeAgent  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.realtime_factory import (  # noqa: E402
    azure_realtime_url,
    build_model_config,
    build_runner,
)

TIMEOUT_S = 30


async def main() -> int:
    s = get_settings()
    missing = s.missing_credentials()
    if missing:
        print(f"[smoke] provider={s.provider} is not configured; missing: {', '.join(missing)}")
        print("[smoke] copy .env.example to .env and fill in the keys.")
        return 2

    target = azure_realtime_url(s) if s.provider == "azure" else s.openai_realtime_model
    print(f"[smoke] provider={s.provider} target={target}")

    agent = RealtimeAgent(name="Smoke", instructions="Reply in one short sentence.")
    runner = build_runner(agent, s)
    started = time.perf_counter()
    session = await runner.run(model_config=build_model_config(s))
    async with session:
        print(f"[smoke] connected in {(time.perf_counter() - started) * 1000:.0f} ms")
        sent = time.perf_counter()
        await session.send_message("Say hello in five words.")
        audio_bytes = 0
        try:
            async with asyncio.timeout(TIMEOUT_S):
                async for event in session:
                    if event.type == "error":
                        print(f"[smoke] error event: {event.error}")
                        return 1
                    if event.type == "audio":
                        if audio_bytes == 0:
                            ms = (time.perf_counter() - sent) * 1000
                            print(f"[smoke] first audio after {ms:.0f} ms")
                        audio_bytes += len(event.audio.data)
                    if event.type == "audio_end" and audio_bytes:
                        print(f"[smoke] OK: received {audio_bytes} bytes of PCM16 audio")
                        return 0
        except TimeoutError:
            pass
    if audio_bytes:
        print(f"[smoke] OK (partial): received {audio_bytes} bytes before timeout")
        return 0
    print(f"[smoke] FAILED: no audio within {TIMEOUT_S}s")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # surface connection errors as a clear one-liner
        print(f"[smoke] FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)

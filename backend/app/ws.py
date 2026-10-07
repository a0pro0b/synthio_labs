"""WebSocket session handler: browser <-> FastAPI <-> Agents SDK realtime session.

Binary frames are PCM16 audio in both directions; text frames are JSON messages defined in
app/protocol.py.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any, Literal
from urllib.parse import urlparse

from agents.realtime import RealtimeSession, RealtimeSessionEvent
from agents.realtime.model_inputs import RealtimeModelSendInterrupt, RealtimeModelSendRawMessage
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.agents.context import PresentationContext
from app.agents.guardrails import find_deck_injection, find_prompt_injection, numbers_in
from app.agents.presenter import build_agents
from app.agents.prompts import (
    BLOCKED_INPUT_PREFIX,
    auto_navigated_message,
    blocked_input_message,
    user_navigated_message,
)
from app.agents.tools import NAV_TOOL_NAMES
from app.config import Settings, get_settings
from app.decks.builtin import BUILTIN_DECK_ID
from app.decks.registry import DeckRegistry
from app.decks.search import confident_slide
from app.live_evals import evaluate_reply, summarize
from app.protocol import (
    Activity,
    AudioEnd,
    AudioInterrupted,
    AudioStart,
    BeginMessage,
    Error,
    InterruptMessage,
    Metrics,
    NavigateMessage,
    SessionReady,
    SlideChanged,
    SlideChangeReason,
    Status,
    TextMessage,
    Transcript,
    TranscriptItem,
    client_message_adapter,
)
from app.realtime_factory import build_model_config, build_runner

log = logging.getLogger(__name__)

NAV_MESSAGE_PREFIX = "[User moved to slide"
HIDDEN_USER_PREFIXES = (NAV_MESSAGE_PREFIX, BLOCKED_INPUT_PREFIX)
MAX_TRANSCRIPT_ITEMS = 60
MAX_ACTIVITY_DETAIL = 300
FAILED_TRANSCRIPT_TEXT = "(voice message - transcription unavailable)"
OUTPUT_DELTAS = frozenset({"response.output_text.delta", "response.output_audio_transcript.delta"})


def origin_allowed(origin: str | None, host: str | None, allowed: list[str]) -> bool:
    if not origin or not allowed:
        return True
    if host and urlparse(origin).netloc == host:
        return True
    return origin.rstrip("/") in {a.rstrip("/") for a in allowed}


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        inner = error.get("error", error)
        if isinstance(inner, dict):
            return str(inner.get("message") or inner)
        return str(inner)
    message = getattr(error, "message", None)
    if message:
        return str(message)
    inner = getattr(error, "error", None)
    if inner is not None and inner is not error:
        return _error_text(inner)
    return str(error)


class TranscriptTracker:
    """Simplified user/assistant transcript built from SDK history plus live transcript deltas."""

    def __init__(self) -> None:
        self._order: list[str] = []
        self._items: dict[str, TranscriptItem] = {}
        self._failed: set[str] = set()

    @staticmethod
    def _item_text(item: Any) -> tuple[str, bool]:
        parts: list[str] = []
        has_pending_audio = False
        for c in getattr(item, "content", []) or []:
            ctype = getattr(c, "type", None)
            if ctype in ("input_text", "text"):
                parts.append(getattr(c, "text", None) or "")
            elif ctype in ("input_audio", "audio"):
                transcript = getattr(c, "transcript", None)
                if transcript is None:
                    has_pending_audio = True
                parts.append(transcript or "")
        return " ".join(p for p in parts if p).strip(), has_pending_audio

    def _convert(self, item: Any) -> TranscriptItem | None:
        if getattr(item, "type", None) != "message":
            return None
        role = getattr(item, "role", None)
        if role not in ("user", "assistant"):
            return None
        text, pending = self._item_text(item)
        if role == "user" and text.startswith(HIDDEN_USER_PREFIXES):
            return None
        prev = self._items.get(item.item_id)
        if not text and prev:
            text = prev.text
        if role == "assistant":
            final = getattr(item, "status", None) in ("completed", "incomplete")
        elif item.item_id in self._failed:
            text = text or FAILED_TRANSCRIPT_TEXT
            final = True
        else:
            final = not pending
        if not text and final:
            return None
        return TranscriptItem(id=item.item_id, role=role, text=text, final=final)

    def apply_history(self, history: list[Any]) -> None:
        converted = [t for t in (self._convert(i) for i in history) if t is not None]
        self._order = [t.id for t in converted]
        self._items = {t.id: t for t in converted}

    def apply_history_item(self, item: Any) -> None:
        converted = self._convert(item)
        if converted is None:
            return
        if converted.id not in self._items:
            self._order.append(converted.id)
        self._items[converted.id] = converted

    def apply_delta(
        self, item_id: str, delta: str, role: Literal["user", "assistant"] = "assistant"
    ) -> None:
        item = self._items.get(item_id)
        if item is None:
            item = TranscriptItem(id=item_id, role=role, text="", final=False)
            self._order.append(item_id)
        self._items[item_id] = item.model_copy(update={"text": item.text + delta})

    def mark_failed(self, item_id: str) -> None:
        self._failed.add(item_id)
        item = self._items.get(item_id)
        if item is None:
            item = TranscriptItem(id=item_id, role="user", text="", final=True)
            self._order.append(item_id)
        self._items[item_id] = item.model_copy(
            update={"text": item.text or FAILED_TRANSCRIPT_TEXT, "final": True}
        )

    def snapshot(self) -> Transcript:
        ids = self._order[-MAX_TRANSCRIPT_ITEMS:]
        return Transcript(items=[self._items[i] for i in ids])


class PresenterBridge:
    """Owns one browser connection and one realtime session."""

    def __init__(
        self, websocket: WebSocket, ctx: PresentationContext, settings: Settings | None = None
    ) -> None:
        self.ws = websocket
        self.ctx = ctx
        self.settings = settings or get_settings()
        self._transcription_error_reported = False
        self.session: RealtimeSession | None = None
        self.transcript = TranscriptTracker()
        self._send_lock = asyncio.Lock()
        self._begun = False
        self._last_sent_index: int | None = None
        self._turn_started_at: float | None = None
        self._speaking = False
        self._agent_navigated = False
        self._audio_item_id: str | None = None
        self._activity_seq = 0
        # Tool events carry no call id, so starts and ends are paired FIFO per (agent, tool).
        self._open_tools: dict[tuple[str, str], list[str]] = {}
        self._seen_agents: set[str] = set()
        self._response_ref: str | None = None
        self._response_started_at = 0.0
        self._response_text = ""
        self._response_latency_ms: int | None = None
        self._response_tripped: set[str] = set()

    async def attach(self, session: RealtimeSession) -> None:
        self.session = session
        self._last_sent_index = self.ctx.current_index
        await self.send(SessionReady(deck=self.ctx.deck, current_index=self.ctx.current_index))
        flagged = find_deck_injection(self.ctx.deck)
        if flagged:
            slide_number, snippet = flagged
            log.warning("Deck %s slide %d: %r", self.ctx.deck.deck_id, slide_number, snippet)
            await self.send(
                Activity(
                    kind="guardrail",
                    label="Deck content flagged: prompt_injection",
                    detail=f"Slide {slide_number}: {snippet}"[:MAX_ACTIVITY_DETAIL],
                    status="fail",
                )
            )
        else:
            await self.send(
                Activity(
                    kind="guardrail",
                    label="Deck scan passed: prompt_injection",
                    detail=f"{self.ctx.slide_count} slides checked",
                    status="pass",
                )
            )

    def _next_ref(self, prefix: str) -> str:
        self._activity_seq += 1
        return f"{prefix}-{self._activity_seq}"

    # ------------------------------------------------------------ sending

    async def send(self, msg: BaseModel) -> None:
        async with self._send_lock:
            await self.ws.send_text(msg.model_dump_json())

    async def send_audio(self, data: bytes) -> None:
        async with self._send_lock:
            await self.ws.send_bytes(data)

    async def send_slide(self, reason: SlideChangeReason) -> None:
        index = self.ctx.current_index
        if reason == "agent" and index == self._last_sent_index:
            return
        self._last_sent_index = index
        await self.send(SlideChanged(index=index, reason=reason))

    def _start_turn_timer(self) -> None:
        self._turn_started_at = time.perf_counter()
        self._speaking = False
        self._agent_navigated = False

    async def auto_navigate(self, utterance: str) -> None:
        """Show the slide a question is clearly about, unless the agent already navigated.

        The model does not always call a navigation tool for topic questions, so this keeps the
        screen in sync deterministically. The agent can still override it with its own tools.
        """
        assert self.session is not None
        if self._agent_navigated:
            return
        slide = confident_slide(self.ctx.deck, utterance)
        if slide is None or slide.index == self.ctx.current_index:
            return
        self.ctx.move_to(slide.index)
        await self.send_slide("agent")
        await self.send(
            Activity(
                kind="tool",
                label="Auto-navigate",
                detail=f"Slide {slide.index + 1}: {slide.title} (matched the question)",
                status="done",
            )
        )
        await self._send_system_note(auto_navigated_message(slide.index + 1, slide.title))

    async def _send_system_note(self, note: str) -> None:
        assert self.session is not None
        await self.session.model.send_event(
            RealtimeModelSendRawMessage(
                message={
                    "type": "conversation.item.create",
                    "other_data": {
                        "item": {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": note}],
                        }
                    },
                }
            )
        )

    async def report_blocked_input(self, snippet: str) -> None:
        await self.send(
            Activity(
                kind="guardrail",
                label="Input blocked: prompt_injection",
                detail=snippet[:MAX_ACTIVITY_DETAIL],
                status="fail",
            )
        )

    async def report_input_passed(self, text: str, source: Literal["typed", "spoken"]) -> None:
        await self.send(
            Activity(
                kind="guardrail",
                label="Input check passed: prompt_injection",
                detail=f"{source}: {text}"[:MAX_ACTIVITY_DETAIL],
                status="pass",
            )
        )

    async def block_spoken_input(self, snippet: str) -> None:
        """The audio already reached the model, so cancel its reply and steer the next one."""
        assert self.session is not None
        await self.hard_interrupt()
        await self.report_blocked_input(snippet)
        self._start_turn_timer()
        await self._send_system_note(blocked_input_message())
        await self.session.model.send_event(
            RealtimeModelSendRawMessage(message={"type": "response.create"})
        )

    # ------------------------------------------------------------ browser -> model

    async def hard_interrupt(self) -> None:
        # With semantic_vad interrupt_response=True, session.interrupt() only truncates playback;
        # forcing response.cancel is what actually stops generation for manual interrupts.
        assert self.session is not None
        await self.session.model.send_event(RealtimeModelSendInterrupt(force_response_cancel=True))
        self._speaking = False

    async def receive_loop(self) -> None:
        assert self.session is not None
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data:
                await self.session.send_audio(data)
                continue
            text = message.get("text")
            if text:
                await self.handle_json(text)

    async def handle_json(self, raw: str) -> None:
        assert self.session is not None
        try:
            msg = client_message_adapter.validate_json(raw)
        except ValidationError:
            await self.send(Error(message="Invalid message."))
            return

        if isinstance(msg, BeginMessage):
            if self._begun:
                return
            self._begun = True
            self._start_turn_timer()
            await self.session.model.send_event(
                RealtimeModelSendRawMessage(message={"type": "response.create"})
            )
        elif isinstance(msg, InterruptMessage):
            await self.hard_interrupt()
            await self.send(Status(state="listening"))
        elif isinstance(msg, TextMessage):
            await self.hard_interrupt()
            self._start_turn_timer()
            await self.send(Status(state="thinking"))
            injection = find_prompt_injection(msg.text)
            if injection:
                await self.report_blocked_input(injection)
                await self.session.send_message(blocked_input_message())
                return
            await self.report_input_passed(msg.text, "typed")
            self.ctx.user_numbers |= numbers_in(msg.text)
            await self.auto_navigate(msg.text)
            await self.session.send_message(msg.text)
        elif isinstance(msg, NavigateMessage):
            if not self.ctx.move_to(msg.index):
                await self.send(Error(message=f"Slide {msg.index + 1} does not exist."))
                return
            await self.hard_interrupt()
            await self.send_slide("user")
            slide = self.ctx.current_slide
            self._start_turn_timer()
            await self.session.send_message(user_navigated_message(slide.index + 1, slide.title))

    # ------------------------------------------------------------ model -> browser

    @staticmethod
    def _agent_profile(agent: Any) -> str:
        tools = [t.name for t in getattr(agent, "tools", []) or []]
        guardrails = [g.get_name() for g in getattr(agent, "output_guardrails", []) or []]
        handoffs = [
            getattr(h, "agent_name", None) or getattr(h, "name", "?")
            for h in getattr(agent, "handoffs", []) or []
        ]
        parts = [
            f"tools: {', '.join(tools) or 'none'}",
            f"guardrails: {', '.join(guardrails) or 'none'}",
        ]
        if handoffs:
            parts.append(f"handoffs: {', '.join(handoffs)}")
        return " · ".join(parts)

    async def start_response(self, agent: Any) -> None:
        self._response_ref = self._next_ref("agent")
        self._response_started_at = time.perf_counter()
        self._response_text = ""
        self._response_latency_ms = None
        self._response_tripped = set()
        first_seen = agent.name not in self._seen_agents
        self._seen_agents.add(agent.name)
        await self.send(
            Activity(
                kind="agent",
                label=f"{agent.name} responding",
                detail=self._agent_profile(agent) if first_seen else "",
                status="running",
                ref=self._response_ref,
            )
        )

    async def end_response(self, agent: Any) -> None:
        if self._response_ref is None:
            return
        ref, self._response_ref = self._response_ref, None
        seconds = time.perf_counter() - self._response_started_at
        reply = self._response_text.strip()
        await self.send(
            Activity(
                kind="agent",
                label=f"{agent.name} {'replied' if reply else 'finished'} in {seconds:.1f}s",
                status="done",
                ref=ref,
                result=reply[:MAX_ACTIVITY_DETAIL],
            )
        )
        if not reply:
            # Tool-only responses are followed by a spoken one; that one gets scored.
            return

        guardrails = [g.get_name() for g in getattr(agent, "output_guardrails", []) or []]
        passed = [g for g in guardrails if g not in self._response_tripped]
        if passed:
            await self.send(
                Activity(
                    kind="guardrail",
                    label=f"Output guardrails passed: {', '.join(passed)}",
                    detail=f"{agent.name} reply, {len(reply)} chars",
                    status="pass",
                )
            )

        checks = evaluate_reply(
            reply, self.ctx.deck, self.ctx.user_numbers, self._response_latency_ms
        )
        ok = sum(c.passed for c in checks)
        await self.send(
            Activity(
                kind="eval",
                label=f"Reply eval: {ok}/{len(checks)} checks passed",
                detail=summarize(checks)[:MAX_ACTIVITY_DETAIL],
                status="pass" if ok == len(checks) else "fail",
            )
        )

    async def pump_events(self) -> None:
        assert self.session is not None
        try:
            async for event in self.session:
                await self.handle_event(event)
        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            return
        except Exception as exc:
            log.exception("Realtime session failed")
            with contextlib.suppress(Exception):
                await self.send(Error(message=f"Realtime session error: {_error_text(exc)}"))
            with contextlib.suppress(Exception):
                await self.ws.close(code=1011)

    async def handle_event(self, event: RealtimeSessionEvent) -> None:
        etype = event.type
        if etype == "audio":
            if not self._speaking:
                self._speaking = True
                if self._turn_started_at is not None:
                    latency = int((time.perf_counter() - self._turn_started_at) * 1000)
                    self._turn_started_at = None
                    self._response_latency_ms = latency
                    await self.send(Metrics(response_latency_ms=latency))
                await self.send(Status(state="speaking"))
            if event.item_id != self._audio_item_id:
                self._audio_item_id = event.item_id
                await self.send(AudioStart(item_id=event.item_id))
            await self.send_audio(event.audio.data)
        elif etype == "audio_interrupted":
            self._speaking = False
            self._audio_item_id = None
            await self.send(AudioInterrupted())
        elif etype == "audio_end":
            self._speaking = False
            self._audio_item_id = None
            await self.send(AudioEnd(item_id=event.item_id))
        elif etype == "agent_start":
            await self.start_response(event.agent)
        elif etype == "agent_end":
            await self.end_response(event.agent)
        elif etype == "tool_start":
            ref = self._next_ref("tool")
            self._open_tools.setdefault((event.agent.name, event.tool.name), []).append(ref)
            await self.send(
                Activity(
                    kind="tool",
                    label=f"{event.agent.name}: {event.tool.name}",
                    detail=(event.arguments or "")[:MAX_ACTIVITY_DETAIL],
                    status="running",
                    ref=ref,
                )
            )
        elif etype == "tool_end":
            if event.tool.name in NAV_TOOL_NAMES:
                self._agent_navigated = True
                await self.send_slide("agent")
            pending = self._open_tools.get((event.agent.name, event.tool.name))
            if pending:
                await self.send(
                    Activity(
                        kind="tool",
                        label=f"{event.agent.name}: {event.tool.name}",
                        detail=(event.arguments or "")[:MAX_ACTIVITY_DETAIL],
                        status="done",
                        ref=pending.pop(0),
                        result=str(event.output)[:MAX_ACTIVITY_DETAIL],
                    )
                )
        elif etype == "handoff":
            await self.send(
                Activity(
                    kind="handoff",
                    label=f"{event.from_agent.name} -> {event.to_agent.name}",
                )
            )
        elif etype == "guardrail_tripped":
            self._response_tripped |= {r.guardrail.get_name() for r in event.guardrail_results}
            names = ", ".join(r.guardrail.get_name() for r in event.guardrail_results)
            matched = [
                (r.output.output_info or {}).get("matched", "")
                for r in event.guardrail_results
                if isinstance(r.output.output_info, dict)
            ]
            await self.send(
                Activity(
                    kind="guardrail",
                    label=f"Guardrail tripped: {names or 'output guardrail'}",
                    detail=("; ".join(m for m in matched if m) or event.message)[
                        :MAX_ACTIVITY_DETAIL
                    ],
                    status="fail",
                )
            )
        elif etype == "history_updated":
            self.transcript.apply_history(event.history)
            await self.send(self.transcript.snapshot())
        elif etype == "history_added":
            self.transcript.apply_history_item(event.item)
            await self.send(self.transcript.snapshot())
        elif etype == "error":
            await self.send(Error(message=_error_text(event.error)))
        elif etype == "raw_model_event":
            await self.handle_raw(event.data)

    async def handle_raw(self, data: Any) -> None:
        dtype = getattr(data, "type", None)
        if dtype == "transcript_delta":
            self.transcript.apply_delta(data.item_id, data.delta)
            await self.send(self.transcript.snapshot())
            return
        if dtype != "raw_server_event" or not isinstance(data.data, dict):
            return
        server_type = data.data.get("type")
        if server_type in OUTPUT_DELTAS:
            self._response_text += data.data.get("delta") or ""
        elif server_type == "input_audio_buffer.speech_started":
            self._speaking = False
            self._turn_started_at = None
            await self.send(Status(state="listening"))
        elif server_type == "input_audio_buffer.speech_stopped":
            self._start_turn_timer()
            await self.send(Status(state="thinking"))
        elif server_type == "conversation.item.input_audio_transcription.delta":
            item_id, delta = data.data.get("item_id"), data.data.get("delta")
            if item_id and delta:
                self.transcript.apply_delta(item_id, delta, role="user")
                await self.send(self.transcript.snapshot())
        elif server_type == "conversation.item.input_audio_transcription.completed":
            transcript = data.data.get("transcript")
            if transcript:
                injection = find_prompt_injection(transcript)
                if injection:
                    await self.block_spoken_input(injection)
                else:
                    await self.report_input_passed(transcript, "spoken")
                    self.ctx.user_numbers |= numbers_in(transcript)
                    await self.auto_navigate(transcript)
        elif server_type == "conversation.item.input_audio_transcription.failed":
            item_id = data.data.get("item_id")
            if item_id:
                self.transcript.mark_failed(item_id)
                await self.send(self.transcript.snapshot())
            error = data.data.get("error") or {}
            log.warning("Input transcription failed: %s", error)
            if not self._transcription_error_reported:
                self._transcription_error_reported = True
                code = error.get("code") if isinstance(error, dict) else None
                hint = (
                    f" No deployment named '{self.settings.transcribe_model}' exists; set "
                    "TRANSCRIBE_MODEL in .env to your transcription deployment name."
                    if code == "DeploymentNotFound"
                    else ""
                )
                await self.send(
                    Error(
                        message="Your speech could not be transcribed, so it won't appear in "
                        f"the transcript.{hint}"
                    )
                )


def _resolve_deck(websocket: WebSocket, deck_id: str | None):
    registry: DeckRegistry = websocket.app.state.registry
    return registry.get(deck_id or BUILTIN_DECK_ID)


async def presenter_ws(websocket: WebSocket, deck_id: str | None = None) -> None:
    settings: Settings = get_settings()
    if not origin_allowed(
        websocket.headers.get("origin"), websocket.headers.get("host"), settings.origins
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()

    deck = _resolve_deck(websocket, deck_id)
    if deck is None:
        await websocket.send_text(Error(message="Unknown deck.").model_dump_json())
        await websocket.close(code=1008)
        return
    missing = settings.missing_credentials()
    if missing:
        await websocket.send_text(
            Error(
                message=f"Realtime provider '{settings.provider}' is not configured. "
                f"Set {', '.join(missing)} in .env and restart the backend."
            ).model_dump_json()
        )
        await websocket.close(code=1011)
        return

    ctx = PresentationContext(deck=deck)
    bridge = PresenterBridge(websocket, ctx, settings)
    agent = build_agents(deck, settings.agent_mode, grounding=settings.grounding_guardrail)
    runner = build_runner(agent, settings)
    tasks: list[asyncio.Task[None]] = []
    try:
        session = await runner.run(context=ctx, model_config=build_model_config(settings))
        async with session:
            await bridge.attach(session)
            tasks = [
                asyncio.create_task(bridge.pump_events()),
                asyncio.create_task(bridge.receive_loop()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.exception("WebSocket session failed")
        with contextlib.suppress(Exception):
            await bridge.send(Error(message=f"Session failed: {_error_text(exc)}"))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
        with contextlib.suppress(Exception):
            await websocket.close()

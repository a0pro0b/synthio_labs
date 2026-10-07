"""WebSocket message contracts. Mirrored by frontend/src/lib/protocol.ts.

Besides these JSON messages, both directions carry binary frames of PCM16 audio
(24 kHz, mono, little-endian; the client sends ~40 ms frames).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.decks.models import DeckManifest

# ---------------------------------------------------------------- client -> server


class BeginMessage(BaseModel):
    """Sent once playback is ready; triggers the greeting."""

    type: Literal["begin"] = "begin"


class NavigateMessage(BaseModel):
    type: Literal["navigate"] = "navigate"
    index: int
    """0-based slide index."""


class TextMessage(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=2000)


class InterruptMessage(BaseModel):
    type: Literal["interrupt"] = "interrupt"


ClientMessage = Annotated[
    BeginMessage | NavigateMessage | TextMessage | InterruptMessage,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# ---------------------------------------------------------------- server -> client

ServerState = Literal["listening", "thinking", "speaking"]
SlideChangeReason = Literal["agent", "user"]
ActivityKind = Literal["agent", "tool", "handoff", "guardrail", "eval"]
ActivityStatus = Literal["info", "running", "done", "pass", "fail"]


class SessionReady(BaseModel):
    type: Literal["session_ready"] = "session_ready"
    deck: DeckManifest
    current_index: int


class SlideChanged(BaseModel):
    type: Literal["slide_changed"] = "slide_changed"
    index: int
    """0-based slide index."""
    reason: SlideChangeReason


class AudioInterrupted(BaseModel):
    type: Literal["audio_interrupted"] = "audio_interrupted"


class AudioStart(BaseModel):
    """Binary audio frames after this belong to transcript item `item_id`."""

    type: Literal["audio_start"] = "audio_start"
    item_id: str


class AudioEnd(BaseModel):
    type: Literal["audio_end"] = "audio_end"
    item_id: str | None = None


class Status(BaseModel):
    type: Literal["status"] = "status"
    state: ServerState


class TranscriptItem(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    final: bool


class Transcript(BaseModel):
    type: Literal["transcript"] = "transcript"
    items: list[TranscriptItem]


class Activity(BaseModel):
    type: Literal["activity"] = "activity"
    kind: ActivityKind
    label: str
    detail: str = ""
    status: ActivityStatus = "info"
    ref: str = ""
    """Messages sharing a non-empty ref update one entry in place (e.g. tool start -> end)."""
    result: str = ""


class Metrics(BaseModel):
    type: Literal["metrics"] = "metrics"
    response_latency_ms: int


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str


ServerMessage = Annotated[
    SessionReady
    | SlideChanged
    | AudioInterrupted
    | AudioStart
    | AudioEnd
    | Status
    | Transcript
    | Activity
    | Metrics
    | Error,
    Field(discriminator="type"),
]

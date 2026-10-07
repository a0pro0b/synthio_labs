// Mirrors backend/app/protocol.py and backend/app/decks/models.py.
// Besides these JSON messages, both directions carry binary PCM16 frames
// (24 kHz, mono, little-endian; the client sends ~40 ms frames).

// ---------------------------------------------------------------- deck manifest

export interface Slide {
  index: number;
  title: string;
  bullets: string[];
  text: string;
  notes: string;
  image_url: string | null;
}

export type DeckSource = "builtin" | "pdf" | "pptx";

export interface DeckManifest {
  deck_id: string;
  name: string;
  source: DeckSource;
  slides: Slide[];
}

// ---------------------------------------------------------------- client -> server

export interface BeginMessage {
  type: "begin";
}

export interface NavigateMessage {
  type: "navigate";
  /** 0-based slide index. */
  index: number;
}

export interface TextMessage {
  type: "text";
  text: string;
}

export interface InterruptMessage {
  type: "interrupt";
}

export type ClientMessage = BeginMessage | NavigateMessage | TextMessage | InterruptMessage;

// ---------------------------------------------------------------- server -> client

export type ServerState = "listening" | "thinking" | "speaking";
export type SlideChangeReason = "agent" | "user";
export type ActivityKind = "agent" | "tool" | "handoff" | "guardrail" | "eval";
export type ActivityStatus = "info" | "running" | "done" | "pass" | "fail";

export interface SessionReady {
  type: "session_ready";
  deck: DeckManifest;
  current_index: number;
}

export interface SlideChanged {
  type: "slide_changed";
  /** 0-based slide index. */
  index: number;
  reason: SlideChangeReason;
}

export interface AudioInterrupted {
  type: "audio_interrupted";
}

/** Binary audio frames after this belong to transcript item `item_id`. */
export interface AudioStart {
  type: "audio_start";
  item_id: string;
}

export interface AudioEnd {
  type: "audio_end";
  item_id: string | null;
}

export interface Status {
  type: "status";
  state: ServerState;
}

export interface TranscriptItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  final: boolean;
}

export interface Transcript {
  type: "transcript";
  items: TranscriptItem[];
}

export interface Activity {
  type: "activity";
  kind: ActivityKind;
  label: string;
  detail: string;
  status: ActivityStatus;
  /** Messages sharing a non-empty ref update one entry in place (e.g. tool start -> end). */
  ref: string;
  result: string;
}

export interface Metrics {
  type: "metrics";
  response_latency_ms: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | SessionReady
  | SlideChanged
  | AudioInterrupted
  | AudioStart
  | AudioEnd
  | Status
  | Transcript
  | Activity
  | Metrics
  | ErrorMessage;

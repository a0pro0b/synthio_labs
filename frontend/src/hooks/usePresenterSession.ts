import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { createAudioEngine, type AudioEngine } from "../lib/audio";
import type {
  Activity,
  DeckManifest,
  ServerMessage,
  ServerState,
  TranscriptItem,
} from "../lib/protocol";
import { SpeechClock } from "../lib/speechClock";
import { WsClient, wsUrl } from "../lib/wsClient";

export type SessionStatus = "idle" | "connecting" | ServerState | "ended";

export interface ActivityEntry extends Activity {
  id: number;
  at: number;
  endedAt: number | null;
}

export interface PresenterState {
  status: SessionStatus;
  deck: DeckManifest | null;
  currentIndex: number;
  transcript: TranscriptItem[];
  activity: ActivityEntry[];
  latencyMs: number | null;
  error: string | null;
  muted: boolean;
}

type Action =
  | { type: "select_deck"; deck: DeckManifest | null }
  | { type: "connecting" }
  | { type: "server"; msg: ServerMessage }
  | { type: "playback"; playing: boolean }
  | { type: "local_index"; index: number }
  | { type: "status"; status: SessionStatus }
  | { type: "muted"; muted: boolean }
  | { type: "error"; error: string | null }
  | { type: "ended" };

const MAX_ACTIVITY = 200;
let activitySeq = 0;

const initialState: PresenterState = {
  status: "idle",
  deck: null,
  currentIndex: 0,
  transcript: [],
  activity: [],
  latencyMs: null,
  error: null,
  muted: false,
};

const isLive = (s: SessionStatus) =>
  s === "listening" || s === "thinking" || s === "speaking";

function reducer(state: PresenterState, action: Action): PresenterState {
  switch (action.type) {
    case "select_deck":
      return { ...initialState, deck: action.deck };
    case "connecting":
      return {
        ...state,
        status: "connecting",
        error: null,
        transcript: [],
        activity: [],
        latencyMs: null,
      };
    case "playback":
      if (action.playing && isLive(state.status)) return { ...state, status: "speaking" };
      if (!action.playing && state.status === "speaking") return { ...state, status: "listening" };
      return state;
    case "local_index":
      return { ...state, currentIndex: action.index };
    case "status":
      return { ...state, status: action.status };
    case "muted":
      return { ...state, muted: action.muted };
    case "error":
      return { ...state, error: action.error };
    case "ended":
      return state.status === "idle" ? state : { ...state, status: "ended" };
    case "server":
      return applyServer(state, action.msg);
  }
}

function applyServer(state: PresenterState, msg: ServerMessage): PresenterState {
  switch (msg.type) {
    case "session_ready":
      return { ...state, deck: msg.deck, currentIndex: msg.current_index, status: "listening" };
    case "slide_changed":
      return { ...state, currentIndex: msg.index };
    case "status":
      // "speaking" is confirmed by the player itself; the server only knows audio was sent.
      if (!isLive(state.status)) return state;
      return { ...state, status: msg.state };
    case "audio_interrupted":
      return isLive(state.status) ? { ...state, status: "listening" } : state;
    case "audio_start":
    case "audio_end":
      return state;
    case "transcript":
      return { ...state, transcript: msg.items };
    case "activity": {
      const now = Date.now();
      const existing = msg.ref ? state.activity.findIndex((e) => e.ref === msg.ref) : -1;
      if (existing >= 0) {
        const prev = state.activity[existing];
        const updated: ActivityEntry = {
          ...prev,
          ...msg,
          detail: msg.detail || prev.detail,
          endedAt: msg.status === "running" ? null : now,
        };
        const activity = state.activity.slice();
        activity[existing] = updated;
        return { ...state, activity };
      }
      const entry: ActivityEntry = {
        ...msg,
        id: ++activitySeq,
        at: now,
        endedAt: msg.status === "running" ? null : now,
      };
      return { ...state, activity: [...state.activity, entry].slice(-MAX_ACTIVITY) };
    }
    case "metrics":
      return { ...state, latencyMs: msg.response_latency_ms };
    case "error":
      return { ...state, error: msg.message };
  }
}

export function usePresenterSession() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const clientRef = useRef<WsClient | null>(null);
  const engineRef = useRef<AudioEngine | null>(null);
  const readyRef = useRef(false);
  const audioItemRef = useRef<string | null>(null);
  const [speechClock] = useState(() => new SpeechClock());
  const clockRef = useRef(speechClock);
  const stateRef = useRef(state);
  stateRef.current = state;

  const teardown = useCallback(() => {
    readyRef.current = false;
    clientRef.current?.close();
    clientRef.current = null;
    const engine = engineRef.current;
    engineRef.current = null;
    void engine?.close();
  }, []);

  useEffect(() => teardown, [teardown]);

  const selectDeck = useCallback(
    (deck: DeckManifest | null) => {
      teardown();
      dispatch({ type: "select_deck", deck });
    },
    [teardown],
  );

  const start = useCallback(async () => {
    const deck = stateRef.current.deck;
    if (!deck || clientRef.current) return;
    dispatch({ type: "connecting" });
    clockRef.current.reset();
    audioItemRef.current = null;

    let engine: AudioEngine;
    try {
      engine = await createAudioEngine({
        onMicFrame: (frame) => {
          if (readyRef.current) clientRef.current?.sendAudio(frame);
        },
        onPlaybackChange: (playing) => dispatch({ type: "playback", playing }),
        onPlaybackProgress: (itemId, played) => clockRef.current.played(itemId, played),
      });
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow mic access and try again."
          : `Could not start audio: ${err instanceof Error ? err.message : String(err)}`;
      dispatch({ type: "error", error: message });
      dispatch({ type: "status", status: "idle" });
      return;
    }
    engine.setMuted(stateRef.current.muted);
    engineRef.current = engine;

    let sawError = false;
    const client = new WsClient({
      onMessage: (msg) => {
        if (msg.type === "session_ready") {
          readyRef.current = true;
          client.send({ type: "begin" });
        } else if (msg.type === "audio_interrupted") {
          engineRef.current?.flush();
          audioItemRef.current = null;
        } else if (msg.type === "audio_start") {
          audioItemRef.current = msg.item_id;
        } else if (msg.type === "audio_end") {
          if (msg.item_id) clockRef.current.audioDone(msg.item_id);
          audioItemRef.current = null;
        } else if (msg.type === "error") {
          sawError = true;
        }
        dispatch({ type: "server", msg });
      },
      onAudio: (chunk) => {
        const engine = engineRef.current;
        if (!engine) return;
        const itemId = audioItemRef.current;
        if (itemId) clockRef.current.received(itemId, chunk.byteLength >> 1);
        engine.play(chunk, itemId);
      },
      onClose: (event) => {
        if (clientRef.current !== client) return;
        teardown();
        if (event.code !== 1000 && !sawError) {
          dispatch({ type: "error", error: "Connection to the presenter was lost." });
        }
        dispatch({ type: "ended" });
      },
      onError: () => {
        if (!sawError) {
          sawError = true;
          dispatch({ type: "error", error: "Could not connect to the backend." });
        }
      },
    });
    clientRef.current = client;
    client.connect(wsUrl(deck.deck_id));
  }, [teardown]);

  const stop = useCallback(() => {
    engineRef.current?.flush();
    teardown();
    dispatch({ type: "ended" });
  }, [teardown]);

  const navigate = useCallback((index: number) => {
    const { deck, currentIndex } = stateRef.current;
    if (!deck || index < 0 || index >= deck.slides.length || index === currentIndex) return;
    const client = clientRef.current;
    if (client && readyRef.current) {
      // The backend owns slide state: flush local audio now, render on slide_changed.
      engineRef.current?.flush();
      client.send({ type: "navigate", index });
    } else {
      dispatch({ type: "local_index", index });
    }
  }, []);

  const sendText = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed || !readyRef.current) return;
    engineRef.current?.flush();
    clientRef.current?.send({ type: "text", text: trimmed });
  }, []);

  const interrupt = useCallback(() => {
    if (!readyRef.current) return;
    engineRef.current?.flush();
    clientRef.current?.send({ type: "interrupt" });
  }, []);

  const toggleMute = useCallback(() => {
    const muted = !stateRef.current.muted;
    engineRef.current?.setMuted(muted);
    dispatch({ type: "muted", muted });
  }, []);

  const clearError = useCallback(() => dispatch({ type: "error", error: null }), []);

  return {
    state,
    speechClock,
    selectDeck,
    start,
    stop,
    navigate,
    sendText,
    interrupt,
    toggleMute,
    clearError,
  };
}

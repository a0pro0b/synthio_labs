import type { SessionStatus } from "../hooks/usePresenterSession";
import styles from "./Controls.module.css";

interface Props {
  status: SessionStatus;
  muted: boolean;
  latencyMs: number | null;
  onStart: () => void;
  onStop: () => void;
  onToggleMute: () => void;
  onInterrupt: () => void;
}

const STATUS_LABEL: Record<SessionStatus, string> = {
  idle: "Ready",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
  ended: "Session ended",
};

export default function Controls({
  status,
  muted,
  latencyMs,
  onStart,
  onStop,
  onToggleMute,
  onInterrupt,
}: Props) {
  const live = status === "listening" || status === "thinking" || status === "speaking";
  const busy = status === "connecting";

  return (
    <div className={styles.controls}>
      {live || busy ? (
        <button className={styles.stop} onClick={onStop}>
          ■ Stop
        </button>
      ) : (
        <button className={styles.start} onClick={onStart}>
          ● {status === "ended" ? "Restart" : "Start"}
        </button>
      )}

      <button
        className={muted ? styles.muted : styles.secondary}
        onClick={onToggleMute}
        disabled={!live}
        aria-pressed={muted}
        title="Toggle microphone (Space)"
      >
        {muted ? "Unmute" : "Mute"}
      </button>

      <button
        className={styles.secondary}
        onClick={onInterrupt}
        disabled={status !== "speaking" && status !== "thinking"}
        title="Stop the presenter talking"
      >
        Interrupt
      </button>

      <span className={`${styles.chip} ${styles[status]}`} aria-live="polite">
        <span className={styles.dot} />
        {muted && live ? "Muted" : STATUS_LABEL[status]}
      </span>

      <span className={styles.latency} title="Time from end of your speech to first audio">
        {latencyMs === null ? "Latency —" : `Latency ${latencyMs} ms`}
      </span>
    </div>
  );
}

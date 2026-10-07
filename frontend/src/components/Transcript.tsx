import { useEffect, useRef, useSyncExternalStore } from "react";

import type { SessionStatus } from "../hooks/usePresenterSession";
import type { TranscriptItem } from "../lib/protocol";
import { revealText, type SpeechClock } from "../lib/speechClock";
import styles from "./Transcript.module.css";

interface Props {
  items: TranscriptItem[];
  status: SessionStatus;
  speechClock: SpeechClock;
}

function visibleText(item: TranscriptItem, clock: SpeechClock): string {
  if (item.role !== "assistant") return item.text;
  const spoken = clock.spokenLength(item.id, item.text);
  // Text usually arrives before its audio; hold it back until the voice starts.
  if (spoken === null) return item.final ? item.text : "";
  return revealText(item.text, spoken);
}

export default function Transcript({ items, status, speechClock }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const clockVersion = useSyncExternalStore(speechClock.subscribe, speechClock.getVersion);

  useEffect(() => {
    // Scroll only the panel; scrollIntoView would also scroll the page on every delta.
    const panel = listRef.current?.parentElement;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [items, clockVersion]);

  if (items.length === 0) {
    return (
      <div className={styles.empty}>
        {status === "idle" || status === "ended"
          ? "Press Start to begin. The conversation will appear here."
          : "Waiting for the presenter…"}
      </div>
    );
  }

  return (
    <div ref={listRef} className={styles.list}>
      {items.map((item) => {
        const text = visibleText(item, speechClock);
        const complete = item.final && text.length === item.text.length;
        return (
          <div
            key={item.id}
            className={`${styles.item} ${item.role === "user" ? styles.user : styles.assistant}`}
          >
            <div className={styles.role}>{item.role === "user" ? "You" : "Presenter"}</div>
            <div className={`${styles.text} ${complete ? "" : styles.partial}`}>
              {text || "…"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

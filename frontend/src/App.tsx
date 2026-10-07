import { useEffect, useState } from "react";

import styles from "./App.module.css";
import ActivityPanel from "./components/ActivityPanel";
import Controls from "./components/Controls";
import DeckPicker from "./components/DeckPicker";
import SlideStrip from "./components/SlideStrip";
import SlideView from "./components/SlideView";
import TextFallback from "./components/TextFallback";
import Transcript from "./components/Transcript";
import { usePresenterSession } from "./hooks/usePresenterSession";

type Tab = "transcript" | "activity";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export default function App() {
  const session = usePresenterSession();
  const { state, navigate, toggleMute } = session;
  const [tab, setTab] = useState<Tab>("transcript");
  const live = ["connecting", "listening", "thinking", "speaking"].includes(state.status);

  useEffect(() => {
    if (!state.deck) return;
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        navigate(state.currentIndex + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigate(state.currentIndex - 1);
      } else if (e.key === " " && live) {
        e.preventDefault();
        toggleMute();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.deck, state.currentIndex, live, navigate, toggleMute]);

  if (!state.deck) {
    return <DeckPicker onSelect={session.selectDeck} />;
  }

  const deck = state.deck;
  const slide = deck.slides[state.currentIndex];

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden>
            ◉
          </span>
          <div>
            <div className={styles.deckName}>{deck.name}</div>
            <div className={styles.deckMeta}>
              {deck.slides.length} slides · {deck.source.toUpperCase()}
            </div>
          </div>
        </div>
        <button className={styles.ghost} onClick={() => session.selectDeck(null)}>
          ← Change deck
        </button>
      </header>

      {state.error && (
        <div className={styles.error} role="alert">
          <span>{state.error}</span>
          <button onClick={session.clearError} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      <main className={styles.main}>
        <section className={styles.stage}>
          <SlideView
            deck={deck}
            slide={slide}
            total={deck.slides.length}
            speaking={state.status === "speaking"}
          />
          <SlideStrip deck={deck} currentIndex={state.currentIndex} onSelect={navigate} />
        </section>

        <aside className={styles.side}>
          <div className={styles.tabs} role="tablist">
            <button
              role="tab"
              aria-selected={tab === "transcript"}
              className={tab === "transcript" ? styles.tabActive : styles.tab}
              onClick={() => setTab("transcript")}
            >
              Transcript
            </button>
            <button
              role="tab"
              aria-selected={tab === "activity"}
              className={tab === "activity" ? styles.tabActive : styles.tab}
              onClick={() => setTab("activity")}
            >
              Agent Activity
              {state.activity.length > 0 && (
                <span className={styles.badge}>{state.activity.length}</span>
              )}
            </button>
          </div>
          <div className={styles.panel}>
            {tab === "transcript" ? (
              <Transcript
                items={state.transcript}
                status={state.status}
                speechClock={session.speechClock}
              />
            ) : (
              <ActivityPanel entries={state.activity} />
            )}
          </div>
        </aside>
      </main>

      <footer className={styles.footer}>
        <Controls
          status={state.status}
          muted={state.muted}
          latencyMs={state.latencyMs}
          onStart={session.start}
          onStop={session.stop}
          onToggleMute={toggleMute}
          onInterrupt={session.interrupt}
        />
        <TextFallback
          disabled={!["listening", "thinking", "speaking"].includes(state.status)}
          onSend={session.sendText}
        />
      </footer>
    </div>
  );
}

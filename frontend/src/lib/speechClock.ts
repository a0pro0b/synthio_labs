// Tracks how much of each assistant item's audio has been received and actually played, so the
// transcript can reveal text in step with the voice instead of as fast as the model streams it.

import { SAMPLE_RATE } from "./audio";

/** Typical realtime TTS pace at the default 1.15x speed, until the item's audio length is known. */
const DEFAULT_CHARS_PER_SECOND = 17;

interface Entry {
  receivedSamples: number;
  playedSamples: number;
  audioDone: boolean;
  shown: number;
}

export class SpeechClock {
  private entries = new Map<string, Entry>();
  private listeners = new Set<() => void>();
  private version = 0;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getVersion = (): number => this.version;

  private entry(itemId: string): Entry {
    let e = this.entries.get(itemId);
    if (!e) {
      e = { receivedSamples: 0, playedSamples: 0, audioDone: false, shown: 0 };
      this.entries.set(itemId, e);
    }
    return e;
  }

  private emit(): void {
    this.version++;
    this.listeners.forEach((l) => l());
  }

  received(itemId: string, samples: number): void {
    this.entry(itemId).receivedSamples += samples;
  }

  played(itemId: string, totalPlayedSamples: number): void {
    const e = this.entry(itemId);
    if (totalPlayedSamples <= e.playedSamples) return;
    e.playedSamples = totalPlayedSamples;
    this.emit();
  }

  audioDone(itemId: string): void {
    this.entry(itemId).audioDone = true;
    this.emit();
  }

  reset(): void {
    this.entries.clear();
    this.emit();
  }

  /**
   * How many characters of `text` have been spoken. Returns null when the item has no audio,
   * in which case the caller should show the text as-is.
   */
  spokenLength(itemId: string, text: string): number | null {
    const e = this.entries.get(itemId);
    if (!e) return null;
    if (e.audioDone && e.playedSamples >= e.receivedSamples) {
      e.shown = text.length;
      return text.length;
    }
    const playedSeconds = e.playedSamples / SAMPLE_RATE;
    const charsPerSecond =
      e.audioDone && e.receivedSamples > 0
        ? text.length / (e.receivedSamples / SAMPLE_RATE)
        : DEFAULT_CHARS_PER_SECOND;
    const estimate = Math.min(text.length, Math.floor(playedSeconds * charsPerSecond));
    e.shown = Math.max(e.shown, estimate);
    return e.shown;
  }
}

/** Cut at a word boundary so partially revealed text never ends mid-word. */
export function revealText(text: string, length: number): string {
  if (length >= text.length) return text;
  const cut = text.lastIndexOf(" ", length);
  return cut > 0 ? text.slice(0, cut) : "";
}

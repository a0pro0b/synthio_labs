import { useEffect, useRef } from "react";

import type { DeckManifest } from "../lib/protocol";
import styles from "./SlideStrip.module.css";

interface Props {
  deck: DeckManifest;
  currentIndex: number;
  onSelect: (index: number) => void;
}

export default function SlideStrip({ deck, currentIndex, onSelect }: Props) {
  const stripRef = useRef<HTMLElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Scroll the strip horizontally only; scrollIntoView can also shift the page.
    const strip = stripRef.current;
    const thumb = activeRef.current;
    if (!strip || !thumb) return;
    const left = thumb.offsetLeft - (strip.clientWidth - thumb.offsetWidth) / 2;
    strip.scrollTo({ left, behavior: "smooth" });
  }, [currentIndex]);

  return (
    <nav ref={stripRef} className={styles.strip} aria-label="Slides">
      {deck.slides.map((s) => {
        const active = s.index === currentIndex;
        return (
          <button
            key={s.index}
            ref={active ? activeRef : undefined}
            className={`${styles.thumb} ${active ? styles.active : ""}`}
            onClick={() => onSelect(s.index)}
            aria-current={active ? "true" : undefined}
            title={`${s.index + 1}. ${s.title}`}
          >
            {s.image_url ? (
              <img src={s.image_url} alt="" loading="lazy" />
            ) : (
              <span className={styles.textThumb}>{s.title}</span>
            )}
            <span className={styles.num}>{s.index + 1}</span>
          </button>
        );
      })}
    </nav>
  );
}

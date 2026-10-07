import type { DeckManifest, Slide } from "../lib/protocol";
import styles from "./SlideView.module.css";

interface Props {
  deck: DeckManifest;
  slide: Slide | undefined;
  total: number;
  speaking: boolean;
}

export default function SlideView({ deck, slide, total, speaking }: Props) {
  const isBuiltin = deck.source === "builtin";

  return (
    <div className={styles.wrap}>
      <div className={`${styles.frame} ${speaking ? styles.speaking : ""}`}>
        {slide?.image_url ? (
          <img
            key={slide.image_url}
            className={styles.image}
            src={slide.image_url}
            alt={slide.title}
          />
        ) : slide ? (
          <article
            key={`${deck.deck_id}-${slide.index}`}
            className={`${styles.html} ${isBuiltin ? styles.builtin : ""}`}
          >
            {isBuiltin && <div className={styles.eyebrow}>Synthio Labs</div>}
            <h1 className={slide.index === 0 ? styles.cover : undefined}>{slide.title}</h1>
            {slide.bullets.length > 0 && (
              <ul>
                {slide.bullets.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            )}
          </article>
        ) : null}
        {slide && (
          <div className={styles.counter}>
            {slide.index + 1} / {total}
          </div>
        )}
      </div>
    </div>
  );
}

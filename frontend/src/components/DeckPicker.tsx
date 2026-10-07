import { useCallback, useEffect, useRef, useState } from "react";

import type { DeckManifest } from "../lib/protocol";
import styles from "./DeckPicker.module.css";

const MAX_MB = 25;
const ACCEPT = ".pptx,.pdf";

interface Props {
  onSelect: (deck: DeckManifest) => void;
}

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; progress: number }
  | { phase: "parsing"; name: string }
  | { phase: "error"; message: string };

function uploadDeck(
  file: File,
  onProgress: (fraction: number) => void,
): Promise<{ deck: DeckManifest; warning: string | null }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    xhr.open("POST", "/api/decks");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // fall through to the generic error below
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve({ deck: body as DeckManifest, warning: xhr.getResponseHeader("X-Deck-Warning") });
      } else {
        const detail = (body as { detail?: unknown } | null)?.detail;
        reject(new Error(typeof detail === "string" ? detail : `Upload failed (${xhr.status}).`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error while uploading."));
    xhr.send(form);
  });
}

export default function DeckPicker({ onSelect }: Props) {
  const [decks, setDecks] = useState<DeckManifest[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [warning, setWarning] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/decks")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: DeckManifest[]) => !cancelled && setDecks(data))
      .catch(() => !cancelled && setLoadError("Could not reach the backend. Is it running?"));
    return () => {
      cancelled = true;
    };
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setWarning(null);
      const ext = file.name.toLowerCase().split(".").pop();
      if (ext !== "pptx" && ext !== "pdf") {
        setUpload({ phase: "error", message: "Only .pptx and .pdf files are supported." });
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        setUpload({ phase: "error", message: `File is larger than ${MAX_MB} MB.` });
        return;
      }
      setUpload({ phase: "uploading", name: file.name, progress: 0 });
      try {
        const { deck, warning } = await uploadDeck(file, (progress) =>
          setUpload(
            progress >= 1
              ? { phase: "parsing", name: file.name }
              : { phase: "uploading", name: file.name, progress },
          ),
        );
        setUpload({ phase: "idle" });
        setDecks((prev) => [deck, ...(prev ?? []).filter((d) => d.deck_id !== deck.deck_id)]);
        if (warning) setWarning(warning);
        else onSelect(deck);
      } catch (err) {
        setUpload({ phase: "error", message: err instanceof Error ? err.message : String(err) });
      }
    },
    [onSelect],
  );

  const busy = upload.phase === "uploading" || upload.phase === "parsing";
  const builtin = decks?.find((d) => d.source === "builtin");
  const uploaded = decks?.filter((d) => d.source !== "builtin") ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div className={styles.kicker}>Voice Slide Presenter</div>
        <h1>An AI presenter you can talk to</h1>
        <p>
          Pick a deck and press Start. The agent presents it out loud, jumps to the right slide
          when you ask a question, and stops the moment you interrupt.
        </p>
      </header>

      {loadError && <div className={styles.error}>{loadError}</div>}

      <div className={styles.grid}>
        <button
          className={styles.featured}
          disabled={!builtin}
          onClick={() => builtin && onSelect(builtin)}
        >
          <span className={styles.tag}>Built-in</span>
          <h2>{builtin?.name ?? "Synthio Labs Overview"}</h2>
          <ol>
            {(builtin?.slides ?? []).map((s) => (
              <li key={s.index}>{s.title}</li>
            ))}
          </ol>
          <span className={styles.cta}>Present this deck →</span>
        </button>

        <div
          className={`${styles.dropzone} ${dragging ? styles.dragging : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files[0];
            if (file && !busy) void handleFile(file);
          }}
          onClick={() => !busy && inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && !busy) inputRef.current?.click();
          }}
          aria-label="Upload a PPTX or PDF deck"
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void handleFile(file);
            }}
          />
          <div className={styles.dropIcon} aria-hidden>
            ⇪
          </div>
          <h2>Upload your own deck</h2>
          <p>Drag a .pptx or .pdf here, or click to browse. Up to {MAX_MB} MB, 40 slides.</p>

          {upload.phase === "uploading" && (
            <div className={styles.progress}>
              <div>Uploading {upload.name}…</div>
              <div className={styles.bar}>
                <div style={{ width: `${Math.round(upload.progress * 100)}%` }} />
              </div>
            </div>
          )}
          {upload.phase === "parsing" && (
            <div className={styles.progress}>
              <div>Parsing {upload.name}… rendering slides</div>
              <div className={`${styles.bar} ${styles.indeterminate}`}>
                <div />
              </div>
            </div>
          )}
          {upload.phase === "error" && <div className={styles.error}>{upload.message}</div>}
        </div>
      </div>

      {warning && (
        <div className={styles.warning}>
          {warning} You can still present it below.
        </div>
      )}

      {uploaded.length > 0 && (
        <section className={styles.uploaded}>
          <h3>Your decks</h3>
          <div className={styles.list}>
            {uploaded.map((d) => (
              <button key={d.deck_id} className={styles.deckCard} onClick={() => onSelect(d)}>
                {d.slides[0]?.image_url ? (
                  <img src={d.slides[0].image_url} alt="" loading="lazy" />
                ) : (
                  <div className={styles.textThumb}>{d.slides[0]?.title}</div>
                )}
                <div className={styles.deckInfo}>
                  <strong>{d.name}</strong>
                  <span>
                    {d.slides.length} slides · {d.source.toUpperCase()}
                    {d.slides.every((s) => !s.image_url) ? " · text-only" : ""}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      <footer className={styles.tip}>
        Tip: use headphones so the presenter doesn't hear itself through your speakers.
      </footer>
    </div>
  );
}

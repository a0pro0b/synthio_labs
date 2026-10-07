import { useState, type FormEvent } from "react";

import styles from "./TextFallback.module.css";

interface Props {
  disabled: boolean;
  onSend: (text: string) => void;
}

export default function TextFallback({ disabled, onSend }: Props) {
  const [text, setText] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <input
        className={styles.input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={disabled ? "Start the session to ask a question" : "Type a question instead…"}
        disabled={disabled}
        maxLength={2000}
        aria-label="Typed question"
      />
      <button className={styles.send} type="submit" disabled={disabled || !text.trim()}>
        Send
      </button>
    </form>
  );
}

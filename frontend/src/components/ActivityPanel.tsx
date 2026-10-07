import { useEffect, useMemo, useRef, useState } from "react";

import type { ActivityEntry } from "../hooks/usePresenterSession";
import type { ActivityKind, ActivityStatus } from "../lib/protocol";
import styles from "./ActivityPanel.module.css";

interface Props {
  entries: ActivityEntry[];
}

type Filter = "all" | "agent" | "tool" | "guardrail" | "eval";

const KIND_LABEL: Record<ActivityKind, string> = {
  agent: "Agent",
  tool: "Tool",
  handoff: "Handoff",
  guardrail: "Guardrail",
  eval: "Eval",
};

const STATUS_LABEL: Partial<Record<ActivityStatus, string>> = {
  running: "running",
  done: "done",
  pass: "pass",
  fail: "fail",
};

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "agent", label: "Agents" },
  { id: "tool", label: "Tools" },
  { id: "guardrail", label: "Guardrails" },
  { id: "eval", label: "Evals" },
];

function matches(filter: Filter, kind: ActivityKind): boolean {
  if (filter === "all") return true;
  // Handoffs are agent-to-agent transitions, so they belong with the agents.
  if (filter === "agent") return kind === "agent" || kind === "handoff";
  return kind === filter;
}

function prettyDetail(detail: string): string {
  if (!detail) return "";
  try {
    const parsed: unknown = JSON.parse(detail);
    if (parsed && typeof parsed === "object") {
      const pairs = Object.entries(parsed as Record<string, unknown>);
      return pairs.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
    }
  } catch {
    // not JSON; show as-is
  }
  return detail;
}

function duration(e: ActivityEntry): string {
  if (e.endedAt === null || e.endedAt === e.at) return "";
  const ms = e.endedAt - e.at;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export default function ActivityPanel({ entries }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const visible = useMemo(() => entries.filter((e) => matches(filter, e.kind)), [entries, filter]);
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: entries.length, agent: 0, tool: 0, guardrail: 0, eval: 0 };
    for (const e of entries) {
      for (const f of FILTERS) if (f.id !== "all" && matches(f.id, e.kind)) c[f.id] += 1;
    }
    return c;
  }, [entries]);
  const activeAgent = useMemo(() => {
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i];
      if (e.kind === "agent") return e.status === "running" ? e.label.replace(/ responding$/, "") : null;
    }
    return null;
  }, [entries]);
  const runningTools = entries.filter((e) => e.kind === "tool" && e.status === "running").length;

  useEffect(() => {
    const panel = rootRef.current?.parentElement;
    if (panel) panel.scrollTop = panel.scrollHeight;
  }, [visible]);

  return (
    <div ref={rootRef} className={styles.root}>
      <div className={styles.toolbar}>
        <div className={styles.live}>
          <span className={activeAgent ? styles.dotOn : styles.dotOff} />
          {activeAgent ? (
            <span>
              <strong>{activeAgent}</strong> is responding
              {runningTools > 0 && ` · ${runningTools} tool${runningTools > 1 ? "s" : ""} running`}
            </span>
          ) : (
            <span>Idle</span>
          )}
        </div>
        <div className={styles.filters} role="tablist" aria-label="Filter activity">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              className={filter === f.id ? styles.chipActive : styles.chip}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
              <span className={styles.count}>{counts[f.id]}</span>
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <div className={styles.empty}>
          {entries.length === 0
            ? "Agents, tool calls, guardrail checks and live reply evals will show up here as they happen."
            : "Nothing of this type yet."}
        </div>
      ) : (
        <div className={styles.list}>
          {visible.map((e) => {
            const detail = prettyDetail(e.detail);
            const status = STATUS_LABEL[e.status];
            const took = duration(e);
            return (
              <div
                key={e.id}
                className={`${styles.entry} ${styles[e.kind]} ${e.status === "fail" ? styles.failed : ""}`}
              >
                <div className={styles.head}>
                  <span className={styles.kind}>{KIND_LABEL[e.kind]}</span>
                  {status && (
                    <span className={`${styles.status} ${styles[`s_${e.status}`]}`}>{status}</span>
                  )}
                  <span className={styles.spacer} />
                  {took && <span className={styles.time}>{took}</span>}
                  <time className={styles.time}>
                    {new Date(e.at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </time>
                </div>
                <div className={styles.label}>{e.label}</div>
                {detail && <div className={styles.detail}>{detail}</div>}
                {e.result && (
                  <div className={styles.result} title={e.result}>
                    {e.kind === "agent" ? `“${e.result}”` : `→ ${e.result}`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

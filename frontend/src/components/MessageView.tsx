import {
  AlertCircle, Check, ChevronRight, CircleDashed, Copy, FileText, Loader2, MinusCircle, RefreshCw, XCircle,
} from "lucide-react";
import { memo, useEffect, useState } from "react";
import { bytes, copyText, mb, seconds } from "../lib/format";
import { useStore } from "../store";
import type { Message, Metrics, Source, Step } from "../types";
import { Markdown } from "./Markdown";
import { Popover } from "./Popover";

const MODE_LABEL = { fast: "Fast", think: "Think", research: "Deep Research" } as const;

function StepMark({ state }: { state: Step["state"] }) {
  if (state === "running") return <Loader2 size={14} className="spin" />;
  if (state === "done") return <Check size={14} strokeWidth={2.4} />;
  if (state === "error") return <XCircle size={14} />;
  if (state === "skipped" || state === "stopped") return <MinusCircle size={14} />;
  return <CircleDashed size={14} />;
}

function Activity({ steps, live, totalSeconds }: { steps: Step[]; live: boolean; totalSeconds?: number }) {
  const [open, setOpen] = useState(live);
  useEffect(() => {
    if (live) setOpen(true);
  }, [live]);
  if (!steps.length) return null;
  const running = [...steps].reverse().find((s) => s.state === "running");
  const current = running ?? steps[steps.length - 1];
  const failed = steps.filter((s) => s.state === "error").length;
  const busy = live && !!running;
  const summary = busy
    ? current.title
    : `${steps.length} step${steps.length === 1 ? "" : "s"}${failed ? ` · ${failed} with problems` : ""}`;
  return (
    <div className={`activity${open ? " open" : ""}`}>
      <button className="activity-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />}
        <span className="label">
          {busy ? <b>{summary}</b> : <>Worked through <b>{summary}</b></>}
        </span>
        {!live && totalSeconds != null && <span className="time">{seconds(totalSeconds)}</span>}
        <ChevronRight size={15} className="chev" />
      </button>
      {open && (
        <ol className="steps">
          {steps.map((s) => (
            <li key={s.id} className={`step ${s.state}`}>
              <span className="mark">
                <StepMark state={s.state} />
              </span>
              <div>
                <div className="t">{s.title}</div>
                {s.detail && <div className={`d${s.kind === "tool" ? " mono" : ""}`}>{s.detail}</div>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Reasoning({ text, live }: { text: string; live: boolean }) {
  if (!text.trim()) return null;
  return (
    <details className="reasoning">
      <summary>
        <ChevronRight size={14} className="chev" />
        {live ? "Model is reasoning…" : "Model reasoning"}
      </summary>
      <div className="body scroll">{text.trim()}</div>
    </details>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  const web = sources.filter((s) => s.kind === "web");
  const docs = sources.filter((s) => s.kind === "document");
  if (!web.length && !docs.length) return null;
  const cited = web.filter((s) => s.cited).length;
  return (
    <div className="sources">
      {web.length > 0 && (
        <>
          <h4>
            Sources <span>{web.length} pages read{cited ? ` · ${cited} cited` : ""}</span>
          </h4>
          <div className="source-list">
            {web.map((s) => (
              <a key={s.n} className={`source${s.cited === false ? " uncited" : ""}`} href={s.url} target="_blank"
                rel="noreferrer noopener" title={s.url}>
                <span className="top">
                  <span className="n">{s.n}</span>
                  <span className="site">{s.site}</span>
                  <span className="date">{s.date || "undated"}</span>
                </span>
                <span className="ttl">{s.title}</span>
              </a>
            ))}
          </div>
        </>
      )}
      {docs.length > 0 && (
        <>
          <h4>
            From your documents <span>{docs.length} passages</span>
          </h4>
          <div className="source-list">
            {docs.map((s, i) => (
              <div key={i} className="source" title={s.snippet}>
                <span className="top">
                  <FileText size={13} />
                  <span className="site">{s.title}</span>
                </span>
                <span className="ttl" style={{ fontWeight: 400 }}>{s.snippet}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function MetricsPanel({ m, mode }: { m: Metrics; mode: Message["mode"] }) {
  return (
    <dl className="metrics">
      <div className="head">
        {m.model_name} {m.quantization} · {MODE_LABEL[mode]}
      </div>
      <dt>Speed</dt>
      <dd>{m.tokens_per_second != null ? `${m.tokens_per_second} tokens/s` : "—"}</dd>
      <dt>First token</dt>
      <dd>{seconds(m.first_token_s)}</dd>
      <dt>Total time</dt>
      <dd>{seconds(m.total_s)}</dd>
      <dt>Tokens generated</dt>
      <dd>{m.completion_tokens ?? "—"}</dd>
      <dt>Tokens read</dt>
      <dd>{m.prompt_tokens ?? "—"}</dd>
      <dt>Model calls · tool calls</dt>
      <dd>
        {m.model_calls ?? 0} · {m.tool_calls ?? 0}
      </dd>
      <dt>Peak GPU memory (system)</dt>
      <dd>{mb(m.peak_vram_mb)}</dd>
      <dt title="Private memory committed by the engine process (excludes the memory-mapped model file)">Peak engine RAM (private)</dt>
      <dd>{mb(m.peak_ram_mb)}</dd>
      <dt>Context window</dt>
      <dd>{m.context_length?.toLocaleString() ?? "—"}</dd>
      {m.load_seconds != null && (
        <>
          <dt>Model load</dt>
          <dd>{seconds(m.load_seconds)}</dd>
        </>
      )}
    </dl>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="icon-btn sm" aria-label="Copy response" title="Copy"
      onClick={async () => {
        if (await copyText(text)) {
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        }
      }}>
      {done ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}

interface Props {
  message: Message;
  live?: boolean;
  isLast?: boolean;
}

export const MessageView = memo(function MessageView({ message: m, live = false, isLast = false }: Props) {
  const regenerate = useStore((s) => s.regenerate);
  const streaming = useStore((s) => s.streaming);
  const notice = useStore((s) => (live ? s.notice : ""));

  if (m.role === "user") {
    return (
      <div className="msg user">
        {m.attachments.length > 0 && (
          <div className="file-chips">
            {m.attachments.map((a) => (
              <span key={a.id} className="file-chip static">
                <FileText size={14} />
                <span className="name">{a.name}</span>
                <span className="size">{bytes(a.size)}</span>
              </span>
            ))}
          </div>
        )}
        <div className="bubble">{m.content}</div>
      </div>
    );
  }

  const hasBody = m.content.trim().length > 0;
  const waiting = live && !hasBody && !m.steps.length && !m.reasoning;
  return (
    <div className="msg assistant" aria-live={live ? "polite" : undefined} aria-busy={live}>
      <Activity steps={m.steps} live={live} totalSeconds={m.metrics.total_s} />
      <Reasoning text={m.reasoning} live={live && !hasBody} />
      {waiting && (
        <div className="waiting">
          <span className="cursor" />
          {notice || "Thinking…"}
        </div>
      )}
      {hasBody && <Markdown text={m.content} sources={m.sources} />}
      {live && hasBody && <span className="cursor" aria-hidden="true" />}
      {m.error && (
        <div className="msg-error" role="alert">
          <AlertCircle size={16} />
          <span>{m.error}</span>
        </div>
      )}
      {!live && m.status === "stopped" && <div className="stopped-note">Stopped before finishing.</div>}
      {!live && m.status === "error" && !m.error && (
        <div className="msg-error" role="alert">
          <AlertCircle size={16} />
          <span>This response failed before it completed.</span>
        </div>
      )}
      {!live && <Sources sources={m.sources} />}
      {!live && (
        <div className="msg-actions">
          {hasBody && <CopyButton text={m.content} />}
          {isLast && (
            <button className="icon-btn sm" aria-label="Regenerate response" title="Regenerate" disabled={streaming}
              onClick={() => void regenerate()}>
              <RefreshCw size={15} />
            </button>
          )}
          {m.metrics.model_name && (
            <span className="meta">
              <Popover side="up" align="left"
                trigger={(toggle) => (
                  <button onClick={toggle} title="Show measured performance">
                    {m.metrics.model_name} · {MODE_LABEL[m.mode]}
                    {m.metrics.tokens_per_second != null ? ` · ${m.metrics.tokens_per_second} tok/s` : ""}
                    {m.metrics.total_s != null ? ` · ${seconds(m.metrics.total_s)}` : ""}
                  </button>
                )}>
                {() => <MetricsPanel m={m.metrics} mode={m.mode} />}
              </Popover>
            </span>
          )}
        </div>
      )}
    </div>
  );
});

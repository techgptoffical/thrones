import { ArrowUp, Check, ChevronDown, FileText, Globe, Lightbulb, Loader2, Paperclip, Square, X, Zap } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { bytes } from "../lib/format";
import { useStore } from "../store";
import type { Mode } from "../types";
import { Popover } from "./Popover";

const MODES: { id: Mode; label: string; short: string; icon: typeof Zap; hint: string }[] = [
  { id: "fast", label: "Fast", short: "Fast", icon: Zap, hint: "Direct answer from the local model. Works offline." },
  { id: "think", label: "Think", short: "Think", icon: Lightbulb,
    hint: "Plans, reasons step by step, verifies calculations with real tools, then checks its own answer. Works offline." },
  { id: "research", label: "Deep Research", short: "Research", icon: Globe,
    hint: "Searches the web, reads several sources and writes a cited report. Needs internet." },
];

export interface ComposerHandle {
  focus: () => void;
  setText: (text: string) => void;
}

export const Composer = forwardRef<ComposerHandle>(function Composer(_, ref) {
  const [text, setText] = useState("");
  const [drag, setDrag] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const composing = useRef(false);

  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const streaming = useStore((s) => s.streaming);
  const send = useStore((s) => s.send);
  const stop = useStore((s) => s.stop);
  const attach = useStore((s) => s.attach);
  const pending = useStore((s) => s.pendingDocs);
  const removePending = useStore((s) => s.removePending);
  const uploading = useStore((s) => s.uploading);
  const models = useStore((s) => s.models);
  const status = useStore((s) => s.status);
  const settings = useStore((s) => s.settings);
  const selectModel = useStore((s) => s.selectModel);
  const switching = useStore((s) => s.switchingModel);
  const openSettings = useStore((s) => s.openSettings);
  const online = useStore((s) => s.online);
  const activeId = useStore((s) => s.activeId);

  useImperativeHandle(ref, () => ({
    focus: () => area.current?.focus(),
    setText: (t: string) => {
      setText(t);
      requestAnimationFrame(() => area.current?.focus());
    },
  }));

  useEffect(() => {
    const resize = () => {
      const el = area.current;
      if (!el) return;
      el.style.height = "auto";
      // scrollHeight is 0 while the window is hidden or not yet laid out; keep the natural height then.
      if (el.scrollHeight > 0) el.style.height = `${Math.min(el.scrollHeight, Math.max(120, window.innerHeight * 0.38))}px`;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [text]);

  useEffect(() => {
    area.current?.focus();
  }, [activeId]);

  const installed = models.filter((m) => m.installed);
  const resolvedId = status?.resolved?.model_id ?? "";
  const current = installed.find((m) => m.id === resolvedId);
  const noModel = installed.length === 0;
  const researchBlocked = mode === "research" && (settings?.offline_mode || settings?.web_research_enabled === false);
  const canSend = text.trim().length > 0 && !streaming && !noModel && uploading === 0;

  const submit = () => {
    if (!canSend) return;
    const value = text;
    setText("");
    void send(value);
  };

  const hint = (() => {
    if (noModel) return "No model installed yet — open Settings → Models to download one.";
    if (researchBlocked) return "Deep Research is unavailable: web access is switched off in Settings → Privacy.";
    if (mode === "research" && online === false) return "No internet connection detected — Deep Research cannot search right now.";
    return MODES.find((m) => m.id === mode)?.hint ?? "";
  })();

  return (
    <div className="composer-wrap">
      <div
        className={`composer${drag ? " drag" : ""}`}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) {
            e.preventDefault();
            setDrag(true);
          }
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (e.dataTransfer.files.length) void attach(Array.from(e.dataTransfer.files));
        }}
      >
        {(pending.length > 0 || uploading > 0) && (
          <div className="pending">
            {pending.map((d) => (
              <span key={d.id} className="file-chip">
                <FileText size={14} />
                <span className="name">{d.name}</span>
                <span className="size">{bytes(d.size)}</span>
                <button className="icon-btn sm" style={{ width: 22, height: 22 }} aria-label={`Remove ${d.name}`}
                  onClick={() => void removePending(d.id)}>
                  <X size={13} />
                </button>
              </span>
            ))}
            {uploading > 0 && (
              <span className="file-chip static">
                <Loader2 size={14} className="spin" />
                <span className="name">Reading file…</span>
              </span>
            )}
          </div>
        )}
        <textarea
          ref={area}
          rows={1}
          value={text}
          placeholder={mode === "research" ? "What should I research?" : "Ask anything"}
          aria-label="Message"
          onChange={(e) => setText(e.target.value)}
          onCompositionStart={() => (composing.current = true)}
          onCompositionEnd={() => (composing.current = false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData.files);
            if (files.length) {
              e.preventDefault();
              void attach(files);
            }
          }}
        />
        <div className="bar">
          <input ref={fileInput} type="file" multiple hidden
            accept=".txt,.md,.pdf,.docx,.csv,.tsv,.json,.jsonl,.yaml,.yml,.xml,.html,.log,.py,.js,.ts,.tsx,.jsx,.java,.c,.h,.cpp,.cs,.go,.rs,.rb,.php,.sql,.sh,.ps1,.css,.tex,.toml,.ini,.rst"
            onChange={(e) => {
              if (e.target.files?.length) void attach(Array.from(e.target.files));
              e.target.value = "";
            }} />
          <button className="icon-btn" aria-label="Attach files" title="Attach documents (text, PDF, DOCX, code)"
            onClick={() => fileInput.current?.click()}>
            <Paperclip size={17} />
          </button>
          <div className="seg" role="radiogroup" aria-label="Mode">
            {MODES.map((m) => (
              <button key={m.id} role="radio" aria-checked={mode === m.id} className={mode === m.id ? "on" : ""}
                title={m.hint} disabled={streaming} onClick={() => setMode(m.id)}>
                <m.icon size={14} />
                {m.label}
              </button>
            ))}
          </div>
          <span className="spacer" />
          <Popover side="up" align="right"
            trigger={(toggle) => (
              <button className="model-btn" onClick={toggle} aria-label="Choose model" disabled={switching}>
                {switching && <Loader2 size={13} className="spin" />}
                <span>{switching ? "Loading model…" : current?.name ?? (noModel ? "No model" : "Choose model")}</span>
                <ChevronDown size={14} />
              </button>
            )}>
            {(close) => (
              <div style={{ minWidth: 270 }}>
                <div className="menu-label">Local models on this PC</div>
                {installed.map((m) => (
                  <button key={m.id} className="menu-item" role="menuitemradio" aria-checked={m.id === resolvedId}
                    onClick={() => {
                      close();
                      if (m.id !== resolvedId) void selectModel(m.id);
                    }}>
                    <span>
                      {m.name} <span style={{ color: "var(--text-3)" }}>{m.quantization}</span>
                      <span className="sub">{m.compatibility.message}</span>
                    </span>
                    {m.id === resolvedId && <Check size={15} className="check" />}
                  </button>
                ))}
                {noModel && <div className="sb-empty">Nothing installed yet.</div>}
                <div className="menu-sep" />
                <button className="menu-item" onClick={() => { close(); openSettings("models"); }}>
                  Manage and download models…
                </button>
              </div>
            )}
          </Popover>
          {streaming ? (
            <button className="send" onClick={() => void stop()} aria-label="Stop generating" title="Stop (Esc)">
              <Square size={13} fill="currentColor" />
            </button>
          ) : (
            <button className="send" onClick={submit} disabled={!canSend} aria-label="Send message" title="Send (Enter)">
              <ArrowUp size={18} strokeWidth={2.4} />
            </button>
          )}
        </div>
      </div>
      <div className="composer-hint">{hint}</div>
    </div>
  );
});

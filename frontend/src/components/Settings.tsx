import {
  AlertTriangle, Brain, CheckCircle2, Cpu, Download, Globe, Info, Pause, Plus, Shield, SlidersHorizontal,
  Sparkles, Trash2, Wrench, X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { bytes, mb } from "../lib/format";
import { useStore, type SettingsSection } from "../store";
import type { Memory, ModelInfo, Settings as SettingsT } from "../types";

const SECTIONS: { id: SettingsSection; label: string; icon: typeof Cpu }[] = [
  { id: "general", label: "General", icon: Sparkles },
  { id: "models", label: "Models & hardware", icon: Cpu },
  { id: "generation", label: "Generation", icon: SlidersHorizontal },
  { id: "research", label: "Research", icon: Globe },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "privacy", label: "Privacy & data", icon: Shield },
  { id: "about", label: "About", icon: Info },
];

/* ---------------------------------------------------------------- controls */
function Field({ name, help, warn, children, col }: {
  name: string; help?: ReactNode; warn?: ReactNode; children: ReactNode; col?: boolean;
}) {
  return (
    <div className={`field${col ? " col" : ""}`}>
      <div className="txt">
        <div className="name">{name}</div>
        {help && <div className="help">{help}</div>}
        {warn && <div className="help warn">{warn}</div>}
      </div>
      <div className="ctl">{children}</div>
    </div>
  );
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button className="switch" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)} />;
}

function Choice<T extends string>({ value, options, onChange }: {
  value: T; options: { id: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="choice" role="radiogroup">
      {options.map((o) => (
        <button key={o.id} role="radio" aria-checked={value === o.id} className={value === o.id ? "on" : ""}
          onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Numeric input that commits on blur/Enter so half-typed values are never saved. */
function Num({ value, onCommit, min, max, step = 1, placeholder, label }: {
  value: number | null; onCommit: (v: number | null) => void; min: number; max: number; step?: number;
  placeholder?: string; label: string;
}) {
  const [draft, setDraft] = useState(value == null ? "" : String(value));
  useEffect(() => setDraft(value == null ? "" : String(value)), [value]);
  const commit = () => {
    if (draft.trim() === "") {
      if (placeholder !== undefined) onCommit(null);
      else setDraft(value == null ? "" : String(value));
      return;
    }
    const n = Number(draft);
    if (Number.isNaN(n)) {
      setDraft(value == null ? "" : String(value));
      return;
    }
    const clamped = Math.min(max, Math.max(min, n));
    setDraft(String(clamped));
    if (clamped !== value) onCommit(clamped);
  };
  return (
    <input className="input num" type="number" inputMode="decimal" aria-label={label} value={draft} min={min} max={max}
      step={step} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
  );
}

function Text({ value, onCommit, placeholder, label, type = "text", width = 260 }: {
  value: string; onCommit: (v: string) => void; placeholder?: string; label: string; type?: string; width?: number;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <input className="input" style={{ width }} type={type} aria-label={label} value={draft} placeholder={placeholder}
      autoComplete="off" spellCheck={false} onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft.trim())}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
  );
}

type Save = (patch: Partial<SettingsT>) => Promise<void>;

/* ----------------------------------------------------------------- general */
function General({ s, save }: { s: SettingsT; save: Save }) {
  const [instructions, setInstructions] = useState(s.custom_instructions);
  return (
    <>
      <div className="set-group">
        <h4>Appearance</h4>
        <Field name="Theme">
          <Choice value={s.theme} onChange={(theme) => void save({ theme })}
            options={[{ id: "system", label: "System" }, { id: "light", label: "Light" }, { id: "dark", label: "Dark" }]} />
        </Field>
        <Field name="Density" help="Compact tightens spacing in the sidebar and conversation.">
          <Choice value={s.density} onChange={(density) => void save({ density })}
            options={[{ id: "comfortable", label: "Comfortable" }, { id: "compact", label: "Compact" }]} />
        </Field>
        <Field name="Text size">
          <Choice value={String(s.font_scale)} onChange={(v) => void save({ font_scale: Number(v) })}
            options={[{ id: "92", label: "Small" }, { id: "100", label: "Default" }, { id: "110", label: "Large" }]} />
        </Field>
      </div>
      <div className="set-group">
        <h4>Assistant</h4>
        <Field name="Conversational style"
          help="Changes tone and level of detail only. It does not switch safety behaviour on or off.">
          <select className="select" value={s.style} aria-label="Conversational style"
            onChange={(e) => void save({ style: e.target.value as SettingsT["style"] })}>
            <option value="balanced">Balanced</option>
            <option value="direct">Direct</option>
            <option value="creative">Creative</option>
            <option value="technical">Technical</option>
          </select>
        </Field>
        <Field name="Custom instructions" col
          help="Added to every conversation. For example: “Reply in Hinglish”, or “I am a second-year CS student”.">
          <textarea className="textarea" rows={4} maxLength={2000} value={instructions} aria-label="Custom instructions"
            placeholder="How should Thrones respond to you?" onChange={(e) => setInstructions(e.target.value)}
            onBlur={() => instructions !== s.custom_instructions && void save({ custom_instructions: instructions })} />
        </Field>
        <Field name="Show model reasoning"
          help="When the model reasons before answering (Think and Deep Research), keep its reasoning text available under each reply.">
          <Switch checked={s.show_reasoning} label="Show model reasoning" onChange={(v) => void save({ show_reasoning: v })} />
        </Field>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ models */
function ModelCard({ m, activeId }: { m: ModelInfo; activeId: string }) {
  const refreshModels = useStore((s) => s.refreshModels);
  const selectModel = useStore((s) => s.selectModel);
  const switching = useStore((s) => s.switchingModel);
  const toast = useStore((s) => s.toast);
  const [confirm, setConfirm] = useState(false);
  const d = m.download;
  const downloading = d?.state === "downloading";
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Action failed.", "error");
    }
    await refreshModels();
  };
  const CompatIcon = m.compatibility.level === "ok" ? CheckCircle2 : AlertTriangle;
  return (
    <div className="model-card">
      <div className="row1">
        <span className="nm">{m.name}</span>
        <span className="tag">{m.quantization}</span>
        <span className="tag">{m.tier}</span>
        {m.adapter && <span className="tag gold">Thrones fine-tune</span>}
        {m.experimental && <span className="tag">Experimental</span>}
        {m.loaded && <span className="tag gold">In memory</span>}
        {!m.loaded && m.id === activeId && m.installed && <span className="tag gold">Selected</span>}
        <span style={{ flex: 1 }} />
        {m.installed ? (
          <>
            {m.id !== activeId && (
              <button className="btn sm" disabled={switching} onClick={() => void selectModel(m.id)}>Use this model</button>
            )}
            {confirm ? (
              <>
                <button className="btn sm danger" onClick={() => { setConfirm(false); void act(() => api.deleteModel(m.id)); }}>
                  Delete {bytes(m.size_bytes)}
                </button>
                <button className="btn sm ghost" onClick={() => setConfirm(false)}>Keep</button>
              </>
            ) : (
              <button className="icon-btn sm" aria-label={`Delete ${m.name} from disk`} title="Delete from disk"
                disabled={m.loaded} onClick={() => setConfirm(true)}>
                <Trash2 size={15} />
              </button>
            )}
          </>
        ) : downloading ? (
          <button className="btn sm" onClick={() => void act(() => api.cancelDownload(m.id))}>
            <Pause size={13} /> Pause
          </button>
        ) : (
          <button className="btn sm primary" disabled={m.compatibility.level === "bad"}
            onClick={() => void act(() => api.downloadModel(m.id))}>
            <Download size={13} /> {d?.state === "paused" || d?.state === "error" ? "Resume" : "Download"} · {bytes(m.size_bytes)}
          </button>
        )}
      </div>
      <div className="meta">
        {m.publisher} · {m.parameters} parameters · {m.license} · native context {m.native_context.toLocaleString()} ·{" "}
        <a href={m.base_repo} target="_blank" rel="noreferrer noopener">model card</a> ·{" "}
        <a href={m.gguf_repo} target="_blank" rel="noreferrer noopener">GGUF source</a>
      </div>
      <div className="meta">{m.notes}</div>
      <div className={`compat ${m.compatibility.level}`}>
        <CompatIcon size={14} /> {m.compatibility.message}
      </div>
      {d && d.state !== "done" && (
        <>
          <div className="progress"><i style={{ width: `${d.total ? (d.received / d.total) * 100 : 0}%` }} /></div>
          <div className="meta">
            {d.state === "error" ? <span style={{ color: "var(--danger)" }}>{d.error}</span>
              : `${bytes(d.received)} of ${bytes(d.total)}${downloading ? ` · ${bytes(d.speed_bps)}/s` : " · paused"}`}
          </div>
        </>
      )}
    </div>
  );
}

function Models({ s, save }: { s: SettingsT; save: Save }) {
  const status = useStore((st) => st.status);
  const models = useStore((st) => st.models);
  const refreshModels = useStore((st) => st.refreshModels);
  const refreshStatus = useStore((st) => st.refreshStatus);
  const streaming = useStore((st) => st.streaming);
  const toast = useStore((st) => st.toast);
  const anyDownloading = models.some((m) => m.download?.state === "downloading");

  useEffect(() => {
    void refreshModels();
    void refreshStatus();
    const t = window.setInterval(() => {
      void refreshModels();
      void refreshStatus();
    }, anyDownloading ? 1000 : 4000);
    return () => window.clearInterval(t);
  }, [anyDownloading, refreshModels, refreshStatus]);

  if (!status) return null;
  const hw = status.hardware;
  const gpu = hw.gpus[0];
  const engine = status.engine;
  const resolved = status.resolved;
  const profiles = [
    { id: "auto", label: "Automatic", description: `Picks for this PC: ${status.profiles[status.recommended_profile]?.label}.` },
    ...Object.entries(status.profiles).map(([id, p]) => ({ id, label: p.label, description: p.description })),
  ];
  const needsReload = engine.loaded && resolved && !resolved.error &&
    (engine.model_id !== resolved.model_id || engine.context_length !== resolved.context_length ||
      engine.gpu_layers !== resolved.gpu_layers);

  const applyNow = async () => {
    try {
      await api.loadEngine();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not load the model.", "error");
    }
    await refreshStatus();
  };

  return (
    <>
      <div className="set-group">
        <h4>This PC — measured now</h4>
        <div className="hw-grid">
          <div>
            <div className="k">Graphics</div>
            <div className="v" title={gpu?.name}>{gpu ? gpu.name.replace("NVIDIA GeForce ", "") : "No supported GPU"}</div>
            <div className="s">{gpu ? `${mb(gpu.vram_used_mb)} of ${mb(gpu.vram_total_mb)} VRAM in use` : "Models will run on the CPU"}</div>
          </div>
          <div>
            <div className="k">Processor</div>
            <div className="v" title={hw.cpu}>{hw.cpu.replace(/\(R\)|\(TM\)|CPU|@.*$/g, "").replace(/\s+/g, " ").trim()}</div>
            <div className="s">{hw.cpu_cores} cores · {hw.cpu_threads} threads</div>
          </div>
          <div>
            <div className="k">Memory</div>
            <div className="v">{hw.ram_total_gb} GB RAM</div>
            <div className="s">{hw.ram_available_gb} GB available</div>
          </div>
        </div>
        <div className="note">
          {engine.loaded ? (
            <>
              <b>{engine.model_name} {engine.quantization}</b> is in memory via {engine.provider} · context{" "}
              {engine.context_length?.toLocaleString()} tokens · {engine.gpu_layers ? "GPU offload on" : "CPU only"} · loaded in{" "}
              {engine.load_seconds}s{engine.model_vram_mb != null ? ` · about ${mb(engine.model_vram_mb)} VRAM taken at load` : ""}.
              {engine.warnings?.map((w) => <div key={w} style={{ color: "var(--warn)" }}>{w}</div>)}
              {engine.fallback && (
                <div style={{ marginTop: 6 }}>
                  The full settings did not fit, usually because other apps were using memory. Close them and press
                  “Apply new settings now” to retry.
                  {engine.last_load_failure && (
                    <details style={{ marginTop: 4 }}>
                      <summary style={{ cursor: "pointer" }}>Engine error</summary>
                      <span className="path">{engine.last_load_failure}</span>
                    </details>
                  )}
                </div>
              )}
            </>
          ) : engine.loading ? "A model is loading…" : "No model is in memory. It loads automatically when you send a message."}
          <div style={{ display: "flex", gap: 8, marginTop: 9 }}>
            {needsReload && <button className="btn sm primary" disabled={streaming} onClick={() => void applyNow()}>Apply new settings now</button>}
            {!engine.loaded && resolved && !resolved.error && (
              <button className="btn sm" disabled={!!engine.loading} onClick={() => void applyNow()}>Load {resolved.model_name} now</button>
            )}
            {engine.loaded && (
              <button className="btn sm" disabled={streaming}
                onClick={() => void api.unloadEngine().then(refreshStatus).catch((e) => toast(e.message, "error"))}>
                Unload and free memory
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="set-group">
        <h4>Performance profile</h4>
        <div className="profiles">
          {profiles.map((p) => (
            <button key={p.id} className={`profile${s.profile === p.id ? " on" : ""}`} aria-pressed={s.profile === p.id}
              onClick={() => void save({ profile: p.id, model_id: "", context_length: 0 })}>
              <span className="n">{p.label}</span>
              <span className="d">{p.description}</span>
            </button>
          ))}
        </div>
        {resolved?.error
          ? <div className="note warn">{resolved.error}</div>
          : resolved && (
            <div className="help" style={{ marginTop: 8, fontSize: "var(--text-sm)", color: "var(--text-3)" }}>
              Current selection: {resolved.model_name}, {resolved.context_length?.toLocaleString()} token context
              {resolved.profile ? ` (${status.profiles[resolved.profile]?.label} profile)` : ""}.
            </div>
          )}
        <Field name="Context length"
          help="How much conversation and document text the model can see at once. Larger uses more memory. 0 follows the profile.">
          <Num label="Context length" value={s.context_length} min={0} max={131072} step={1024}
            onCommit={(v) => void save({ context_length: v ?? 0 })} />
        </Field>
        <Field name="GPU layers" help="-1 puts as much of the model on the GPU as fits. 0 forces CPU only.">
          <Num label="GPU layers" value={s.gpu_layers} min={-1} max={999} onCommit={(v) => void save({ gpu_layers: v ?? -1 })} />
        </Field>
        <Field name="Unload when idle" help="Minutes without use before the model is removed from memory. 0 keeps it loaded.">
          <Num label="Idle unload minutes" value={s.idle_unload_minutes} min={0} max={720}
            onCommit={(v) => void save({ idle_unload_minutes: v ?? 0 })} />
        </Field>
      </div>

      <div className="set-group">
        <h4>Models</h4>
        {!status.runtime_installed && (
          <div className="note warn">The llama.cpp runtime was not found in runtime/llama.cpp. Models cannot be loaded until it is installed.</div>
        )}
        {models.map((m) => <ModelCard key={m.id} m={m} activeId={resolved?.model_id ?? ""} />)}
        <div className="note">
          These are unmodified third-party open-weight models, each under its own license. Thrones is the application
          around them; it does not ship or claim its own trained model. Files are stored in <span className="path">{status.paths.models}</span>
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------------- generation */
function Generation({ s, save }: { s: SettingsT; save: Save }) {
  return (
    <>
      <div className="set-group">
        <h4>Sampling</h4>
        <Field name="Temperature" help="Leave empty to use the recommended value for each mode (0.6–1.0).">
          <Num label="Temperature" value={s.temperature} min={0} max={2} step={0.05} placeholder="auto"
            onCommit={(v) => void save({ temperature: v })} />
        </Field>
        <Field name="Top-p" help="Leave empty for the mode default.">
          <Num label="Top-p" value={s.top_p} min={0.05} max={1} step={0.05} placeholder="auto" onCommit={(v) => void save({ top_p: v })} />
        </Field>
        <Field name="Top-k" help="Leave empty for the mode default (20).">
          <Num label="Top-k" value={s.top_k} min={1} max={200} placeholder="auto" onCommit={(v) => void save({ top_k: v })} />
        </Field>
        <Field name="Maximum response length" help="Upper limit in tokens for one reply, including any reasoning.">
          <Num label="Maximum tokens" value={s.max_tokens} min={256} max={32768} step={256}
            onCommit={(v) => void save({ max_tokens: v ?? 4096 })} />
        </Field>
      </div>
      <div className="set-group">
        <h4>Think mode budgets</h4>
        <Field name="Verify answers" help="After answering, run a second independent pass that re-checks logic and recomputes numbers, and rewrite the answer if it finds an error.">
          <Switch checked={s.think_verify} label="Verify answers" onChange={(v) => void save({ think_verify: v })} />
        </Field>
        <Field name="Tool calls per answer" help="Most calculator or Python calls allowed while solving one request.">
          <Num label="Tool calls" value={s.think_max_tool_calls} min={0} max={20} onCommit={(v) => void save({ think_max_tool_calls: v ?? 6 })} />
        </Field>
        <Field name="Time budget (seconds)" help="After this, no new tool calls or checks are started.">
          <Num label="Think time budget" value={s.think_time_budget_s} min={20} max={1800} step={10}
            onCommit={(v) => void save({ think_time_budget_s: v ?? 180 })} />
        </Field>
        <Field name="Reasoning limit per step (tokens)"
          help="Small models can reason in circles and never answer. After this many thinking tokens the engine makes the model stop and answer. 0 = no limit. Applies the next time the model loads.">
          <Num label="Reasoning limit" value={s.think_reasoning_budget} min={0} max={32768} step={256}
            onCommit={(v) => void save({ think_reasoning_budget: v ?? 2048 })} />
        </Field>
        <Field name="Token budget" help="Total tokens the model may generate across planning, solving and checking.">
          <Num label="Think token budget" value={s.think_token_budget} min={1000} max={60000} step={500}
            onCommit={(v) => void save({ think_token_budget: v ?? 8000 })} />
        </Field>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- research */
function Research({ s, save }: { s: SettingsT; save: Save }) {
  const online = useStore((st) => st.online);
  return (
    <>
      <div className="set-group">
        <h4>Web access</h4>
        <Field name="Allow Deep Research to use the internet"
          help="Only Deep Research goes online. It sends your search queries to the search provider and downloads the pages it reads. Fast and Think never use the network."
          warn={s.offline_mode ? "Offline mode is on (Privacy & data), so this has no effect right now." : undefined}>
          <Switch checked={s.web_research_enabled} label="Allow web research" onChange={(v) => void save({ web_research_enabled: v })} />
        </Field>
        <div className="note">
          Connection right now: {s.offline_mode ? "blocked by offline mode" : online == null ? "checking…" : online ? "internet reachable" : "no internet detected"}.
        </div>
      </div>
      <div className="set-group">
        <h4>Search provider</h4>
        <Field name="Provider" col
          help={{
            duckduckgo: "DuckDuckGo — no account or key needed. An unofficial interface, so it can be rate-limited during heavy use.",
            searxng: "SearXNG — your own self-hosted metasearch instance. Most private; you run it yourself.",
            brave: "Brave Search API — official API with a free tier; needs your own key. The key is stored only in the local database.",
          }[s.search_provider]}>
          <Choice value={s.search_provider} onChange={(search_provider) => void save({ search_provider })}
            options={[{ id: "duckduckgo", label: "DuckDuckGo" }, { id: "searxng", label: "SearXNG" }, { id: "brave", label: "Brave API" }]} />
        </Field>
        {s.search_provider === "searxng" && (
          <Field name="SearXNG address" help="Must have the JSON output format enabled.">
            <Text label="SearXNG address" value={s.searxng_url} placeholder="http://localhost:8080" onCommit={(v) => void save({ searxng_url: v })} />
          </Field>
        )}
        {s.search_provider === "brave" && (
          <Field name="Brave API key">
            <Text label="Brave API key" type="password" value={s.brave_api_key} placeholder="Paste your key" onCommit={(v) => void save({ brave_api_key: v })} />
          </Field>
        )}
      </div>
      <div className="set-group">
        <h4>Depth</h4>
        <Field name="Sources to read" help="Pages fetched and analysed per report. More is slower but broader.">
          <Num label="Sources to read" value={s.research_max_sources} min={2} max={15} onCommit={(v) => void save({ research_max_sources: v ?? 8 })} />
        </Field>
        <Field name="Search rounds" help="With 2 or more, the model checks for gaps and searches again if evidence is thin.">
          <Num label="Search rounds" value={s.research_max_rounds} min={1} max={3} onCommit={(v) => void save({ research_max_rounds: v ?? 2 })} />
        </Field>
        <Field name="Time budget (seconds)">
          <Num label="Research time budget" value={s.research_time_budget_s} min={60} max={1800} step={30}
            onCommit={(v) => void save({ research_time_budget_s: v ?? 300 })} />
        </Field>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------- tools */
function Tools({ s, save }: { s: SettingsT; save: Save }) {
  return (
    <div className="set-group">
      <h4>Tools the model can use</h4>
      <Field name="Calculator" help="Exact arithmetic evaluated by Python instead of by the model. Always available in Fast and Think.">
        <span className="tag gold">Always on</span>
      </Field>
      <Field name="Document reading" help="Text, code, CSV, JSON, PDF and DOCX files you attach are indexed locally and quoted to the model. Scanned PDFs need OCR, which is not installed.">
        <span className="tag gold">Always on</span>
      </Field>
      <Field name="Web search and page reading" help="Used only by Deep Research. Configure it under Research.">
        <span className="tag">{s.web_research_enabled && !s.offline_mode ? "Enabled" : "Off"}</span>
      </Field>
      <Field name="Run Python code (Think mode)"
        help="Lets the model write and run short Python scripts for multi-step calculations and data work."
        warn="This is not a security sandbox. Scripts run as your Windows user with a 15-second limit in a temporary folder. Leave it off unless you want this.">
        <Switch checked={s.python_tool_enabled} label="Run Python code" onChange={(v) => void save({ python_tool_enabled: v })} />
      </Field>
      <Field name="External tool servers (MCP)" help="Not available in Thrones 1.0. Planned with per-tool permissions, timeouts and logging.">
        <span className="tag">Not available</span>
      </Field>
    </div>
  );
}

/* ------------------------------------------------------------------ memory */
function MemorySection({ s, save }: { s: SettingsT; save: Save }) {
  const [items, setItems] = useState<Memory[]>([]);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const toast = useStore((st) => st.toast);

  const load = () => api.memories().then((r) => setItems(r.memories)).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const run = (p: Promise<unknown>) => p.then(load).catch((e) => toast(e.message, "error"));

  return (
    <>
      <div className="set-group">
        <h4>Long-term memory</h4>
        <Field name="Use memory"
          help="Saved facts are included in every new conversation. Thrones only saves something when you add it here or explicitly ask it to remember. Everything stays in the local database.">
          <Switch checked={s.memory_enabled} label="Use memory" onChange={(v) => void save({ memory_enabled: v })} />
        </Field>
      </div>
      <div className="set-group">
        <h4>Saved ({items.length})</h4>
        <div className="field">
          <input className="input" style={{ flex: 1 }} value={draft} maxLength={400} aria-label="New memory"
            placeholder="Add something to remember, e.g. “Prefers answers in Hinglish”"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                void run(api.addMemory(draft.trim()));
                setDraft("");
              }
            }} />
          <button className="btn" disabled={!draft.trim()} onClick={() => { void run(api.addMemory(draft.trim())); setDraft(""); }}>
            <Plus size={14} /> Add
          </button>
        </div>
        {items.length === 0 && <div className="sb-empty" style={{ padding: "14px 0" }}>Nothing saved yet.</div>}
        {items.map((m) => (
          <div key={m.id} className="mem-row">
            {editing === m.id ? (
              <input className="input" style={{ flex: 1 }} autoFocus value={editText} maxLength={400} aria-label="Edit memory"
                onChange={(e) => setEditText(e.target.value)}
                onBlur={() => {
                  setEditing(null);
                  if (editText.trim() && editText.trim() !== m.content) void run(api.updateMemory(m.id, { content: editText.trim() }));
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                  if (e.key === "Escape") setEditing(null);
                }} />
            ) : (
              <button className={`text${m.enabled ? "" : " off"}`} style={{ textAlign: "left" }} title="Click to edit"
                onClick={() => { setEditing(m.id); setEditText(m.content); }}>
                {m.content}
                <div className="src">{m.source === "assistant" ? "Saved by the assistant at your request" : "Added by you"} · {new Date(m.created_at * 1000).toLocaleDateString()}</div>
              </button>
            )}
            <Switch checked={!!m.enabled} label={`Use memory: ${m.content}`} onChange={(v) => void run(api.updateMemory(m.id, { enabled: v }))} />
            <button className="icon-btn sm" aria-label="Delete memory" title="Delete" onClick={() => void run(api.deleteMemory(m.id))}>
              <Trash2 size={15} />
            </button>
          </div>
        ))}
        {items.length > 0 && (
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            {confirmClear ? (
              <>
                <button className="btn sm danger" onClick={() => { setConfirmClear(false); void run(api.clearMemories()); }}>Yes, delete all {items.length}</button>
                <button className="btn sm ghost" onClick={() => setConfirmClear(false)}>Cancel</button>
              </>
            ) : <button className="btn sm danger" onClick={() => setConfirmClear(true)}>Delete all memories</button>}
            <a className="btn sm" href="/api/export">Export with my data</a>
          </div>
        )}
      </div>
    </>
  );
}

/* ----------------------------------------------------------------- privacy */
function Privacy({ s, save }: { s: SettingsT; save: Save }) {
  const status = useStore((st) => st.status);
  const newChat = useStore((st) => st.newChat);
  const refresh = useStore((st) => st.refreshConversations);
  const toast = useStore((st) => st.toast);
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <div className="set-group">
        <h4>Network</h4>
        <Field name="Offline mode" help="Blocks every network feature: Deep Research and model downloads. Chat, Think, documents and memory keep working.">
          <Switch checked={s.offline_mode} label="Offline mode" onChange={(v) => void save({ offline_mode: v })} />
        </Field>
        <Field name="Web research" help="Allow Deep Research to search and read web pages.">
          <Switch checked={s.web_research_enabled} label="Web research" onChange={(v) => void save({ web_research_enabled: v })} />
        </Field>
        <Field name="Remote AI services" help="Thrones has no cloud-model integration. All inference runs on this PC through llama.cpp.">
          <span className="tag">None</span>
        </Field>
        <Field name="Diagnostics and telemetry" help="Nothing is collected or sent. A local engine log is kept in the data folder for troubleshooting.">
          <span className="tag">Local log only</span>
        </Field>
        <div className="note">
          Every outbound request Thrones can make: (1) search queries to your chosen search provider and (2) the web pages
          Deep Research reads — both only during a Deep Research run; (3) model files from huggingface.co when you press
          Download. Links you click open in your browser as normal.
        </div>
      </div>
      <div className="set-group">
        <h4>Your data</h4>
        <Field name="Memory persistence" help="Keep saved facts across conversations.">
          <Switch checked={s.memory_enabled} label="Memory persistence" onChange={(v) => void save({ memory_enabled: v })} />
        </Field>
        <Field name="Export everything" help="Conversations, memories, projects and settings as one JSON file. API keys are left out.">
          <a className="btn" href="/api/export"><Download size={14} /> Export</a>
        </Field>
        <Field name="Delete all conversations" help="Removes every chat, research report and attached document from this PC. Memories and settings are kept.">
          {confirm ? (
            <>
              <button className="btn danger" onClick={() => {
                setConfirm(false);
                void api.deleteAllConversations().then(() => { newChat(); void refresh(); toast("All conversations deleted.", "success"); })
                  .catch((e) => toast(e.message, "error"));
              }}>Yes, delete everything</button>
              <button className="btn ghost" onClick={() => setConfirm(false)}>Cancel</button>
            </>
          ) : <button className="btn danger" onClick={() => setConfirm(true)}>Delete all…</button>}
        </Field>
      </div>
      {status && (
        <div className="set-group">
          <h4>Where things are stored</h4>
          <Field name="Conversations, memory and settings" col><span className="path">{status.paths.database}</span></Field>
          <Field name="Uploaded documents" col><span className="path">{status.paths.uploads}</span></Field>
          <Field name="Model files" col><span className="path">{status.paths.models}</span></Field>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------- about */
function About() {
  const status = useStore((s) => s.status);
  const models = useStore((s) => s.models);
  const active = models.find((m) => m.id === status?.resolved?.model_id);
  return (
    <>
      <div className="set-group">
        <h4>Thrones {status?.version}</h4>
        <div className="note" style={{ marginTop: 8 }}>
          Thrones is a local-first AI assistant: an application that runs open-weight language models on your own
          computer and adds reasoning workflows, tools, document reading, memory and web research around them.
        </div>
        <Field name="What Thrones is" help="Original application software: this interface, the orchestration, tools and research pipeline. Released under the MIT license.">
          <span className="tag gold">Software</span>
        </Field>
        <Field name="What Thrones is not" help="Thrones did not train a language model from scratch. Its intelligence comes from open-weight base models made by others, listed below. Thrones Adapter 0.2 is a small optional fine-tune (a 61 MB LoRA) on top of Qwen3.5 4B; the base weights are unchanged.">
          <span className="tag">Not a from-scratch model</span>
        </Field>
      </div>
      <div className="set-group">
        <h4>Base model in use</h4>
        {active ? (
          <>
            {active.adapter && (
              <Field name={`${active.adapter} (Thrones fine-tune)`}
                help={`A LoRA adapter trained by the Thrones project on licensed and self-generated data, applied on top of ${active.base_name}. File: ${active.lora_file}. Training details and results: training/runs/${(active.lora_file ?? '').replace('.gguf', '')}/MODEL_CARD.md.`}>
                <span className="tag gold">Ours</span>
              </Field>
            )}
            <Field name={`${active.base_name ?? active.name} (${active.quantization})`} help={`${active.publisher} · ${active.parameters} parameters · ${active.license} license`}>
              <a className="btn sm" href={active.base_repo} target="_blank" rel="noreferrer noopener">Model card</a>
            </Field>
            <Field name="Quantized build" help={`${active.file} — a community GGUF conversion of the original weights. Quantization reduces precision to fit consumer hardware.`}>
              <a className="btn sm" href={active.gguf_repo} target="_blank" rel="noreferrer noopener">Source</a>
            </Field>
          </>
        ) : <div className="sb-empty" style={{ padding: "12px 0" }}>No model installed.</div>}
        <Field name="Inference engine" help="llama.cpp (MIT license), running as a local process bound to 127.0.0.1.">
          <a className="btn sm" href="https://github.com/ggml-org/llama.cpp" target="_blank" rel="noreferrer noopener">Project</a>
        </Field>
      </div>
      <div className="set-group">
        <h4>Honest limits</h4>
        <div className="note" style={{ marginTop: 8 }}>
          A 2–9B local model is much smaller than frontier cloud models. It makes more factual and reasoning mistakes,
          and its knowledge stops at its training date. Think mode and Deep Research reduce some errors with tools and
          sources; they do not change the model's weights. Check anything important.
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ dialog */
export function SettingsDialog() {
  const section = useStore((s) => s.settingsOpen);
  const open = useStore((s) => s.openSettings);
  const settings = useStore((s) => s.settings);
  const save = useStore((s) => s.saveSettings);
  const dialog = useRef<HTMLDivElement>(null);
  const restore = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!section) return;
    restore.current = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") open(null);
      if (e.key === "Tab" && dialog.current) {
        const nodes = dialog.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!nodes.length) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      restore.current?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!section]);

  if (!section || !settings) return null;
  const current = SECTIONS.find((x) => x.id === section)!;
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && open(null)}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="Settings" ref={dialog} tabIndex={-1}>
        <div className="set-nav">
          <h2>Settings</h2>
          {SECTIONS.map((x) => (
            <button key={x.id} className={x.id === section ? "on" : ""} aria-current={x.id === section ? "page" : undefined}
              onClick={() => open(x.id)}>
              <x.icon size={16} /> {x.label}
            </button>
          ))}
        </div>
        <div className="set-body">
          <div className="set-head">
            <h3>{current.label}</h3>
            <button className="icon-btn" onClick={() => open(null)} aria-label="Close settings"><X size={18} /></button>
          </div>
          <div className="set-content scroll">
            {section === "general" && <General s={settings} save={save} />}
            {section === "models" && <Models s={settings} save={save} />}
            {section === "generation" && <Generation s={settings} save={save} />}
            {section === "research" && <Research s={settings} save={save} />}
            {section === "tools" && <Tools s={settings} save={save} />}
            {section === "memory" && <MemorySection s={settings} save={save} />}
            {section === "privacy" && <Privacy s={settings} save={save} />}
            {section === "about" && <About />}
          </div>
        </div>
      </div>
    </div>
  );
}

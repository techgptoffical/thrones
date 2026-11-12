import { ArrowDown, BookOpen, Calculator, Code2, Globe, Languages, Loader2, PenLine } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { greeting } from "../lib/format";
import { useStore } from "../store";
import type { Mode } from "../types";
import { Logo } from "./Logo";
import { MessageView } from "./MessageView";

const STARTERS: { icon: typeof Code2; label: string; prompt: string; mode: Mode }[] = [
  { icon: BookOpen, label: "Explain a hard idea simply", mode: "fast",
    prompt: "Explain how a transformer language model works, simply, with one everyday analogy." },
  { icon: Calculator, label: "Solve a problem step by step", mode: "think",
    prompt: "A loan of ₹8,50,000 at 9.5% annual interest is repaid monthly over 7 years. What is the EMI and the total interest paid? Show the working." },
  { icon: Code2, label: "Write and explain some code", mode: "fast",
    prompt: "Write a Python function that merges overlapping time intervals, then explain how it works and add three test cases." },
  { icon: Globe, label: "Research a current topic with sources", mode: "research",
    prompt: "What are the most capable open-weight language models that run on a 16 GB GPU right now, and how do they compare?" },
  { icon: Languages, label: "Hinglish mein samjhao", mode: "fast",
    prompt: "Mujhe Hinglish mein samjhao ki GPU aur CPU mein kya fark hota hai, aur AI ke liye GPU kyun zaroori hai." },
  { icon: PenLine, label: "Draft or rewrite something", mode: "fast",
    prompt: "Rewrite this to sound confident and concise: \"I think maybe we could possibly look at moving the launch, if that's okay with everyone.\"" },
];

function Welcome({ onStarter }: { onStarter: (prompt: string, mode: Mode) => void }) {
  const status = useStore((s) => s.status);
  const models = useStore((s) => s.models);
  const openSettings = useStore((s) => s.openSettings);
  const draftProject = useStore((s) => s.projects.find((p) => p.id === s.draftProjectId));
  const noModel = models.length > 0 && !models.some((m) => m.installed);
  const model = status?.resolved?.model_name;

  return (
    <div className="welcome scroll">
      <div className="welcome-inner">
        <div style={{ display: "grid", justifyItems: "center", color: "var(--text)" }}>
          <Logo size={38} />
        </div>
        <h1>
          {greeting()} <em>What’s on your mind?</em>
        </h1>
        <p className="sub">
          {draftProject ? `New chat in “${draftProject.name}”. ` : ""}
          {model ? `Running ${model} on this PC. Nothing leaves it unless you start Deep Research.` : "Private AI that runs on your own PC."}
        </p>
        {noModel || status?.runtime_installed === false ? (
          <div className="setup-card">
            <h3>{status?.runtime_installed === false ? "The inference runtime is missing" : "Choose a model to get started"}</h3>
            <p>
              {status?.runtime_installed === false
                ? "Thrones could not find llama.cpp in its runtime folder, so models cannot be loaded yet."
                : `Thrones needs one local model. For this PC the ${status?.profiles[status.recommended_profile]?.label ?? "Balanced"} profile is recommended. Downloads are several gigabytes and happen once.`}
            </p>
            <div>
              <button className="btn primary" onClick={() => openSettings("models")}>Open model setup</button>
            </div>
          </div>
        ) : (
          <div className="starters">
            {STARTERS.map((s) => (
              <button key={s.label} className="starter" onClick={() => onStarter(s.prompt, s.mode)} title={s.prompt}>
                <s.icon size={16} />
                <span>{s.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function Thread({ onStarter }: { onStarter: (prompt: string, mode: Mode) => void }) {
  const messages = useStore((s) => s.messages);
  const live = useStore((s) => (s.live && (s.liveConversationId === s.activeId || s.liveConversationId === null) ? s.live : null));
  const activeId = useStore((s) => s.activeId);
  const loading = useStore((s) => s.loadingConversation);
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const toBottom = useCallback((smooth = false) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  // Follow new text only while the reader is at the bottom; never yank them back while they read earlier content.
  useLayoutEffect(() => {
    if (pinned.current) toBottom();
  }, [messages, live, toBottom]);

  useEffect(() => {
    pinned.current = true;
    setShowJump(false);
    requestAnimationFrame(() => toBottom());
  }, [activeId, toBottom]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinned.current = distance < 80;
    setShowJump(distance > 320);
  };

  if (loading) {
    return (
      <div className="welcome">
        <Loader2 size={20} className="spin" style={{ color: "var(--text-3)" }} />
      </div>
    );
  }
  if (messages.length === 0 && !live) return <Welcome onStarter={onStarter} />;

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  return (
    <>
      <div className="thread scroll" ref={scroller} onScroll={onScroll}>
        <div className="thread-inner">
          {messages.map((m) => (
            <MessageView key={m.id} message={m} isLast={!live && m.id === lastAssistant?.id && m === messages[messages.length - 1]} />
          ))}
          {live && <MessageView key="live" message={live} live />}
        </div>
      </div>
      {showJump && (
        <button className="jump" onClick={() => { pinned.current = true; toBottom(true); }} aria-label="Jump to latest">
          <ArrowDown size={16} />
        </button>
      )}
    </>
  );
}

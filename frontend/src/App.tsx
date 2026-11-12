import { CloudOff, Download, PanelLeftOpen, SquarePen, WifiOff, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Composer, type ComposerHandle } from "./components/Composer";
import { Logo } from "./components/Logo";
import { Popover } from "./components/Popover";
import { SettingsDialog } from "./components/Settings";
import { Sidebar } from "./components/Sidebar";
import { Thread } from "./components/Thread";
import { useStore } from "./store";
import type { Mode } from "./types";

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  if (!toasts.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span>{t.text}</span>
          <button onClick={() => dismiss(t.id)} aria-label="Dismiss"><X size={15} /></button>
        </div>
      ))}
    </div>
  );
}

function TopBar() {
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const toggle = useStore((s) => s.toggleSidebar);
  const newChat = useStore((s) => s.newChat);
  const conversation = useStore((s) => s.conversations.find((c) => c.id === s.activeId));
  const settings = useStore((s) => s.settings);
  const online = useStore((s) => s.online);
  const openSettings = useStore((s) => s.openSettings);
  const documents = useStore((s) => s.documents);
  const removeDocument = useStore((s) => s.removeDocument);

  return (
    <header className="topbar">
      {!sidebarOpen && (
        <>
          <button className="icon-btn" onClick={toggle} aria-label="Open sidebar" title="Open sidebar (Ctrl+B)">
            <PanelLeftOpen size={18} />
          </button>
          <button className="icon-btn" onClick={() => newChat()} aria-label="New chat" title="New chat (Ctrl+Shift+O)">
            <SquarePen size={17} />
          </button>
        </>
      )}
      <span className="title">{conversation?.title ?? ""}</span>
      <span className="spacer" />
      {documents.length > 0 && (
        <Popover align="right"
          trigger={(t) => (
            <button className="chip" onClick={t} title="Documents attached to this conversation">
              {documents.length} document{documents.length === 1 ? "" : "s"}
            </button>
          )}>
          {() => (
            <div style={{ minWidth: 280 }}>
              <div className="menu-label">Used as context in this chat</div>
              {documents.map((d) => (
                <div key={d.id} className="menu-item" style={{ cursor: "default" }}>
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</span>
                    <span className="sub">{d.n_chars.toLocaleString()} characters indexed locally</span>
                  </span>
                  <button className="icon-btn sm" aria-label={`Remove ${d.name}`} onClick={() => void removeDocument(d.id)}>
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Popover>
      )}
      {settings?.offline_mode ? (
        <button className="chip" onClick={() => openSettings("privacy")} title="Offline mode is on. Chat and Think work; Deep Research and downloads are blocked.">
          <CloudOff size={14} /> Offline mode
        </button>
      ) : online === false ? (
        <span className="chip warn" title="No internet detected. Local chat still works; Deep Research cannot search.">
          <WifiOff size={14} /> No internet
        </span>
      ) : null}
      {conversation && (
        <Popover align="right"
          trigger={(t) => (
            <button className="icon-btn" onClick={t} aria-label="Export conversation" title="Export">
              <Download size={17} />
            </button>
          )}>
          {(close) => (
            <>
              <a className="menu-item" href={`/api/conversations/${conversation.id}/export?format=md`} onClick={close}>Export as Markdown</a>
              <a className="menu-item" href={`/api/conversations/${conversation.id}/export?format=json`} onClick={close}>Export as JSON</a>
            </>
          )}
        </Popover>
      )}
    </header>
  );
}

export default function App() {
  const ready = useStore((s) => s.ready);
  const bootError = useStore((s) => s.bootError);
  const boot = useStore((s) => s.boot);
  const settings = useStore((s) => s.settings);
  const composer = useRef<ComposerHandle>(null);
  const searchInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void boot();
  }, [boot]);

  // Appearance: theme, density and text size are applied to the document root.
  useEffect(() => {
    if (!settings) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = settings.theme === "dark" || (settings.theme === "system" && media.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    try {
      localStorage.setItem("thrones.theme", settings.theme);
    } catch {
      /* storage unavailable: the theme is still applied for this session */
    }
    document.documentElement.dataset.density = settings.density;
    document.documentElement.style.setProperty("--scale", String(settings.font_scale / 100));
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [settings]);

  // Keep engine state and connectivity fresh while the tab is visible.
  useEffect(() => {
    if (!ready) return;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      void useStore.getState().refreshStatus();
    };
    const net = () => document.visibilityState === "visible" && void useStore.getState().checkOnline();
    const a = window.setInterval(tick, 5000);
    const b = window.setInterval(net, 20000);
    window.addEventListener("online", net);
    window.addEventListener("offline", net);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
      window.removeEventListener("online", net);
      window.removeEventListener("offline", net);
    };
  }, [ready]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useStore.getState();
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        s.newChat();
        composer.current?.focus();
      } else if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (!s.sidebarOpen) s.toggleSidebar();
        requestAnimationFrame(() => searchInput.current?.focus());
      } else if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        s.toggleSidebar();
      } else if (mod && e.key === ",") {
        e.preventDefault();
        s.openSettings(s.settingsOpen ? null : "general");
      } else if (e.key === "Escape" && s.streaming && !s.settingsOpen) {
        void s.stop();
      } else if (mod && e.key === "/") {
        e.preventDefault();
        composer.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!ready) {
    return (
      <div className="boot">
        <div className="inner">
          <Logo size={40} />
          <h1>Thrones</h1>
          {bootError ? (
            <>
              <p>{bootError}</p>
              <button className="btn primary" onClick={() => void boot()}>Try again</button>
            </>
          ) : (
            <p>Starting…</p>
          )}
        </div>
      </div>
    );
  }

  const onStarter = (prompt: string, mode: Mode) => {
    useStore.getState().setMode(mode);
    composer.current?.setText(prompt);
  };

  return (
    <div className="app">
      <Sidebar ref={searchInput} />
      <main className="main">
        <TopBar />
        <Thread onStarter={onStarter} />
        <Composer ref={composer} />
      </main>
      <SettingsDialog />
      <Toasts />
    </div>
  );
}

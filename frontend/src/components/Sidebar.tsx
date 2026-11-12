import {
  ChevronDown, ChevronRight, Download, Folder, FolderInput, FolderMinus, Globe, MoreHorizontal, PanelLeftClose,
  Pencil, Plus, Search, Settings as SettingsIcon, SquarePen, Trash2,
} from "lucide-react";
import { forwardRef, useMemo, useState } from "react";
import { dayBucket } from "../lib/format";
import { useStore } from "../store";
import type { Conversation, Project } from "../types";
import { Logo } from "./Logo";
import { Popover } from "./Popover";

function ConfirmDialog({ title, body, action, onConfirm, onClose }: {
  title: string; body: string; action: string; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog small" role="alertdialog" aria-modal="true" aria-label={title}>
        <h3>{title}</h3>
        <p>{body}</p>
        <div className="row">
          <button className="btn" onClick={onClose} autoFocus>Cancel</button>
          <button className="btn danger" onClick={() => { onConfirm(); onClose(); }}>{action}</button>
        </div>
      </div>
    </div>
  );
}

function Item({ c, projects }: { c: Conversation; projects: Project[] }) {
  const active = useStore((s) => s.activeId === c.id);
  const isLive = useStore((s) => s.liveConversationId === c.id);
  const open = useStore((s) => s.openConversation);
  const rename = useStore((s) => s.renameConversation);
  const remove = useStore((s) => s.deleteConversation);
  const move = useStore((s) => s.moveConversation);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.title);
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const commit = () => {
    setEditing(false);
    const title = draft.trim();
    if (title && title !== c.title) void rename(c.id, title);
  };

  return (
    <div className={`sb-item${active ? " active" : ""}${menu ? " menu-open" : ""}`}>
      {editing ? (
        <input className="rename" value={draft} autoFocus aria-label="Conversation title"
          onChange={(e) => setDraft(e.target.value)} onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }} />
      ) : (
        <button className="sb-open" title={c.title} aria-current={active ? "page" : undefined}
          onClick={() => {
            void open(c.id);
            if (window.innerWidth <= 900) toggleSidebar();
          }}>
          {isLive && <span className="live-dot" aria-label="Generating" />}
          <span className="title">{c.title}</span>
        </button>
      )}
      {!editing && (
        <Popover align="right" onOpenChange={setMenu}
          trigger={(toggle) => (
            <button className="icon-btn sm more" onClick={toggle} aria-label={`Options for ${c.title}`}>
              <MoreHorizontal size={16} />
            </button>
          )}>
          {(close) => (
            <>
              <button className="menu-item" onClick={() => { close(); setDraft(c.title); setEditing(true); }}>
                <Pencil size={15} /> Rename
              </button>
              <a className="menu-item" href={`/api/conversations/${c.id}/export?format=md`} onClick={close}>
                <Download size={15} /> Export as Markdown
              </a>
              <a className="menu-item" href={`/api/conversations/${c.id}/export?format=json`} onClick={close}>
                <Download size={15} /> Export as JSON
              </a>
              {(projects.length > 0 || c.project_id) && <div className="menu-sep" />}
              {projects.filter((p) => p.id !== c.project_id).map((p) => (
                <button key={p.id} className="menu-item" onClick={() => { close(); void move(c.id, p.id); }}>
                  <FolderInput size={15} /> Move to {p.name}
                </button>
              ))}
              {c.project_id && (
                <button className="menu-item" onClick={() => { close(); void move(c.id, null); }}>
                  <FolderMinus size={15} /> Remove from project
                </button>
              )}
              <div className="menu-sep" />
              <button className="menu-item danger" onClick={() => { close(); setConfirm(true); }}>
                <Trash2 size={15} /> Delete
              </button>
            </>
          )}
        </Popover>
      )}
      {confirm && (
        <ConfirmDialog title="Delete this conversation?" action="Delete"
          body={`"${c.title}" and any documents attached to it will be permanently removed from this PC.`}
          onConfirm={() => void remove(c.id)} onClose={() => setConfirm(false)} />
      )}
    </div>
  );
}

function ProjectGroup({ p, items, projects }: { p: Project; items: Conversation[]; projects: Project[] }) {
  const [open, setOpen] = useState(true);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(p.name);
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const newChat = useStore((s) => s.newChat);
  const rename = useStore((s) => s.renameProject);
  const remove = useStore((s) => s.deleteProject);

  const commit = () => {
    setEditing(false);
    if (draft.trim() && draft.trim() !== p.name) void rename(p.id, draft.trim());
  };

  return (
    <div>
      <div className={`sb-item sb-project${menu ? " menu-open" : ""}`}>
        {editing ? (
          <input className="rename" value={draft} autoFocus aria-label="Project name"
            onChange={(e) => setDraft(e.target.value)} onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditing(false);
            }} />
        ) : (
          <button className="sb-open" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <Folder size={15} />
            <span className="title">{p.name}</span>
          </button>
        )}
        {!editing && (
          <Popover align="right" onOpenChange={setMenu}
            trigger={(toggle) => (
              <button className="icon-btn sm more" onClick={toggle} aria-label={`Options for project ${p.name}`}>
                <MoreHorizontal size={16} />
              </button>
            )}>
            {(close) => (
              <>
                <button className="menu-item" onClick={() => { close(); newChat(p.id); }}>
                  <SquarePen size={15} /> New chat in project
                </button>
                <button className="menu-item" onClick={() => { close(); setDraft(p.name); setEditing(true); }}>
                  <Pencil size={15} /> Rename
                </button>
                <div className="menu-sep" />
                <button className="menu-item danger" onClick={() => { close(); setConfirm(true); }}>
                  <Trash2 size={15} /> Delete project
                </button>
              </>
            )}
          </Popover>
        )}
      </div>
      {open && (
        <div className="sb-children">
          {items.length === 0 && <div className="sb-empty">No chats yet</div>}
          {items.map((c) => <Item key={c.id} c={c} projects={projects} />)}
        </div>
      )}
      {confirm && (
        <ConfirmDialog title="Delete this project?" action="Delete project"
          body={`"${p.name}" will be removed. Its chats are kept and move back to your main list.`}
          onConfirm={() => void remove(p.id)} onClose={() => setConfirm(false)} />
      )}
    </div>
  );
}

export const Sidebar = forwardRef<HTMLInputElement>(function Sidebar(_, searchRef) {
  const open = useStore((s) => s.sidebarOpen);
  const toggle = useStore((s) => s.toggleSidebar);
  const conversations = useStore((s) => s.conversations);
  const projects = useStore((s) => s.projects);
  const search = useStore((s) => s.search);
  const setSearch = useStore((s) => s.setSearch);
  const newChat = useStore((s) => s.newChat);
  const createProject = useStore((s) => s.createProject);
  const openSettings = useStore((s) => s.openSettings);
  const status = useStore((s) => s.status);
  const streaming = useStore((s) => s.streaming);
  const switching = useStore((s) => s.switchingModel);
  const [adding, setAdding] = useState(false);
  const [projectName, setProjectName] = useState("");

  const { research, grouped, byProject } = useMemo(() => {
    const loose = conversations.filter((c) => !c.project_id);
    const research = loose.filter((c) => c.kind === "research");
    const chats = loose.filter((c) => c.kind !== "research");
    const grouped: [string, Conversation[]][] = [];
    for (const c of chats) {
      const bucket = dayBucket(c.updated_at);
      const last = grouped[grouped.length - 1];
      if (last && last[0] === bucket) last[1].push(c);
      else grouped.push([bucket, [c]]);
    }
    const byProject = new Map<string, Conversation[]>();
    for (const c of conversations) {
      if (c.project_id) byProject.set(c.project_id, [...(byProject.get(c.project_id) ?? []), c]);
    }
    return { research, grouped, byProject };
  }, [conversations]);

  const engine = status?.engine;
  const engineLine1 = switching || engine?.loading
    ? "Loading model…"
    : engine?.loaded ? `${engine.model_name} ${engine.quantization ?? ""}` : status?.resolved?.model_name ?? "No model installed";
  const engineLine2 = switching || engine?.loading
    ? "Reading weights into memory"
    : engine?.loaded
      ? `${streaming ? "Generating" : "Ready"} · ${engine.context_length?.toLocaleString()} ctx · local`
      : status?.resolved?.model_name ? "Idle — loads on first message" : "Open Settings to download";
  const dotClass = switching || engine?.loading || streaming ? "busy" : engine?.loaded ? "ok" : "off";

  const submitProject = () => {
    const name = projectName.trim();
    setAdding(false);
    setProjectName("");
    if (name) void createProject(name);
  };

  return (
    <>
      {open && <div className="sb-backdrop" onClick={toggle} />}
      <nav className={`sidebar${open ? "" : " closed"}`} aria-label="Conversations" aria-hidden={!open}
        {...(!open ? { inert: true } : {})}>
        <div className="sb-head">
          <div className="brand">
            <Logo />
            <span className="brand-name">Thrones</span>
          </div>
          <button className="icon-btn" onClick={toggle} aria-label="Collapse sidebar" title="Collapse sidebar (Ctrl+B)">
            <PanelLeftClose size={18} />
          </button>
        </div>

        <div className="sb-actions">
          <button className="sb-row" onClick={() => newChat()}>
            <SquarePen size={17} /> New chat <span className="kbd">Ctrl ⇧ O</span>
          </button>
          <label className="sb-search">
            <Search size={17} />
            <input ref={searchRef} value={search} placeholder="Search chats" aria-label="Search chats"
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && (setSearch(""), e.currentTarget.blur())} />
          </label>
        </div>

        <div className="sb-scroll scroll">
          {!search && (
            <>
              <div className="sb-label">
                Projects
                <button onClick={() => setAdding(true)} aria-label="New project" title="New project">
                  <Plus size={14} />
                </button>
              </div>
              {adding && (
                <div className="sb-item">
                  <input className="rename" autoFocus placeholder="Project name" value={projectName}
                    aria-label="New project name" onChange={(e) => setProjectName(e.target.value)} onBlur={submitProject}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitProject();
                      if (e.key === "Escape") { setAdding(false); setProjectName(""); }
                    }} />
                </div>
              )}
              {projects.length === 0 && !adding && <div className="sb-empty">Group related chats here</div>}
              {projects.map((p) => (
                <ProjectGroup key={p.id} p={p} items={byProject.get(p.id) ?? []} projects={projects} />
              ))}
            </>
          )}

          {research.length > 0 && (
            <>
              <div className="sb-label">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Globe size={12} /> Research
                </span>
              </div>
              {research.map((c) => <Item key={c.id} c={c} projects={projects} />)}
            </>
          )}

          {grouped.map(([bucket, items]) => (
            <div key={bucket}>
              <div className="sb-label">{bucket}</div>
              {items.map((c) => <Item key={c.id} c={c} projects={projects} />)}
            </div>
          ))}
          {conversations.length === 0 && (
            <div className="sb-empty" style={{ paddingTop: 14 }}>
              {search ? "No chats match your search." : "Your conversations will appear here. They are stored only on this PC."}
            </div>
          )}
        </div>

        <div className="sb-foot">
          <button className="engine-row" onClick={() => openSettings("models")} title="Engine and hardware">
            <span className={`dot ${dotClass}`} />
            <span className="lines">
              <span className="l1" style={{ display: "block" }}>{engineLine1}</span>
              <span className="l2" style={{ display: "block" }}>{engineLine2}</span>
            </span>
          </button>
          <button className="sb-row" onClick={() => openSettings("general")}>
            <SettingsIcon size={17} /> Settings <span className="kbd">Ctrl ,</span>
          </button>
        </div>
      </nav>
    </>
  );
});

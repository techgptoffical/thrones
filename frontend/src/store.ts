import { create } from "zustand";
import { api, ApiError, streamChat } from "./api";
import type {
  Conversation, DocumentInfo, Message, Mode, ModelInfo, Project, Settings, Status, StreamEvent,
} from "./types";

export type SettingsSection =
  | "general" | "models" | "generation" | "research" | "tools" | "memory" | "privacy" | "about";

export interface Toast {
  id: number;
  kind: "info" | "error" | "success";
  text: string;
}

interface State {
  ready: boolean;
  bootError: string;
  status: Status | null;
  settings: Settings | null;
  models: ModelInfo[];
  online: boolean | null;

  conversations: Conversation[];
  projects: Project[];
  search: string;
  activeId: string | null;
  draftProjectId: string | null;
  messages: Message[];
  documents: DocumentInfo[];
  loadingConversation: boolean;

  mode: Mode;
  pendingDocs: DocumentInfo[];
  uploading: number;

  live: Message | null;
  liveConversationId: string | null;
  streaming: boolean;
  runId: string | null;
  notice: string;
  switchingModel: boolean;

  sidebarOpen: boolean;
  settingsOpen: SettingsSection | null;
  toasts: Toast[];

  boot: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshModels: () => Promise<void>;
  refreshConversations: () => Promise<void>;
  checkOnline: () => Promise<void>;
  setSearch: (q: string) => void;
  openConversation: (id: string) => Promise<void>;
  newChat: (projectId?: string | null) => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  moveConversation: (id: string, projectId: string | null) => Promise<void>;
  createProject: (name: string) => Promise<void>;
  renameProject: (id: string, name: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;

  setMode: (m: Mode) => void;
  selectModel: (id: string) => Promise<void>;
  saveSettings: (patch: Partial<Settings>) => Promise<void>;
  attach: (files: File[]) => Promise<void>;
  removePending: (id: string) => Promise<void>;
  removeDocument: (id: string) => Promise<void>;

  send: (text: string) => Promise<void>;
  regenerate: () => Promise<void>;
  stop: () => Promise<void>;

  toggleSidebar: () => void;
  openSettings: (s: SettingsSection | null) => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 1;
let abort: AbortController | null = null;
let searchTimer: number | undefined;

// Tokens arrive far faster than React should re-render; batch them per animation frame.
let pendingText = "";
let pendingReasoning = "";
let frame = 0;

const errorText = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Something went wrong.");

function blankAssistant(id: string, conversationId: string, mode: Mode): Message {
  return {
    id, conversation_id: conversationId, role: "assistant", content: "", reasoning: "", mode, steps: [], sources: [],
    metrics: {}, attachments: [], status: "streaming", created_at: Date.now() / 1000,
  };
}

export const useStore = create<State>((set, get) => {
  const flush = () => {
    frame = 0;
    const { live } = get();
    if (!live || (!pendingText && !pendingReasoning)) return;
    set({ live: { ...live, content: live.content + pendingText, reasoning: live.reasoning + pendingReasoning } });
    pendingText = "";
    pendingReasoning = "";
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(flush);
  };
  const patchLive = (patch: Partial<Message> | ((m: Message) => Partial<Message>)) => {
    flush();
    const { live } = get();
    if (!live) return;
    set({ live: { ...live, ...(typeof patch === "function" ? patch(live) : patch) } });
  };

  const onEvent = (ev: StreamEvent) => {
    switch (ev.type) {
      case "run":
        set({ runId: ev.run_id });
        break;
      case "start": {
        const s = get();
        const sameView = s.activeId === ev.conversation_id || s.activeId === null;
        const live = { ...(s.live ?? blankAssistant("", "", ev.mode)), id: ev.assistant_message_id,
          conversation_id: ev.conversation_id, mode: ev.mode };
        if (sameView) {
          const messages = s.messages.filter((m) => !m.id.startsWith("tmp-") && m.id !== ev.user_message.id);
          set({ activeId: ev.conversation_id, messages: [...messages, ev.user_message], live,
            liveConversationId: ev.conversation_id, pendingDocs: [] });
        } else {
          set({ live, liveConversationId: ev.conversation_id });
        }
        void get().refreshConversations();
        break;
      }
      case "token":
        pendingText += ev.text;
        schedule();
        break;
      case "reasoning":
        pendingReasoning += ev.text;
        schedule();
        break;
      case "content_reset":
        pendingText = "";
        patchLive({ content: "" });
        break;
      case "content_replace":
        pendingText = "";
        patchLive({ content: ev.text });
        break;
      case "step":
        patchLive((m) => {
          const i = m.steps.findIndex((x) => x.id === ev.step.id);
          const steps = i >= 0 ? m.steps.map((x, j) => (j === i ? ev.step : x)) : [...m.steps, ev.step];
          return { steps };
        });
        break;
      case "sources":
        patchLive({ sources: ev.sources });
        break;
      case "engine":
        set((s) => (s.status ? { status: { ...s.status, engine: ev.status } } : {}));
        break;
      case "title":
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === ev.conversation_id ? { ...c, title: ev.title } : c)),
        }));
        break;
      case "notice":
        set({ notice: ev.message });
        break;
      case "error":
        patchLive({ error: ev.message });
        break;
      case "done": {
        flush();
        const s = get();
        const final: Message = { ...ev.message, error: s.live?.error };
        if (s.activeId === final.conversation_id) {
          set({ messages: [...s.messages.filter((m) => m.id !== final.id), final] });
        }
        set({ live: null, liveConversationId: null, streaming: false, runId: null, notice: "" });
        void get().refreshConversations();
        void get().refreshStatus();
        break;
      }
    }
  };

  const run = async (content: string, regenerate: boolean) => {
    const s = get();
    if (s.streaming) return;
    const conversationId = s.activeId;
    const docIds = s.pendingDocs.map((d) => d.id);
    abort = new AbortController();
    pendingText = "";
    pendingReasoning = "";

    const optimistic: Message[] = regenerate
      ? (() => {
          const lastUser = [...s.messages].reverse().find((m) => m.role === "user");
          return lastUser ? s.messages.slice(0, s.messages.indexOf(lastUser) + 1) : s.messages;
        })()
      : [...s.messages, {
          id: "tmp-user", conversation_id: conversationId ?? "", role: "user", content, reasoning: "", mode: s.mode,
          steps: [], sources: [], metrics: {}, status: "complete", created_at: Date.now() / 1000,
          attachments: s.pendingDocs.map((d) => ({ id: d.id, name: d.name, size: d.size })),
        }];
    set({ messages: optimistic, live: blankAssistant("tmp-live", conversationId ?? "", s.mode),
      liveConversationId: conversationId, streaming: true, notice: "" });

    try {
      await streamChat(
        { conversation_id: conversationId, content, mode: s.mode, model_id: "", document_ids: docIds, regenerate,
          project_id: conversationId ? null : s.draftProjectId },
        onEvent, abort.signal,
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) get().toast(errorText(e), "error");
    } finally {
      // If the stream ended without a "done" event (network drop, abort), reconcile with what was saved.
      if (get().streaming) {
        flush();
        const id = get().liveConversationId ?? get().activeId;
        set({ live: null, liveConversationId: null, streaming: false, runId: null, notice: "" });
        if (id && get().activeId === id) {
          try {
            const data = await api.conversation(id);
            set({ messages: data.messages, documents: data.documents });
          } catch {
            /* the conversation list refresh below will surface a real outage */
          }
        }
        void get().refreshConversations();
      }
      abort = null;
    }
  };

  return {
    ready: false, bootError: "", status: null, settings: null, models: [], online: null,
    conversations: [], projects: [], search: "", activeId: null, draftProjectId: null, messages: [], documents: [],
    loadingConversation: false, mode: "fast", pendingDocs: [], uploading: 0,
    live: null, liveConversationId: null, streaming: false, runId: null, notice: "", switchingModel: false,
    // innerWidth can be 0 while the window is still hidden; only start collapsed on a genuinely narrow screen.
    sidebarOpen: !(window.innerWidth > 0 && window.innerWidth <= 900), settingsOpen: null, toasts: [],

    boot: async () => {
      try {
        const [status, settings, models, list] = await Promise.all([
          api.status(), api.settings(), api.models(), api.conversations(),
        ]);
        set({ status, settings, models: models.models, conversations: list.conversations, projects: list.projects,
          ready: true, bootError: "" });
        void get().checkOnline();
      } catch (e) {
        set({ bootError: errorText(e) });
      }
    },
    refreshStatus: async () => {
      try {
        set({ status: await api.status() });
      } catch {
        /* transient; the next poll retries */
      }
    },
    refreshModels: async () => {
      try {
        set({ models: (await api.models()).models });
      } catch {
        /* transient */
      }
    },
    refreshConversations: async () => {
      try {
        const list = await api.conversations(get().search);
        set({ conversations: list.conversations, projects: list.projects });
      } catch {
        /* transient */
      }
    },
    checkOnline: async () => {
      try {
        set({ online: (await api.connectivity()).online });
      } catch {
        set({ online: null });
      }
    },
    setSearch: (q) => {
      set({ search: q });
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => void get().refreshConversations(), 180);
    },

    openConversation: async (id) => {
      if (get().activeId === id) return;
      set({ activeId: id, messages: [], documents: [], loadingConversation: true, pendingDocs: [], draftProjectId: null });
      try {
        const data = await api.conversation(id);
        if (get().activeId !== id) return; // user moved on while this was loading
        const liveId = get().live?.id;
        set({ messages: data.messages.filter((m) => m.id !== liveId), documents: data.documents,
          loadingConversation: false });
      } catch (e) {
        if (get().activeId === id) set({ loadingConversation: false, activeId: null });
        get().toast(errorText(e), "error");
      }
    },
    newChat: (projectId = null) =>
      set({ activeId: null, messages: [], documents: [], pendingDocs: [], draftProjectId: projectId,
        loadingConversation: false }),
    renameConversation: async (id, title) => {
      try {
        const { conversation } = await api.patchConversation(id, { title });
        set((s) => ({ conversations: s.conversations.map((c) => (c.id === id ? conversation : c)) }));
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },
    deleteConversation: async (id) => {
      if (get().liveConversationId === id) await get().stop();
      try {
        await api.deleteConversation(id);
        if (get().activeId === id) get().newChat();
        await get().refreshConversations();
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },
    moveConversation: async (id, projectId) => {
      try {
        await api.patchConversation(id, projectId ? { project_id: projectId } : { clear_project: true });
        await get().refreshConversations();
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },
    createProject: async (name) => {
      try {
        await api.createProject(name);
        await get().refreshConversations();
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },
    renameProject: async (id, name) => {
      try {
        await api.renameProject(id, name);
        await get().refreshConversations();
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },
    deleteProject: async (id) => {
      try {
        await api.deleteProject(id);
        if (get().draftProjectId === id) set({ draftProjectId: null });
        await get().refreshConversations();
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },

    setMode: (mode) => set({ mode }),
    selectModel: async (id) => {
      if (get().streaming) {
        get().toast("Stop the current response before switching models.", "info");
        return;
      }
      set({ switchingModel: true });
      try {
        const settings = await api.saveSettings({ model_id: id });
        set({ settings });
        await api.loadEngine();
      } catch (e) {
        get().toast(errorText(e), "error");
      } finally {
        set({ switchingModel: false });
        await Promise.all([get().refreshStatus(), get().refreshModels()]);
      }
    },
    saveSettings: async (patch) => {
      const before = get().settings;
      if (before) set({ settings: { ...before, ...patch } });
      try {
        set({ settings: await api.saveSettings(patch) });
        if ("offline_mode" in patch) void get().checkOnline();
        if ("profile" in patch || "model_id" in patch || "context_length" in patch || "gpu_layers" in patch) {
          void get().refreshStatus();
        }
      } catch (e) {
        set({ settings: before });
        get().toast(errorText(e), "error");
      }
    },
    attach: async (files) => {
      for (const file of files) {
        set((s) => ({ uploading: s.uploading + 1 }));
        try {
          const doc = await api.uploadDocument(file, get().activeId);
          set((s) => ({ pendingDocs: [...s.pendingDocs, doc] }));
        } catch (e) {
          get().toast(`${file.name}: ${errorText(e)}`, "error");
        } finally {
          set((s) => ({ uploading: s.uploading - 1 }));
        }
      }
    },
    removePending: async (id) => {
      set((s) => ({ pendingDocs: s.pendingDocs.filter((d) => d.id !== id) }));
      try {
        await api.deleteDocument(id);
      } catch {
        /* already gone */
      }
    },
    removeDocument: async (id) => {
      try {
        await api.deleteDocument(id);
        set((s) => ({ documents: s.documents.filter((d) => d.id !== id) }));
      } catch (e) {
        get().toast(errorText(e), "error");
      }
    },

    send: async (text) => {
      const content = text.trim();
      if (!content) return;
      const docs = get().pendingDocs;
      await run(content, false);
      if (docs.length) {
        const id = get().activeId;
        if (id) {
          try {
            set({ documents: (await api.conversation(id)).documents });
          } catch {
            /* non-critical */
          }
        }
      }
    },
    regenerate: () => run("", true),
    stop: async () => {
      const { runId, streaming } = get();
      if (!streaming) return;
      if (runId) {
        try {
          await api.stopRun(runId); // the server answers with a final "done: stopped" event
        } catch {
          abort?.abort();
        }
        window.setTimeout(() => {
          if (get().streaming && get().runId === runId) abort?.abort();
        }, 4000);
      } else {
        abort?.abort();
      }
    },

    toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    openSettings: (section) => set({ settingsOpen: section }),
    toast: (text, kind = "info") => {
      const id = toastSeq++;
      set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }));
      window.setTimeout(() => get().dismissToast(id), kind === "error" ? 8000 : 4000);
    },
    dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  };
});

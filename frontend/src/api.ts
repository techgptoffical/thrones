import type {
  Conversation, DocumentInfo, DownloadState, EngineStatus, Memory, Message, Mode, ModelInfo, Project, Settings,
  Status, StreamEvent,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the Thrones engine. Is the app still running?", 0);
  }
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, resp.status);
  }
  return resp.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  status: () => request<Status>("/api/status"),
  connectivity: () => request<{ online: boolean; reason: string }>("/api/connectivity"),

  settings: () => request<Settings>("/api/settings"),
  saveSettings: (patch: Partial<Settings>) => request<Settings>("/api/settings", json("PATCH", patch)),
  resetSettings: () => request<Settings>("/api/settings/reset", json("POST")),

  models: () => request<{ models: ModelInfo[] }>("/api/models"),
  downloadModel: (id: string) => request<DownloadState>(`/api/models/${id}/download`, json("POST")),
  cancelDownload: (id: string) => request<{ ok: boolean }>(`/api/models/${id}/cancel`, json("POST")),
  deleteModel: (id: string) => request<{ ok: boolean }>(`/api/models/${id}`, json("DELETE")),
  loadEngine: (model_id = "") => request<EngineStatus>("/api/engine/load", json("POST", { model_id })),
  unloadEngine: () => request<EngineStatus>("/api/engine/unload", json("POST")),

  conversations: (search = "") =>
    request<{ conversations: Conversation[]; projects: Project[] }>(
      `/api/conversations${search ? `?search=${encodeURIComponent(search)}` : ""}`,
    ),
  conversation: (id: string) =>
    request<{ conversation: Conversation; messages: Message[]; documents: DocumentInfo[] }>(`/api/conversations/${id}`),
  patchConversation: (id: string, body: { title?: string; project_id?: string; clear_project?: boolean }) =>
    request<{ conversation: Conversation }>(`/api/conversations/${id}`, json("PATCH", body)),
  deleteConversation: (id: string) => request<{ ok: boolean }>(`/api/conversations/${id}`, json("DELETE")),
  deleteAllConversations: () => request<{ ok: boolean }>("/api/data/conversations", json("DELETE")),

  createProject: (name: string) => request<Project>("/api/projects", json("POST", { name })),
  renameProject: (id: string, name: string) => request<{ ok: boolean }>(`/api/projects/${id}`, json("PATCH", { name })),
  deleteProject: (id: string) => request<{ ok: boolean }>(`/api/projects/${id}`, json("DELETE")),

  memories: () => request<{ memories: Memory[]; enabled: boolean }>("/api/memory"),
  addMemory: (content: string) => request<Memory>("/api/memory", json("POST", { content })),
  updateMemory: (id: string, body: { content?: string; enabled?: boolean }) =>
    request<{ ok: boolean }>(`/api/memory/${id}`, json("PATCH", body)),
  deleteMemory: (id: string) => request<{ ok: boolean }>(`/api/memory/${id}`, json("DELETE")),
  clearMemories: () => request<{ ok: boolean }>("/api/memory", json("DELETE")),

  uploadDocument: (file: File, conversationId: string | null) => {
    const form = new FormData();
    form.append("file", file);
    form.append("conversation_id", conversationId ?? "");
    return request<DocumentInfo>("/api/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<{ ok: boolean }>(`/api/documents/${id}`, json("DELETE")),

  stopRun: (runId: string) => request<{ stopped: boolean }>(`/api/chat/${runId}/stop`, json("POST")),
};

export interface ChatBody {
  conversation_id: string | null;
  content: string;
  mode: Mode;
  model_id: string;
  document_ids: string[];
  regenerate: boolean;
  project_id: string | null;
}

/** POST /api/chat and deliver each server-sent event as it arrives. */
export async function streamChat(body: ChatBody, onEvent: (e: StreamEvent) => void, signal: AbortSignal): Promise<void> {
  const resp = await fetch("/api/chat", { ...json("POST", body), signal });
  if (!resp.ok || !resp.body) {
    let detail = `Request failed (${resp.status})`;
    try {
      const data = await resp.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, resp.status);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            onEvent(JSON.parse(line.slice(6)) as StreamEvent);
          } catch {
            /* ignore a malformed frame */
          }
        }
      }
    }
  }
}

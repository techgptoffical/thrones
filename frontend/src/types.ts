export type Mode = "fast" | "think" | "research";

export interface Step {
  id: string;
  kind: string;
  title: string;
  detail: string;
  state: "running" | "done" | "error" | "skipped" | "stopped";
  t?: number;
  t_end?: number;
}

export interface Source {
  n?: number;
  kind: "web" | "document";
  title: string;
  url: string;
  site?: string;
  date?: string;
  snippet?: string;
  cited?: boolean;
}

export interface Metrics {
  model_id?: string;
  model_name?: string;
  quantization?: string;
  context_length?: number;
  first_token_s?: number | null;
  total_s?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  tokens_per_second?: number | null;
  model_calls?: number;
  tool_calls?: number;
  peak_vram_mb?: number | null;
  peak_ram_mb?: number | null;
  load_seconds?: number | null;
}

export interface Attachment {
  id: string;
  name: string;
  size: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  mode: Mode;
  steps: Step[];
  sources: Source[];
  metrics: Metrics;
  attachments: Attachment[];
  status: "complete" | "streaming" | "stopped" | "error";
  created_at: number;
  error?: string;
}

export interface Conversation {
  id: string;
  title: string;
  kind: "chat" | "research";
  project_id: string | null;
  created_at: number;
  updated_at: number;
}

export interface Project {
  id: string;
  name: string;
  created_at: number;
}

export interface DocumentInfo {
  id: string;
  name: string;
  size: number;
  n_chunks: number;
  n_chars: number;
  conversation_id: string | null;
}

export interface Memory {
  id: string;
  content: string;
  enabled: number;
  source: string;
  created_at: number;
}

export interface Gpu {
  name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_free_mb: number;
  driver: string;
}

export interface Hardware {
  os: string;
  cpu: string;
  cpu_cores: number;
  cpu_threads: number;
  ram_total_gb: number;
  ram_available_gb: number;
  gpus: Gpu[];
  has_gpu: boolean;
}

export interface EngineStatus {
  loaded: boolean;
  loading: string;
  provider: string;
  model_id?: string;
  model_name?: string;
  quantization?: string;
  context_length?: number;
  gpu_layers?: number;
  load_seconds?: number;
  model_vram_mb?: number | null;
  warnings?: string[];
  fallback?: boolean;
  last_load_failure?: string;
  busy?: boolean;
}

export interface ProfileInfo {
  label: string;
  description: string;
  model_id: string;
  context_length: number;
}

export interface Status {
  app: string;
  version: string;
  engine: EngineStatus;
  hardware: Hardware;
  recommended_profile: string;
  resolved: { model_id?: string; model_name?: string; context_length?: number; gpu_layers?: number; profile?: string; error?: string } | null;
  runtime_installed: boolean;
  paths: { data: string; models: string; database: string; uploads: string };
  profiles: Record<string, ProfileInfo>;
}

export interface DownloadState {
  state: "downloading" | "done" | "paused" | "error";
  received: number;
  total: number;
  speed_bps: number;
  error: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  family: string;
  publisher: string;
  base_repo: string;
  gguf_repo: string;
  file: string;
  size_bytes: number;
  license: string;
  parameters: string;
  quantization: string;
  tier: string;
  native_context: number;
  notes: string;
  lora_file?: string;
  adapter?: string;
  base_name?: string;
  experimental?: boolean;
  installed: boolean;
  loaded: boolean;
  compatibility: { level: "ok" | "warn" | "bad"; message: string };
  download: DownloadState | null;
}

export interface Settings {
  theme: "system" | "light" | "dark";
  density: "comfortable" | "compact";
  font_scale: number;
  profile: string;
  model_id: string;
  context_length: number;
  gpu_layers: number;
  idle_unload_minutes: number;
  temperature: number | null;
  top_p: number | null;
  top_k: number | null;
  max_tokens: number;
  style: "balanced" | "direct" | "creative" | "technical";
  custom_instructions: string;
  show_reasoning: boolean;
  think_max_tool_calls: number;
  think_time_budget_s: number;
  think_token_budget: number;
  think_verify: boolean;
  think_reasoning_budget: number;
  offline_mode: boolean;
  web_research_enabled: boolean;
  search_provider: "duckduckgo" | "searxng" | "brave";
  searxng_url: string;
  brave_api_key: string;
  research_max_sources: number;
  research_max_rounds: number;
  research_time_budget_s: number;
  python_tool_enabled: boolean;
  memory_enabled: boolean;
}

export type StreamEvent =
  | { type: "run"; run_id: string }
  | { type: "start"; conversation_id: string; user_message: Message; assistant_message_id: string; mode: Mode }
  | { type: "step"; step: Step }
  | { type: "token"; text: string }
  | { type: "reasoning"; text: string }
  | { type: "content_reset" }
  | { type: "content_replace"; text: string }
  | { type: "sources"; sources: Source[] }
  | { type: "engine"; status: EngineStatus }
  | { type: "title"; conversation_id: string; title: string }
  | { type: "notice"; message: string }
  | { type: "error"; message: string }
  | { type: "done"; status: Message["status"]; message: Message };

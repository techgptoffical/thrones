# Thrones architecture

Thrones 1.0 is a local-first assistant: one Python process that serves the interface and an API, and one child process (`llama-server`) that runs the language model. Everything binds to `127.0.0.1`. The only outbound traffic is Deep Research (search queries and the pages it reads) and model downloads, both user-initiated and both blocked by Offline mode.

```
 Browser (React UI) ──HTTP/SSE──▶ Thrones backend (FastAPI, 127.0.0.1:8765)
                                     │
                     ┌───────────────┼─────────────────────────────────┐
                     │               │                                 │
              Reasoning layer   Knowledge layer                   Tool layer
              fast / think /    SQLite: chats, memory,           calculator, python (opt-in),
              research          documents (FTS5)                  save_memory, web search+fetch
                     │
              Model runtime: ModelManager ──▶ ChatProvider (llama.cpp)
                                                 │  OpenAI-compatible HTTP, 127.0.0.1:8766
                                                 ▼
                                          llama-server.exe  (child process, Windows job object)
                                                 │
                                          GGUF weights on local SSD (models/)
```

## Layers and where they live

| Layer (directive) | Code | Responsibility |
|---|---|---|
| A — Language model | `backend/thrones/runtime/` | `ChatProvider` protocol, `LlamaCppProvider`, `ModelManager` (selection, load, fallback, idle unload, downloads, memory sampling) |
| B — Orchestration | `backend/thrones/reasoning/engine.py`, `prompts.py` | Turn lifecycle, context budgeting, mode workflows, bounded tool loop, metrics |
| C — Tools | `backend/thrones/tools/`, `backend/thrones/research/` | Tool registry with budgets and de-duplication; calculator; Python runner; search adapters; safe fetcher; extractor; research pipeline |
| D — Knowledge & memory | `backend/thrones/db.py`, `retrieval/documents.py` | SQLite persistence, user memory, document ingestion and BM25 retrieval |
| E — Interface | `frontend/src/` | React + TypeScript + Zustand; SSE streaming client |
| F — Model development | `evals/`, `training/` (plan) | Benchmark harness, eval set, training plan |

## Request lifecycle (one chat turn)

1. `POST /api/chat` creates a background task and returns a Server-Sent Events stream. The task id is sent first (`run` event) so the UI can stop it.
2. `run_turn` saves the user message, creates an assistant row with `status=streaming`, and takes the **generation lock** (one generation at a time, matching the single llama.cpp slot).
3. `ModelManager.ensure_loaded` starts or reuses `llama-server` with the profile's model, context and GPU layers. If the load fails it retries down a fallback ladder (half context → 4096 → CPU only) and reports which setting was used.
4. Context is assembled under a token budget: system prompt (identity, style, date, language rules, memories, custom instructions) → attached-document context → recent history. History that does not fit is summarised by the model once and cached on the conversation (`summary`, `summary_count`).
5. The selected mode runs (below). Every visible step is emitted as a `step` event; tokens stream as `token` / `reasoning` events.
6. On completion, stop or error, the assistant row is updated with content, reasoning, steps, sources, and **measured** metrics (llama.cpp timings, wall-clock, peak VRAM via `nvidia-smi`, peak engine RSS via `psutil`).
7. Closing the HTTP stream (browser closed, Stop pressed) cancels the task; the in-flight request to llama-server is dropped, which stops generation.

## Modes — what actually changes

| | Fast | Think | Deep Research |
|---|---|---|---|
| Model thinking (`enable_thinking`) | off | on | off for planning/extraction, on for the final report |
| Model calls per turn | 1 (+1 per tool round, +1 title) | plan + solve loop + independent verify (+ revise) | plan + 1 per source + gap check + write |
| Tools | calculator, save_memory (≤ 2 calls) | calculator, save_memory, Python if enabled (user budget, default 6) | search + fetch, run by code, not by the model |
| Network | never | never | yes (blocked by Offline mode) |
| Budgets | 120 s | user time, token and tool-call budgets | user time, source and round budgets |

**Think** is a bounded planner → executor → verifier:
- *Plan*: a separate low-temperature call writes 2–5 steps and the main risk. The plan is shown and injected into the solver's system prompt.
- *Execute*: thinking on, tool loop with a per-request `ToolSet` (call budget, identical-call refusal, per-tool timeouts). Text the model writes before a tool call is discarded from the visible answer.
- *Verify*: a fresh call, given only the question and the draft, checks for errors and may recompute numbers with its own calculator budget. It must end with `VERDICT: PASS` or `VERDICT: FAIL - …`.
- *Revise*: on FAIL, one rewrite with the reviewer's specific issue. No loops.

**Deep Research** is driven by code; the model only answers narrow questions (see `research/pipeline.py`):
plan queries → search (pluggable provider) → de-duplicate and interleave results → fetch in parallel (SSRF-guarded, robots.txt, per-host throttle, size and time caps) → extract readable text (trafilatura / pypdf) → per-source evidence notes → optional gap check and second search round → cited report → **citation sanitizer** that removes any `[n]` outside the real source list and any link to a page that was not fetched.

## Security model

- **Network surface:** API on 127.0.0.1 only, `TrustedHostMiddleware` (blocks DNS-rebinding), CORS limited to the dev server origin. llama-server on 127.0.0.1 with its web UI disabled.
- **Untrusted web content:** the model has *no tools* while it reads fetched pages; page text is wrapped in explicit untrusted-data markers; sources and URLs in the final answer are validated against what was actually fetched.
- **SSRF:** every URL and redirect hop must be http(s), default port, no credentials, and resolve only to public addresses (private, loopback, link-local, CGNAT, multicast, reserved and IPv4-mapped variants are refused).
- **Code execution:** the calculator evaluates a whitelisted AST only. The Python tool is off by default, clearly labelled as *not a sandbox*, and runs with `-I`, a temp directory, no stdin and a 15 s timeout.
- **Files:** uploads are parsed, never executed; stored under `data/uploads`; deleting a conversation deletes its documents.
- **Process lifetime:** llama-server is placed in a Windows job object with kill-on-close, so a crashed or force-closed backend cannot strand VRAM. A stale engine from a previous session on our port is also reaped at startup.

## Data

One SQLite file (`data/thrones.db`, WAL mode): `settings`, `conversations`, `messages` (content, reasoning, steps, sources, metrics as JSON), `projects`, `memories`, `documents`, `chunks` (FTS5, unicode61 tokenizer). Retrieval is BM25 over ~1400-character overlapping chunks; small documents are passed whole.

## Key decisions

| Decision | Why | Alternative considered |
|---|---|---|
| llama.cpp `llama-server` as a child process | Official Windows CUDA 13 builds; first-class Qwen3.5 and gpt-oss support; OpenAI-compatible streaming with `reasoning_content` and tool calls; no Python CUDA stack needed for inference | **Ollama**: Unsloth documents that Qwen3.5 GGUFs do not load in Ollama because of the separate vision projector. **vLLM/SGLang**: Linux-first, need nightly builds for Qwen3.5. |
| One process, one model, one slot | 16 GB system RAM and 16 GB VRAM; parallel slots would split the KV cache and slow every reply | Multiple slots for concurrent chats |
| SSE over WebSocket | One-directional streaming; works through the Vite proxy; stop is a separate POST and closing the stream also cancels | WebSocket |
| SQLite FTS5 instead of a vector DB | Zero extra dependencies or model downloads; BM25 is strong for "find the passage that mentions X" in the user's own files | Embedding model + vector store (planned option, see IMPLEMENTATION_PLAN) |
| Research pipeline driven by code, not by a free agent loop | Predictable time and cost on a 9B model; prevents a page from steering tool use; every citation is verifiable | Model-driven browse/search tool loop |
| No text vision / image input in 1.0 | Vision projector (`mmproj`) costs ~0.9 GB VRAM and the UI flow is not built | Load `mmproj` on demand (planned) |

## Extending

- **New model:** add an entry to `config/models.json` (GGUF URL, size, license). It appears in Settings with a download button and compatibility check.
- **New runtime:** implement `ChatProvider` (`start`, `stop`, `stream`, `count_tokens`) and pass it to `ModelManager`.
- **New tool:** create a `Tool` (JSON schema + async handler + timeout) and add it to the `ToolSet` in `engine.run_turn` for the modes that should have it.
- **New search provider:** implement `search(query, max_results) -> list[SearchResult]` and register it in `research/search.get_provider`.

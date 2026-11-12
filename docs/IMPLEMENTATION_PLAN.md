# Thrones implementation plan

Phases follow the project directive. Status reflects what was built **and tested**; details and evidence are in `PROGRESS.md`.

## Phase 1 — Working local AI  ✅ complete

| Milestone | Status |
|---|---|
| Hardware and tool inspection; isolated environments on D: | done |
| llama.cpp CUDA runtime (official b12289 release) in `runtime/` | done |
| Qwen3.5 2B / 4B / 9B Q4_K_M downloaded and verified by byte size | done |
| Provider abstraction + model manager (profiles, fallback ladder, idle unload, crash-safe child process) | done |
| Streaming chat API (SSE), stop, regenerate, persistence (SQLite) | done |
| Fast and Think modes with real backend differences | done |
| UI: sidebar, search, projects, composer, markdown/code/math, light & dark | done |
| Offline operation demonstrated (Offline-mode e2e check; Fast/Think never use the network) | done |

## Phase 2 — Online research  ✅ first version complete

| Milestone | Status |
|---|---|
| Pluggable search (DuckDuckGo default, SearXNG, Brave API) | done |
| SSRF-safe fetcher, robots.txt, throttling, extraction (HTML + PDF) | done |
| Deep Research pipeline with gap check, citations, sanitizer | done |
| Research steps and sources in the UI, research history | done |
| Freshness weighting of sources by date; per-claim conflict table | next |

## Phase 3 — Model development  ◐ in progress

| Milestone | Status |
|---|---|
| Model comparison on this machine (`evals/run_bench.py`) | done — see MODEL_RESEARCH.md |
| Eval set v1 (39 deterministic items) | done |
| Training data pipeline + licence manifest | planned (TRAINING_PLAN §3) |
| First LoRA on Qwen3.5 4B, evaluated against base | planned |
| Adapter version management in the catalog | planned |

Dependencies: WSL2 or Unsloth Studio environment; reviewed dataset; held-out set.

## Phase 4 — Advanced capabilities  ○ planned

Ordered by expected user value per effort:

1. **Embedding retrieval** alongside BM25 for paraphrased questions over documents (small local embedding model, e.g. a 0.1–0.6B GGUF, loaded only when documents exist).
2. **Vision input** via the Qwen3.5 `mmproj` projector (+~0.9 GB VRAM) for screenshots and photos.
3. **Public benchmark subsets** in `evals/` (GSM8K, IFEval, HumanEval, MMLU-Pro) for regression tracking.
4. **Research quality:** date-aware ranking, per-claim conflict table, PDF-first for scholarly queries.
5. **Long context:** 32 k on the 9B where VRAM allows (measure first), better summarisation of long chats.
6. **MCP tool servers** with per-tool permission prompts, timeouts and an audit log.
7. **Per-message edit and branch.**

## Phase 5 — Public release  ○ planned

1. Windows desktop shell (Tauri) wrapping the existing server — only after Phase 1–2 stay stable.
2. Installer with first-run wizard: hardware detection → recommended profile → model download.
3. Signed binaries; auto-update off by default.
4. Fresh-machine install tests (GPU and CPU-only), Playwright UI suite, soak test.
5. Public repository: README, licences, security policy, contribution guide, model and eval reports.

## Working rules

- The app stays runnable after every change; every feature lands with a test or a recorded manual check.
- No mock endpoints or decorative controls. Unavailable features are labelled "Not available".
- No performance number appears in docs or the UI unless it was measured on the stated hardware.

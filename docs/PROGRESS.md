# Thrones — progress

Last updated: 12 November 2026. "Done" means implemented **and** verified by the test named in the last column. Anything not verified says so.

## Feature status

### Core (Phase 1)

| Feature | Status | Verified by |
|---|---|---|
| Local inference via llama.cpp (CUDA 13.5 build b12289) | Done | e2e #2, browser session, benchmarks |
| Model catalog: Qwen3.5 9B / 4B / 2B (Q4_K_M), gpt-oss 20B (MXFP4) | Done | all four downloaded, byte sizes match catalog, all four benchmarked |
| In-app model download with progress, pause/resume, disk-space check | Implemented | **not exercised end-to-end in the UI** (models were pre-downloaded); offline refusal verified (e2e #12) |
| Hardware detection, profiles (Auto/Lite/Balanced/High), compatibility labels | Done | Settings screen read in browser; e2e #1 |
| Load fallback ladder (smaller context → CPU) | Implemented | **not forced in a test yet** |
| Idle unload | Implemented | not timed in a test |
| Engine dies with the app (Windows job object); stale engine reaped at start | Done | manual: force-killed backend → engine gone, VRAM back to idle |
| Streaming chat, stop, regenerate | Done | e2e #2, #4, #5; browser |
| Conversation persistence, titles, search, rename, delete, projects | Done | unit tests; e2e #3; browser |
| Export (conversation MD/JSON, full data JSON) | Done | e2e #13 |
| Context management (budgeted history + cached summary of older turns) | Implemented | unit-level only; **no long-conversation e2e yet** |
| Fast mode | Done | e2e #2, #7 |
| Think mode: plan → tools → verify → revise, with time/token/tool budgets and a per-step reasoning limit | Done | e2e #6, #7; browser (EMI problem); hard-set app eval 24/26 with no empty answers |
| Calculator tool (safe AST) | Done | unit tests; e2e #6 |
| Python tool (opt-in, not a sandbox) | Implemented | **not exercised by the model in a test** |
| Offline operation | Done | e2e #12; Fast/Think have no network code paths |
| UI: light/dark/system, density, text size, keyboard shortcuts, responsive | Done | browser session (light/dark screenshots pending in repo) |
| Measured per-reply metrics in the UI | Done | browser (metrics popover) |

### Research (Phase 2)

| Feature | Status | Verified by |
|---|---|---|
| DuckDuckGo search (default) | Done | e2e #16 (live), two manual runs |
| SearXNG and Brave API adapters | Implemented | **not tested against a live instance / key** |
| SSRF-safe fetcher, robots.txt, per-host throttle | Done | unit tests (14 address cases, 8 URL cases) |
| HTML and PDF extraction | Done (HTML), implemented (PDF) | HTML in live runs; PDF extraction not yet hit in a live run |
| Deep Research: plan, search, read, evidence notes, gap check, cited report | Done | e2e #16; browser |
| Citation sanitizer (no invented sources or links) | Done | unit test; live runs: all citations in range |
| Research history in sidebar | Done | browser |

### Knowledge & memory

| Feature | Status | Verified by |
|---|---|---|
| Document upload (text, code, CSV, JSON, PDF, DOCX), FTS5 retrieval, page labels | Done | unit tests; e2e #8, #9, #10 |
| Long-term memory (explicit save tool + Settings CRUD + toggle + export) | Done | unit tests; e2e #11 |
| Embedding-based retrieval | Not implemented | planned (Phase 4) |

### Model development (Phase 3)

| Item | Status |
|---|---|
| Model comparison on this PC | Done — `docs/MODEL_RESEARCH.md`, raw JSON in `evals/results/` |
| Eval set v1 (39 base + 26 hard items, deterministic graders, unit-tested) | Done |
| Training pipeline (licensed dataset builder, Unsloth LoRA, GGUF export, base-vs-adapter eval) | Done — `training/README.md` |
| Thrones Adapter 0.1 (LoRA on Qwen3.5 4B) | **Withdrawn.** Gained tool use and Hinglish, but later testing in the app's real setup showed lower general maths (GSM8K 84.8% vs 95.2%, MATH 61.3% vs 84.0%). |
| **Thrones Adapter 0.2** (LoRA on Qwen3.5 4B, incl. linear-attention layers; 1,006 verified Qwen3.5 9B solutions added) | Trained, evaluated, selectable in the app (Experimental). Keeps 0.1's tool-use and Hinglish gains; GSM8K / MATH / MBPP 94.0 / 80.7 / 62.0 % vs base 95.2 / 84.0 / 60.0 % (within noise). Distillation did not raise reasoning. Model card: `training/runs/thrones-adapter-0.2/MODEL_CARD.md` |

### Not implemented in 1.0 (labelled as such in the UI where relevant)

Image/vision input · voice · MCP/external tool servers · per-message edit · embedding retrieval · Windows installer / desktop shell (Tauri) · auto-update.

## Test results (this build)

| Suite | Result | When |
|---|---|---|
| Backend unit tests (`pytest backend/tests`) | **77 / 77 passed** | 12 Nov 2026 |
| Adapters vs base on identical inputs (held-out + GSM8K/MATH/MBPP test samples) through llama.cpp | see `training/runs/thrones-adapter-0.2/MODEL_CARD.md` | 13 Nov 2026 |
| Out-of-memory during long evals (16 GB RAM, C: nearly full) | 2 runs crashed (`bad allocation`, `paging file too small`); evals now retry and record per-item errors; re-run results complete | 13 Nov 2026 |
| Frontend type-check + production build (`npm run build`) | passed | 12 Nov 2026 |
| End-to-end API checks (`scripts/e2e_check.py`, real model, live web) | **16 / 17** on first run; the failing check (identity) was fixed and then passed 5 / 5 times | 12 Nov 2026 |
| Browser session (in-app browser, production build) | Think EMI problem answered correctly (₹13,892.38 / ₹3,16,960.29) with 4 calculator calls; metrics popover, settings, phone width (375 px) checked | 12 Nov 2026 |
| Force-kill backend with model loaded | engine exited with it; VRAM returned to idle | 12 Nov 2026 |
| Cold load of the 9B, 3 times, 8 GB RAM free | 3 / 3 full-settings loads, 4.6–4.9 s | 12 Nov 2026 |
| Model benchmarks and evals | see `docs/MODEL_RESEARCH.md` | 12 Nov 2026 |

## Known issues

1. **Think mode does not raise the score** on our hard set (24/26, same as the raw 9B). Its benefits are reliability and checked working, at ~3× the time of Fast. Ideas to test: self-consistency (several answers, majority vote) for maths/logic.
2. **16 GB system RAM is the bottleneck.** The 9B keeps ~5.3 GB resident in RAM even fully on the GPU. With a browser and other apps open, a load can fall back to a smaller context or CPU. The fallback is now kept (no reload loop), explained in Settings, and logged to `data/load-failures.log`.
3. **gpt-oss 20B** is the most accurate model measured, but needs ~12 GB RAM; not recommended on 16 GB PCs.
4. The Think verifier sometimes approves a wrong answer (seen on 1 hard item) or is inconclusive (2 of 26).
5. DuckDuckGo search is unofficial and can be rate-limited (one page returned HTTP 429 in a test run).
6. Not yet tested: fresh install on a clean machine, CPU-only Lite profile, SearXNG/Brave adapters against live services, PDF pages in a live research run, in-app model download end-to-end, long-conversation summarisation, Firefox, screen readers.
7. Another tool left `GPT6_HANDOFF.md` and `.serena/` in the project folder. They are not part of Thrones and are not committed. Its separate work copy (`D:\Thrones-gpt6-support`) was not merged; one idea from its report (publishing the SQLite connection only after initialisation succeeds) was implemented independently.

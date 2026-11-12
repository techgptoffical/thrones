# Thrones test plan

A test is reported as passing only when it actually ran and its assertion held. Results for the current build are in `PROGRESS.md`; raw benchmark output is in `evals/results/`.

## 1. Test layers

| Layer | Where | Needs model? | Needs internet? | How to run |
|---|---|---|---|---|
| Unit | `backend/tests/` | no | no | `.venv\Scripts\python -m pytest backend/tests -q` |
| End-to-end API | `scripts/e2e_check.py` | yes (running app) | one check | `python scripts/e2e_check.py [--skip-web]` |
| Model benchmark & eval | `evals/run_bench.py` | yes (app engine unloaded) | no | `python evals/run_bench.py --think both` |
| UI in a browser | manual + scripted browser session | yes | for research | see §5 |
| Type-check / build | `frontend/` | no | no | `npm run build` (runs `tsc --noEmit`) |

Unit tests use a temporary data directory (`THRONES_DATA`); they never touch the user's database.

## 2. Unit tests (55 cases)

- **Calculator:** correct values (including the EMI formula and thousands separators); rejects names, attributes, calls outside the whitelist, strings, lambdas, and exponent/factorial bombs.
- **Tool registry:** identical-call refusal, call budget, bad JSON, unknown tool, timeout reported as a tool error rather than raised.
- **Research safety:** public/non-public IP classification (loopback, RFC1918, link-local incl. cloud metadata, CGNAT, IPv6 ULA/link-local, IPv4-mapped); URL guard rejects `file:`, `ftp:`, localhost, private hosts, `.local`, credentials, non-default ports; URL normalisation for de-duplication; citation sanitizer drops invented `[n]` and links to unfetched pages; tolerant JSON extraction; relevance window keeps the planted fact.
- **Persistence:** settings defaults and unknown-key filtering; message round-trip with JSON fields; regenerate truncation; search over titles and content; project deletion keeps chats; memory CRUD; failed DB initialisation is not cached; document ingest → chunk → BM25 search → context building (whole vs passages) → delete; unsupported and empty files rejected.

## 3. End-to-end checks (real model, real API)

| # | Check | Pass condition |
|---|---|---|
| 1 | Status | runtime found, hardware read, a model resolves |
| 2 | Fast chat | streamed tokens, content contains the requested word, metrics recorded |
| 3 | Multi-turn context + persistence | turn 2 recalls a number from turn 1; 4 messages saved; title generated |
| 4 | Regenerate | message count unchanged, assistant row replaced |
| 5 | Stop | status `stopped`, partial text saved, < 12 s, engine not busy afterwards |
| 6 | Think | plan + execute + verify steps; ≥ 1 calculator call; exact integer answer correct |
| 7 | Modes differ | Fast has no reasoning and no plan; Think has both and more model calls |
| 8 | Document Q&A | answer quotes a value that exists only in the uploaded file |
| 9 | Retrieval on a large file | correct value from one passage of a 117 k-character file; passage sources recorded |
| 10 | Bad upload | `.exe` rejected with a readable message |
| 11 | Memory | "please remember" saves via tool; new conversation recalls it; deletion works |
| 12 | Offline mode | Deep Research refuses with an explanation and no sources; local chat still answers; model download refused |
| 13 | Export | Markdown and JSON per conversation; full export excludes the API key |
| 14 | Hindi / Hinglish | Hinglish answered in Roman script; Hindi answered in Devanagari |
| 15 | Identity | names Thrones and the Qwen base model |
| 16 | Deep Research | ≥ 1 web source; all citations within range; plan/search/read/notes/write steps; a cited URL is reachable |
| 17 | Model switch | reply metrics show the other model; engine status matches |

## 4. Model evaluation

`evals/items.py` holds 39 items written for this project in six categories: maths (10), logic (8), code (5, graded by running hidden asserts), instruction following (5), Hindi/Hinglish (5), knowledge (6). Graders are deterministic. Settings: greedy decoding (temperature 0, top-k 1), same prompts for every model, thinking on/off recorded per run.

Performance is measured in the same run: load time, VRAM taken at load, generation speed on a ~300-token answer, prompt-processing speed and first-token latency on a ~10.8 k-token document, and whether a fact planted two-thirds of the way into that document is retrieved.

Interpretation rules:
- 39 items give roughly ±8 percentage points of noise; differences smaller than that are not claimed as real.
- A fine-tuned checkpoint is compared only against its own base, on identical items and settings.
- The set is small and was written by the same team that builds the prompts; it is a regression guard, not evidence of general capability. Public benchmarks (e.g. MMLU-Pro, GSM8K, HumanEval, IFEval) are on the plan for Phase 4.

## 5. UI checks (performed in the in-app browser against the production build)

- First load, theme from settings, engine status in the sidebar.
- Starter prompt → mode pre-selected → send → live activity (plan, tool calls) → streamed Markdown with KaTeX → collapsed activity with timing → metrics popover.
- Settings → Models & hardware shows live hardware, engine, profiles, installed/downloadable models with licences.
- Responsive: sidebar overlay under 900 px; composer usable at small heights.

Still to automate: Playwright suite covering the above plus keyboard shortcuts, focus trapping, drag-and-drop upload and dark/light screenshots.

## 6. Not yet covered

- Fresh-machine install of `scripts/setup.ps1` on a clean Windows user account.
- CPU-only (Lite) profile on a machine without an NVIDIA GPU.
- Long soak (hours of use, many conversations), memory growth.
- Out-of-memory recovery under deliberate VRAM pressure (fallback ladder is implemented; not yet forced in a test).
- Screen-reader pass (NVDA), Firefox.

# Model research — choosing Thrones' engine

Date: 12 November 2026. Machine: **RTX 5060 Ti 16 GB · Core i3-10105F (4C/8T) · 16 GB RAM · Windows 11 Pro**, NVIDIA driver 621.01, llama.cpp **b12289** (official CUDA 13.5 Windows build). Raw results: `evals/results/*.json`; regenerate the tables with `python evals/summarize.py`.

Everything in the *Measured* sections was run on this machine during this session. Figures marked *vendor-reported* come from the model publishers and were not reproduced here.

## 1. Candidates

| Model | Publisher | Licence | Type | File we used | File size | Native context | Thinking control | Notes |
|---|---|---|---|---|---|---|---|---|
| **Qwen3.5 9B** | Alibaba Cloud (Qwen) | Apache-2.0 | dense, hybrid Gated DeltaNet + attention, vision encoder (unused) | bartowski Q4_K_M GGUF | 6.17 GB | 262 144 | on/off (`enable_thinking`) | Released Feb 2026 |
| **Qwen3.5 4B** | Alibaba Cloud (Qwen) | Apache-2.0 | dense, same family (separate weights) | bartowski Q4_K_M GGUF | 3.01 GB | 262 144 | on/off | Local fine-tuning target |
| **Qwen3.5 2B** | Alibaba Cloud (Qwen) | Apache-2.0 | dense, same family | bartowski Q4_K_M GGUF | 1.40 GB | 262 144 | on/off | Lite tier |
| **gpt-oss 20B** | OpenAI | Apache-2.0 (+ usage policy) | MoE, 20.9 B total / 3.6 B active | ggml-org MXFP4 GGUF | 12.11 GB | 131 072 | effort only (low/medium/high), cannot be switched off | Released Aug 2025 |

Not evaluated in this round: larger Qwen3.5 models (27B and up need well over 16 GB VRAM at Q4 with useful context) and other 8–14B families such as Gemma. They are candidates for the next round; adding one is a catalog entry plus a `run_bench.py` run.

## 2. Runtime choice

| Runtime | Qwen3.5 | gpt-oss | Windows CUDA | Verdict |
|---|---|---|---|---|
| **llama.cpp `llama-server`** | yes | yes | official prebuilt CUDA 13.5 builds | **chosen**: OpenAI-compatible streaming with separate `reasoning_content`, tool calls, per-request timings, no Python CUDA stack |
| Ollama | **no** — Unsloth's Qwen3.5 guide states no Qwen3.5 GGUF works in Ollama because of the separate vision projector file | yes | yes | rejected for now |
| vLLM / SGLang | nightly / main branch only (per Qwen model card) | yes | Linux-first | rejected for a Windows desktop app |
| Transformers | needs v5 from main | yes | yes | too heavy for inference on 16 GB RAM |

The provider abstraction (`backend/thrones/runtime/base.py`) keeps this swappable.

## 3. Measured performance (16 384-token context, all layers on GPU)

| Model | Load | VRAM at load | Generation | First token (short prompt) | Reading a 10.8k-token prompt | First token (10.8k prompt) | Planted fact found | Peak VRAM (system) |
|---|---|---|---|---|---|---|---|---|
| Qwen3.5 9B Q4_K_M | 12.1 s | 5,994 MB | **50.4 tok/s** | 1.23 s | 2,904 tok/s | 4.5 s | yes | 7,696 MB |
| Qwen3.5 4B Q4_K_M | 7.1 s | 3,538 MB | **98.4 tok/s** | 0.75 s | 5,503 tok/s | 2.4 s | yes | 5,203 MB |
| Qwen3.5 2B Q4_K_M | 3.2 s | 1,558 MB | **163.8 tok/s** | 0.77 s | 10,162 tok/s | 1.5 s | yes | 3,457 MB |
| gpt-oss 20B MXFP4 | 17.4 s | 11,718 MB | **99.9 tok/s** | 1.10 s | 5,215 tok/s | 2.4 s | yes | 13,451 MB |

Load times vary with disk cache: later loads of the 9B took 4.6–8.5 s. In the app the 9B measured 50–65 tok/s across sessions.

How to read it:
- *VRAM at load* is the increase in GPU memory when the model loads (weights + KV cache for 16k context + compute buffers). *Peak VRAM (system)* is total GPU memory in use during the run, including ~1.5 GB used by Windows and other apps.
- *10.8k-token prompt* is a synthetic report with one planted fact two-thirds of the way in; *needle found* means the model returned both the name and the amount.
- *Engine working set* includes pages of the memory-mapped model file, so it overstates the RAM truly committed; see §5.

## 4. Measured accuracy

Two deterministic sets written for this project (`evals/items.py`): **base** (39 items) and **hard** (26 items). Greedy decoding, identical prompts, answers graded by code (code items run against hidden asserts). Maths, logic and knowledge items were re-graded after a parser fix so every model is scored by the same grader.

**Raw model** (greedy decoding, thinking off; gpt-oss uses `reasoning_effort: low` because its reasoning cannot be switched off):

| Model | Base set (39) | Hard set (26) | Hard: maths / logic / code / format / Hindi | Mean time per hard item |
|---|---|---|---|---|
| gpt-oss 20B | **39/39** | **25/26** | 10/10 · 5/6 · 5/5 · 3/3 · 2/2 | 2.2 s |
| Qwen3.5 9B | 37/39 | 24/26 | 9/10 · 5/6 · 5/5 · 3/3 · 2/2 | 7.1 s |
| Qwen3.5 4B | 37/39 | 21/26 | 10/10 · 3/6 · 3/5 · 3/3 · 2/2 | 4.9 s |
| Qwen3.5 2B | 33/39 | 19/26 | 9/10 · 3/6 · 2/5 · 3/3 · 2/2 | 2.4 s |

The base set was too easy to separate the 9B from the 4B (both 37/39); the hard set was added for that reason. One 2B answer ("3 3/5" for 3.6) was re-graded as correct after a fraction-parsing fix in the grader.

**Through the Thrones app** (Qwen3.5 9B, hard set, app sampling, so expect ±1–2 items between runs):

| Mode | Score | Mean time | Notes |
|---|---|---|---|
| Raw model, no app | 24/26 | 7.1 s | reference |
| Fast | 23/26 (two runs: 23, 23) | 6.7–7.4 s | calculator used on 6 items |
| Think — first version | 23/26 | 27.7 s | 2 empty answers: the model reasoned in circles until the token cap; verifier inconclusive on 8 items |
| Think — with 2,048-token reasoning limit and non-thinking verifier | **24/26** | 22.0 s | no empty answers; verifier inconclusive on 2 items |

What this shows, honestly: on these 26 questions **Think mode does not score higher than the raw 9B**; it ties it. Its measured value is reliability (no empty answers after the fix, every number recomputed by a real calculator, visible working) at about 3× the time of Fast. The first version of Think was worse than useless on some items, which is why the reasoning limit (`think_reasoning_budget`) now exists. Qwen's model card warns against greedy decoding with thinking enabled; we confirmed it: a greedy thinking run looped to the 6,000-token cap on 5 of the first 7 items, so no greedy-thinking scores are reported.

Caveats: 26–39 items give roughly ±8–10 points of noise, the items were written by the same team that built the prompts, and greedy decoding hides run-to-run variation. Treat differences of one or two items as ties.

### Public test sets through the app setup

Same configuration as Thrones' Fast mode (system prompt + calculator, thinking off, greedy), on random samples of the **test** splits (seed 7): GSM8K (MIT), MATH problems with integer answers (MIT), MBPP (CC-BY-4.0, graded by its own unit tests).

| Model | GSM8K (250) | MATH (150) | MBPP (150) |
|---|---|---|---|
| Qwen3.5 9B | 95.6% | 84.7% | **66.0%** |
| Qwen3.5 4B | 95.2% | 84.0% | 60.0% |

On standard maths the 4B is within one item of the 9B; the gap is in code (6 points, ≈ 9 problems — near the noise level for 150 items) and on our harder puzzle set (24 vs 21 of 26). These public sets are widely used in training data, so absolute scores may be inflated by contamination; comparisons between models on identical items are the useful part.

## 5. System RAM — the real constraint on this PC

Measured on the reference PC with a normal desktop session open (browser ≈ 4 GB, other apps ≈ 6 GB; 5.6–8 GB free before loading):

| Model (16k context, all layers on GPU) | System RAM taken by the engine | Engine private commit | VRAM | Free RAM left |
|---|---|---|---|---|
| Qwen3.5 9B (`--load-mode auto`) | 5.3 GB | 7.1 GB | 5.8 GB | 0.4 GB |
| Qwen3.5 9B (`--load-mode mmap`) | 5.3 GB | 7.1 GB | 6.4 GB | 0.4 GB |
| Qwen3.5 9B (`--load-mode none`) | — | — | — | engine crashed (out of RAM) |
| gpt-oss 20B (auto, observed during benchmark) | ≈ 12 GB | 12.6 GB | 11.7 GB | 0.1 GB |

Even with every layer on the GPU, llama.cpp on Windows keeps roughly the model's size resident in system RAM. On a 16 GB PC that is the binding constraint, not VRAM. The app's compatibility check now warns when a model needs more RAM than the PC has, and the demo guide tells users to close heavy apps first.

## 6. Vendor-reported benchmarks (not reproduced here)

From the Qwen3.5-9B model card (scores for gpt-oss-20B as listed by Qwen; mode not labelled, probably thinking):

| Benchmark | gpt-oss 20B | Qwen3.5 9B | Qwen3.5 4B |
|---|---|---|---|
| MMLU-Pro | 74.8 | 82.5 | 79.1 |
| GPQA Diamond | 71.5 | 81.7 | 76.2 |
| IFEval | 88.2 | 91.5 | 89.8 |
| LiveCodeBench v6 | 74.6 | 65.6 | 55.8 |
| HMMT Feb 25 | 76.7 | 83.2 | 74.0 |
| BFCL-V4 (tool calling) | — | 66.1 | 50.3 |
| MMMLU (multilingual) | 69.7 | 81.2 | 76.1 |

## 7. Fine-tuning feasibility on this GPU

| Model | bf16 LoRA VRAM (Unsloth) | On a 16 GB card |
|---|---|---|
| Qwen3.5 2B | ~5 GB | yes |
| Qwen3.5 4B | ~10 GB | **yes — first training target** |
| Qwen3.5 9B | ~22 GB | no; QLoRA discouraged by Unsloth for Qwen3.5 |
| gpt-oss 20B | not assessed | no (MoE, 12 GB weights in MXFP4) |

## 8. Recommendation

**Default (High profile): Qwen3.5 9B Q4_K_M.**
- Second-best accuracy measured here (24/26 hard, 37/39 base), within one item of gpt-oss.
- Fits this PC with headroom: ~5.8 GB VRAM and ~5.3 GB RAM at 16k context, leaving VRAM for longer contexts.
- Thinking can be switched off (Fast) or on with a limit (Think).
- Vendor-reported multilingual (MMMLU 81.2 vs 69.7) and tool-calling (BFCL-V4 66.1) scores are the strongest of the candidates, which matters for Hindi/Hinglish and tool use.
- Same family as the trainable 4B.

**Balanced: Qwen3.5 4B** — twice as fast, equal on easy questions, clearly weaker on harder logic and code (21/26). Also the local fine-tuning base.

**Lite: Qwen3.5 2B** — 164 tok/s on GPU; noticeably weaker (19/26). CPU-only speed has not been measured yet.

**Optional: gpt-oss 20B** — the most accurate and fastest model we measured, but on Windows it needs ~12 GB of system RAM in addition to ~11.7 GB VRAM. Recommended only on PCs with 24 GB+ RAM. It stays in the catalog with a RAM warning.

**What would actually make Thrones much stronger:** a bigger model, not more prompting. On a 24–32 GB GPU with 32 GB+ RAM, 27B-class dense or 30–35B MoE models become practical; that hardware step is a larger capability jump than anything prompts or a LoRA can deliver on a 4–9B model.

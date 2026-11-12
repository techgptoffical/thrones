<p align="center"><img src="frontend/public/thrones.svg" width="56" alt=""></p>

<h1 align="center">Thrones</h1>

<p align="center">A private AI assistant that runs on your own PC.<br>
Open-weight models, real reasoning tools, cited web research and document Q&amp;A, in one calm interface.</p>

---

**Thrones 1.0** is application software by TECH GPT. The language model it runs is **not** a Thrones model: by default it is **Qwen3.5 9B** by Alibaba Cloud's Qwen team (Apache-2.0), unmodified, in a community Q4_K_M quantization, executed locally by **llama.cpp**. Thrones' own trained weights so far are **Thrones Adapter 0.1**, a small LoRA fine-tune (42 MB) on Qwen3.5 4B that makes it use the calculator reliably and write cleaner Hinglish, with no measured loss elsewhere — see its [model card](training/runs/thrones-adapter-0.1/MODEL_CARD.md). It is optional and marked Experimental; it is not a model trained from scratch.

## What it does

| | |
|---|---|
| **Chat, fully offline** | Streaming answers from a local model. Works with the network cable unplugged. No account, no telemetry. |
| **Fast / Think / Deep Research** | Three modes that change what the backend actually does. *Think* plans, solves with thinking enabled, checks arithmetic with a real calculator, then has an independent pass verify the answer and fix it if wrong. *Deep Research* searches the web, reads several pages, and writes a report whose every citation points to a page it actually fetched. |
| **Your documents** | Attach text, code, CSV, JSON, PDF or DOCX. They are indexed locally (SQLite FTS5) and quoted to the model with file and page references. |
| **Memory you control** | Save facts across chats; see, edit, disable, delete or export every one. |
| **Hindi, English, Hinglish** | Answers in the language and script you write in. |
| **Honest numbers** | Every reply carries its measured speed, latency, token counts and peak memory. |
| **Hardware-aware** | Detects your GPU/RAM, picks a profile (Lite / Balanced / High), falls back to smaller context or CPU if a load fails, unloads when idle. |

## Measured on the reference PC

RTX 5060 Ti 16 GB · Core i3-10105F · 16 GB RAM · Windows 11 · llama.cpp b12289 · 16k context. Full method and results: [`docs/MODEL_RESEARCH.md`](docs/MODEL_RESEARCH.md).

| Model | Speed | VRAM | System RAM | Hard questions (26) | Profile |
|---|---|---|---|---|---|
| **Qwen3.5 9B** Q4_K_M (default) | 50 tok/s | 5.8 GB | ~5.3 GB | 24 | High |
| Qwen3.5 4B Q4_K_M | 98 tok/s | 3.5 GB | — | 21 | Balanced |
| Thrones Adapter 0.1 (Qwen3.5 4B + LoRA) | 82 tok/s (in app) | 3.5 GB | — | 21 | Balanced, experimental |
| Qwen3.5 2B Q4_K_M | 164 tok/s | 1.6 GB | — | 19 | Lite |
| gpt-oss 20B MXFP4 (optional) | 100 tok/s | 11.7 GB | ~12 GB | 25 | needs 24 GB+ RAM |

Hard questions = our own 26-item maths / logic / code / format / Hindi set, greedy decoding, model alone. Through the app the 9B scores 23–24 in Fast and 24 in Think (Think adds checked, visible working, not extra points on this set).

## Install (Windows 10/11)

Requirements: Python 3.11+, Node.js 20+, ~10 GB free disk for the default model. An NVIDIA GPU with 8 GB+ VRAM is recommended; CPU-only works with the Lite profile.

```powershell
git clone <this repository> Thrones
cd Thrones
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1      # add -Cpu for machines without an NVIDIA GPU
```

The script creates `.venv`, builds the interface, and downloads the official llama.cpp release into `runtime\`. Nothing is installed system-wide.

Then double-click **`Thrones.bat`**. Your browser opens at `http://127.0.0.1:8765`. Go to **Settings → Models & hardware**, download the model recommended for your PC, and start chatting. Closing the Thrones window stops everything and frees the GPU.

## Privacy

Conversations, memories, documents and settings live in `data\` on your PC. Thrones contacts the internet only when you run **Deep Research** (search queries + the pages it reads) or **download a model**. **Offline mode** blocks both. Details: [`SECURITY.md`](SECURITY.md).

## Limits — please read

- A 2–9B local model is far smaller than frontier cloud assistants. It makes more factual and reasoning errors and knows nothing after its training data. Think mode and Deep Research reduce some errors with tools and sources; they do not make the model smarter, and they do not change its weights.
- Deep Research uses DuckDuckGo through an unofficial library by default. It can be rate-limited; Brave API or your own SearXNG are supported alternatives.
- The optional Python tool is **not a sandbox** and is off by default.
- Images, voice, and external MCP tools are not supported in 1.0.
- There is no installer yet; setup uses the PowerShell script above.

Status of every feature, including what is not done: [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Project documents

[Architecture](docs/ARCHITECTURE.md) · [Model research](docs/MODEL_RESEARCH.md) · [Implementation plan](docs/IMPLEMENTATION_PLAN.md) · [Training plan](docs/TRAINING_PLAN.md) · [Training pipeline](training/README.md) · [UI design spec](docs/UI_DESIGN_SPEC.md) · [Test plan](docs/TEST_PLAN.md) · [Progress](docs/PROGRESS.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

## Licence

Thrones application code: [MIT](LICENSE). Models, the llama.cpp runtime, fonts and libraries keep their own licences: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

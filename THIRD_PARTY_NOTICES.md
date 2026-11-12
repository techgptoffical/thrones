# Third-party notices

Thrones application code is MIT-licensed (see `LICENSE`). It does **not** contain or redistribute model weights or the inference runtime; those are downloaded by the user from their original publishers and remain under their own licenses.

## Models (downloaded on demand, not bundled)

| Model | Publisher | License | Original weights | Quantized file used |
|---|---|---|---|---|
| Qwen3.5 9B | Alibaba Cloud (Qwen team) | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.5-9B | `bartowski/Qwen_Qwen3.5-9B-GGUF` Q4_K_M |
| Qwen3.5 4B | Alibaba Cloud (Qwen team) | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.5-4B | `bartowski/Qwen_Qwen3.5-4B-GGUF` Q4_K_M |
| Qwen3.5 2B | Alibaba Cloud (Qwen team) | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.5-2B | `bartowski/Qwen_Qwen3.5-2B-GGUF` Q4_K_M |
| gpt-oss 20B | OpenAI | Apache-2.0 (plus OpenAI's gpt-oss usage policy) | https://huggingface.co/openai/gpt-oss-20b | `ggml-org/gpt-oss-20b-GGUF` MXFP4 |

GGUF files are community conversions of the original weights; check each repository's model card for its exact provenance.

## Training data (Thrones Adapter 0.1)

| Dataset | Licence | Used |
|---|---|---|
| CohereLabs/aya_dataset (Hindi rows) | Apache-2.0 | 600 rows, unchanged |
| OpenAssistant/oasst2 (English, first turn, rank-0 replies) | Apache-2.0 | 550 rows |
| findnitai/english-to-hinglish (`source = 1` human-annotated rows; aggregates Hinglish TOP, CMU DoG, HinGE, PHINC) | Apache-2.0 | 700 rows wrapped as translation instructions |

The adapter weights (`models/thrones-adapter-0.1.gguf`) are MIT-licensed by the Thrones project and apply to Qwen3.5 4B (Apache-2.0).

## Training tools (in `.venv-train`, not shipped)

PyTorch (BSD-3), Transformers (Apache-2.0), TRL (Apache-2.0), PEFT (Apache-2.0), Unsloth (Apache-2.0), datasets (Apache-2.0), sacrebleu (Apache-2.0), gguf / convert_lora_to_gguf.py from llama.cpp (MIT).

## Runtime (downloaded by `scripts/setup.ps1`, not bundled)

- **llama.cpp** (`llama-server`), MIT License — https://github.com/ggml-org/llama.cpp. The CUDA build ships NVIDIA CUDA runtime DLLs under NVIDIA's redistribution terms.

## Python packages (installed into `.venv`)

FastAPI (MIT), Starlette (BSD-3), Uvicorn (BSD-3), Pydantic (MIT), HTTPX (BSD-3), psutil (BSD-3), pypdf (BSD-3), python-docx (MIT), python-multipart (Apache-2.0), trafilatura (Apache-2.0), ddgs (MIT), pytest (MIT).

## JavaScript packages (bundled into `frontend/dist`)

React and React DOM (MIT), Zustand (MIT), react-markdown, remark-gfm, remark-math, rehype-katex, rehype-highlight (MIT), KaTeX (MIT), highlight.js (BSD-3), lucide-react (ISC), Vite (MIT, build only), TypeScript (Apache-2.0, build only).

## Fonts (bundled)

- **Geist** and **Geist Mono** — SIL Open Font License 1.1 (Vercel), via `@fontsource-variable`.
- **Instrument Serif** — SIL Open Font License 1.1, via `@fontsource`.
- **KaTeX fonts** — SIL Open Font License 1.1 / MIT.

## Services used only when the user enables them

- **DuckDuckGo** search via the unofficial `ddgs` library (Deep Research only). Not an official API; subject to DuckDuckGo's terms and rate limits.
- **Brave Search API** (optional; user's own key) — https://brave.com/search/api/
- **SearXNG** (optional; user's own instance) — AGPL-3.0, run separately by the user.
- **Hugging Face** — model file downloads.

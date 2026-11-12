# Thrones training plan

**Status (12 Nov 2026): no training has been run.** Thrones 1.0 ships the unmodified base models listed in `config/models.json`. Nothing in the app, its prompts or its tools changes model weights, and the UI says so (Settings → About). This document is the plan for the first genuine adapter.

## 1. Goal and principle

Produce a **Thrones adapter**: a LoRA on top of a named base model that measurably improves a few things users of this app need, without degrading the base model elsewhere. Every claim of improvement must come from the same held-out evaluation run on the base and the adapter with identical settings.

Target behaviours, in priority order:

1. Hindi and Hinglish fluency (natural Roman-script Hinglish, correct Devanagari).
2. Reliable tool use in Thrones' format: calling the calculator instead of guessing arithmetic; not calling tools when unnecessary; well-formed JSON arguments.
3. Instruction and format adherence (lengths, lists, JSON-only replies).
4. Direct, non-preachy answers to benign requests (fewer unnecessary refusals and disclaimers) **without** increasing compliance with genuinely harmful requests.
5. Correct self-identification: "Thrones running \<base model\>".

## 2. What can be trained on this machine

Hardware: RTX 5060 Ti 16 GB (Blackwell, needs PyTorch built for CUDA 12.8+), 16 GB system RAM, 4-core i3.

| Base | Method | VRAM needed (Unsloth's published figure) | Fits 16 GB? |
|---|---|---|---|
| Qwen3.5 2B | bf16 LoRA | ~5 GB | yes |
| **Qwen3.5 4B** | **bf16 LoRA** | **~10 GB** | **yes — first target** |
| Qwen3.5 9B | bf16 LoRA | ~22 GB | **no** |
| Qwen3.5 9B | QLoRA (4-bit) | lower | not recommended: Unsloth advises against QLoRA for all Qwen3.5 models due to "higher than normal quantization differences" |

Source: Unsloth's Qwen3.5 fine-tuning guide (unsloth.ai/docs/models/qwen3.5/fine-tune), read 12 Nov 2026. These are vendor estimates, not our measurements; the first run will record actual peak VRAM.

Consequences:
- The first adapter is trained on **Qwen3.5 4B**. The 9B stays as the separate, unmodified default inference model.
- A 4B adapter is **never** applied to the 9B (different architecture sizes; it would not load, and if forced would be meaningless).
- 9B training is deferred until there is either rented GPU time (≥ 24 GB, e.g. one 24–48 GB cloud GPU for a few hours) or a validated low-memory method.
- 16 GB system RAM is tight for loading and merging; training will use short sequences (2048), gradient checkpointing, batch size 1–2 with accumulation, and will not merge in RAM until checked.
- Unsloth documents Windows support for *Unsloth Studio*; the code workflow on native Windows is not documented, so the training environment will be WSL2 (Ubuntu) or Studio, isolated from the app's `.venv`. Transformers v5 is required for Qwen3.5.

## 3. Data — allowed sources only

| Source type | Use | Rule |
|---|---|---|
| Permissively licensed instruction datasets (candidates: OpenAssistant oasst2 — Apache-2.0; Aya dataset — Apache-2.0, includes Hindi; Dolly-15k — CC BY-SA 3.0) | general instruction following, Hindi | licence verified on the dataset card at download time and recorded in `training/datasets/LICENSES.md` |
| Examples written by the Thrones team | Hinglish conversations, tool-use traces in Thrones' exact format, identity, refusal-calibration pairs | authored by people for this project; author and date recorded |
| Traces from the base model itself, corrected by a human | tool-use format examples | allowed (Apache-2.0 base), every example reviewed |
| Public-domain or CC0 text | Hindi prose | provenance recorded |

**Excluded:**
- Outputs from Claude, Fable or any Anthropic model, and from any provider whose terms forbid using outputs to train competing models — unless written permission exists.
- Datasets distilled from proprietary models under non-commercial terms (e.g. Alpaca-style sets derived from text-davinci-003).
- Scraped personal data, private chats, or copyrighted text without rights.
- Data intended to make the model comply with harmful requests. Refusal calibration only teaches the model to *help* with benign requests it wrongly refuses; harmful-request handling is evaluated for regression.

Every dataset row keeps `source`, `license`, `author_or_origin`, `transform` (what we changed) and `reviewed_by`. A manifest with SHA-256 hashes is committed with each training run.

Target size for adapter v0.1: 3–6 k examples (≈ 40 % Hindi/Hinglish, 25 % tool use, 20 % format adherence, 10 % benign-refusal calibration, 5 % identity), plus a 300-example **held-out** set never used in training.

## 4. Method

- Unsloth + PEFT, bf16 LoRA, `r=16`, `alpha=16`, dropout 0, language layers only (vision layers frozen — Qwen3.5 checkpoints include a vision encoder), sequence length 2048, 1–2 epochs, cosine LR around 1e-4 with warm-up (to be tuned on a 10 % pilot run).
- Chat template identical to the one llama.cpp uses at inference (Qwen3.5 Jinja template, thinking disabled for non-reasoning examples).
- Export: LoRA adapter (safetensors) **and** a merged GGUF Q4_K_M via Unsloth's `save_pretrained_gguf`, so the app can load it like any other catalog model.

## 5. Evaluation (before any claim)

Run on base 4B and adapter 4B with identical greedy settings:

1. Thrones eval set (`evals/items.py`, 39 items) — regression guard.
2. The 300-example held-out Thrones set (per target behaviour).
3. Public regression checks: a reasoning set (GSM8K subset), a knowledge set (MMLU-Pro subset), an instruction set (IFEval subset), a code set (HumanEval) — to catch damage outside the training targets.
4. Safety regression: a fixed set of clearly harmful requests (must not become more compliant) and a fixed set of benign-but-edgy requests (should become less refused).
5. Speed and memory: unchanged GGUF size class; confirm tokens/s and VRAM in `run_bench.py`.

Ship criterion: improvement beyond noise on targets 1–3 **and** no regression beyond noise on 3–4. Otherwise the adapter is not shipped and the result is documented anyway.

## 6. Artefacts saved for every run

`training/runs/<date>-<name>/`: adapter weights, merged GGUF, exact base model id and revision hash, `config.yaml`, dataset manifest with licences and hashes, the exact command line and environment (`pip freeze`), training log and loss curve, evaluation JSON for base and adapter, and a `MODEL_CARD.md` naming the base model, the method, the data, the results and the limits. If a run fails, its logs and partial checkpoints are kept and the failure is recorded.

## 7. Naming

An adapter release is called, for example, **"Thrones Adapter 0.1 for Qwen3.5 4B"**. It is never described as a new model trained from scratch, and the base model's name and licence travel with it.

## 8. Later

- 9B adapter on rented ≥ 24 GB GPU once 4B results justify it.
- Preference tuning (DPO/ORPO) on human-ranked pairs for directness and format, if enough reviewed pairs exist.
- Task adapters (e.g. a Hinglish-only adapter) selectable in Settings.

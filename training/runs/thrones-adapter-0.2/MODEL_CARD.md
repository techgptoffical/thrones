# Thrones Adapter 0.2 for Qwen3.5 4B

Thrones' second fine-tune, and the one the app now offers. A **LoRA adapter** (30.5 M parameters, 61 MB as GGUF f16) applied on top of the **unmodified** Qwen3.5 4B. It replaces Adapter 0.1, which turned out to reduce general maths accuracy (see below). It is not a model trained from scratch; the base model's knowledge and reasoning come from Alibaba Cloud's Qwen team.

| | |
|---|---|
| Base model | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), Apache-2.0 |
| Deployed as | `models/Qwen_Qwen3.5-4B-Q4_K_M.gguf` + `models/thrones-adapter-0.2.gguf` (`llama-server --lora`) |
| Adapter licence | MIT (Thrones project); base stays Apache-2.0 |
| Method | bf16 LoRA (Unsloth), r = 16, α = 16. Targets: q/k/v/o of the 8 full-attention layers, gate/up/down of all 32 MLP blocks, and — new in 0.2 — `in_proj_qkv`, `in_proj_z`, `out_proj` of the 24 linear-attention (Gated DeltaNet) layers. |
| Training | 1 epoch, 468 steps, batch 1 × grad-accum 8, cosine LR 1e-4, max 3,072 tokens, loss on assistant tokens only. 51 min on one RTX 5060 Ti 16 GB, peak 9.5 GB VRAM, mean train loss 0.47. |
| Data (3,738 rows) | **1,006 verified teacher solutions** (new): Qwen3.5 9B (Apache-2.0) solved GSM8K (MIT), MATH levels 4–5 (MIT) and MBPP (CC-BY-4.0) *train* problems with the Thrones calculator; kept only if the answer matched the dataset's gold answer or the code passed the problem's own unit tests (291 / 342 / 373 kept of 300 / 500 / 474). Plus 900 code-generated tool-use examples, 700 human Hinglish pairs, 600 Aya Hindi, 500 oasst2 English, 32 varied identity answers. Manifest: `training/datasets/thrones_sft_v0.2.manifest.json`. **No outputs from Claude, Fable or any proprietary model.** |

## Results (same inputs, greedy, through llama.cpp, 13 Nov 2026)

### Public test sets, in the app's Fast-mode setup (system prompt + calculator)

None of these test items is in any training set.

| Test (sample) | Base 4B | Adapter 0.1 | **Adapter 0.2** | Qwen3.5 9B (reference) |
|---|---|---|---|---|
| GSM8K (250) | 95.2% | 84.8% | **94.0%** | 95.6% |
| MATH, integer answers (150) | 84.0% | 61.3% | **80.7%** | 84.7% |
| MBPP, own unit tests (150) | 60.0% | 56.7% | **62.0%** | 66.0% |

### Thrones held-out set (`thrones_sft_v0.2.heldout.jsonl`)

| Test | Base 4B | Adapter 0.1 | **Adapter 0.2** |
|---|---|---|---|
| Tool use, training-style questions (86) | 76 | 86 | **86** |
| Tool use, **question types never trained on** (120: unit conversion, profit/loss %, bill splitting) | 118 (calculator used on 75) | 120 (used on 120) | **119** (used on 117) |
| English↔Hinglish translation, chrF (100) | 37.5 | 49.2 | **50.2** |
| Identity (names Thrones and Qwen) | 3/3 | 3/3 | **3/3** |
| Regression: base set (39) / hard set (26), no system prompt | 37 / 21 | 37 / 21 | **36 / 22** |

Raw results: `evals/results/reasoning-*.json`, `evals/results/adapter-v02-*.json`.

## What this shows — honestly

- **Learning from the 9B did not raise the 4B's reasoning.** Against the base, 0.2 is −1.2 points on GSM8K, −3.3 on MATH and +2.0 on MBPP — all within the noise of 150–250 items (roughly ±3–5 points), with MATH leaning slightly down. The likely reason: on these sets the 9B teacher is barely better than the 4B student (gap 0.4 / 0.7 / 6.0 points), so there was little to transfer.
- **What 0.2 does deliver:** the tool-use and Hinglish gains of 0.1 (now also on question types it never trained on, where it reliably reaches for the calculator: 117 of 120 vs 75 for the base), **without** 0.1's damage to general maths.
- **Adapter 0.1 is superseded.** Its own evaluation only covered its training-style questions and the regression sets without the app's system prompt. In the real app setup it lost 10 points on GSM8K and 23 on MATH, making real reasoning errors (not formatting slips). Mixing verified worked solutions into the training data is what fixed this in 0.2.
- Small samples, one seed, one run. Hinglish chrF partly measures format (no preamble); no human quality review has been done.

## Intended use

Selectable in Thrones as **"Thrones Adapter 0.2 (Qwen3.5 4B)"** (Balanced tier, Experimental): a faster engine than the 9B with dependable calculator use and better Hinglish. For the hardest reasoning and code, the unmodified Qwen3.5 9B (default) remains the better choice. Never apply this adapter to another base model.

## Limits and risks

Inherits Qwen3.5 4B's limitations. Safety behaviour was not separately evaluated. The teacher's solutions were checked for the final answer or test pass only; their intermediate steps were not reviewed by a person.

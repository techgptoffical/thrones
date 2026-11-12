"""Train a Thrones LoRA adapter on Qwen3.5 4B with Unsloth (bf16 LoRA — Unsloth advises against QLoRA for Qwen3.5).

    .venv-train\\Scripts\\python training\\train_lora.py --run thrones-adapter-0.1

Writes training/runs/<run>/:
  adapter/            LoRA weights (safetensors) + tokenizer
  config.json         every hyper-parameter and the exact base-model revision
  train_log.jsonl     loss per step
  summary.json        steps, time, peak VRAM
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "hf"))
os.environ.setdefault("UNSLOTH_CACHE_DIR", str(ROOT / ".cache" / "unsloth"))
os.environ.setdefault("TRITON_CACHE_DIR", str(ROOT / ".cache" / "triton"))

BASE_DIR = ROOT / "training" / "base" / "Qwen3.5-4B"
DATA = ROOT / "training" / "datasets" / "thrones_sft_v0.1.train.jsonl"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="thrones-adapter-0.1")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-seq", type=int, default=2048)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=-1, help="override epochs (for a quick pilot)")
    args = ap.parse_args()

    import torch
    from unsloth import FastLanguageModel  # must be imported before transformers/trl
    from unsloth.chat_templates import train_on_responses_only
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer
    from transformers import TrainerCallback

    out = ROOT / "training" / "runs" / args.run
    out.mkdir(parents=True, exist_ok=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(BASE_DIR), max_seq_length=args.max_seq,
        load_in_4bit=False, load_in_16bit=True, full_finetuning=False,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=args.rank, lora_alpha=args.rank, lora_dropout=0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=3407,
    )

    # Qwen3.5 ships a vision encoder, so Unsloth returns a multimodal *processor*. Calling it on plain
    # text makes it look for images; all text work goes through its inner tokenizer instead.
    text_tok = getattr(tokenizer, "tokenizer", tokenizer)

    raw = load_dataset("json", data_files={"train": str(DATA)}, split="train")

    def render(example: dict) -> dict:
        msgs = []
        for m in example["messages"]:
            m = {k: v for k, v in m.items() if v is not None}
            msgs.append(m)
        text = text_tok.apply_chat_template(
            msgs, tools=example.get("tools"), tokenize=False, add_generation_prompt=False, enable_thinking=False)
        return {"text": text}

    ds = raw.map(render, remove_columns=raw.column_names)
    lengths = [len(text_tok(t)["input_ids"]) for t in ds["text"][:400]]
    print(f"rows {len(ds)}  token length (first 400): mean {sum(lengths) / len(lengths):.0f}, max {max(lengths)}")

    class LogLoss(TrainerCallback):
        def on_log(self, _args, state, _control, logs=None, **_):
            if logs:
                with (out / "train_log.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"step": state.global_step, **logs}) + "\n")

    (out / "train_log.jsonl").unlink(missing_ok=True)
    cfg = SFTConfig(
        output_dir=str(out / "checkpoints"), dataset_text_field="text", max_length=args.max_seq,
        per_device_train_batch_size=1, gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs, max_steps=args.max_steps, learning_rate=args.lr,
        lr_scheduler_type="cosine", warmup_ratio=0.05, weight_decay=0.0,
        logging_steps=5, save_strategy="no", optim="adamw_8bit", bf16=True,
        seed=3407, dataset_num_proc=1, report_to="none",
    )
    trainer = SFTTrainer(model=model, train_dataset=ds, processing_class=text_tok, args=cfg,
                         callbacks=[LogLoss()])
    # Loss only on the assistant's turns (including its tool calls), never on system/user/tool text.
    trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\n",
                                      response_part="<|im_start|>assistant\n")

    sample = trainer.train_dataset[0]
    trained_tokens = sum(1 for x in sample["labels"] if x != -100)
    print(f"sample 0: {len(sample['input_ids'])} tokens, {trained_tokens} trained (assistant only)")

    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    result = trainer.train()
    seconds = time.time() - t0

    model.save_pretrained(str(out / "adapter"))
    text_tok.save_pretrained(str(out / "adapter"))

    base_files = {p.name: sha256(p) for p in sorted(BASE_DIR.glob("*.safetensors"))}
    (out / "config.json").write_text(json.dumps({
        "run": args.run, "method": "bf16 LoRA (Unsloth)", "base_model": "Qwen/Qwen3.5-4B",
        "base_weights_sha256": base_files, "dataset": DATA.name, "dataset_sha256": sha256(DATA),
        "rank": args.rank, "alpha": args.rank, "dropout": 0, "lr": args.lr, "epochs": args.epochs,
        "max_steps": args.max_steps, "grad_accum": args.grad_accum, "batch": 1, "max_seq": args.max_seq,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        "loss": "assistant tokens only", "chat_template": "Qwen3.5, enable_thinking=False",
        "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
        "python": platform.python_version(), "command": " ".join(sys.argv),
    }, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({
        "steps": result.global_step, "train_loss": result.training_loss, "seconds": round(seconds, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    }, indent=2), encoding="utf-8")
    print("saved adapter to", out / "adapter")


if __name__ == "__main__":
    main()

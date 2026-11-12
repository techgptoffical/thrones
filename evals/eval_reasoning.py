"""Out-of-distribution reasoning evaluation: GSM8K, MATH (integer answers) and MBPP *test* splits.

The model runs as in the Thrones app (system prompt + calculator tool, thinking off, greedy), with
several parallel requests for speed. No item here is used for training.

    python evals/eval_reasoning.py --model qwen3.5-4b-q4km --label base4b
    python evals/eval_reasoning.py --model qwen3.5-4b-q4km --lora models/thrones-adapter-0.2.gguf --label adapter02
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "backend"))

import reasoning_sets as rs  # noqa: E402
from run_bench import BASE, Server, free_app_engine  # noqa: E402
from thrones import config  # noqa: E402
from thrones.reasoning import prompts  # noqa: E402

N_GSM8K, N_MATH, N_MBPP, SEED, SLOTS = 250, 150, 150, 7, 4


def system_for(entry: dict, adapter: bool) -> str:
    e = dict(entry)
    if adapter:
        e.update(name="Thrones Adapter (Qwen3.5 4B)", base_name="Qwen3.5 4B", adapter="Thrones Adapter")
    return prompts.system_prompt(e, {"style": "balanced", "custom_instructions": ""}, "fast", []) + \
        "\n\n" + prompts.TOOL_GUIDE


def test_items() -> list[dict]:
    return (rs.sample(rs.gsm8k("test"), N_GSM8K, SEED) + rs.sample(rs.math_int("test"), N_MATH, SEED)
            + rs.sample(rs.mbpp(("test",)), N_MBPP, SEED))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--lora", default="")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    entry = next(e for e in config.load_catalog() if e["id"] == args.model)
    items = test_items()
    system = system_for(entry, bool(args.lora))
    client = httpx.Client(timeout=900)

    def post(body: dict) -> dict:
        r = client.post(BASE + "/v1/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]

    def one(item: dict) -> dict:
        produced, final = rs.solve(post, [{"role": "system", "content": system},
                                          {"role": "user", "content": item["prompt"]}], rs.TOOLS)
        calls = sum(len(m.get("tool_calls", [])) for m in produced if m["role"] == "assistant")
        return {"id": item["id"], "kind": item["kind"], "ok": rs.grade(item, final), "tool_calls": calls,
                "chars": len(final), "final": final[-1500:]}

    free_app_engine()
    extra = ["-np", str(SLOTS)] + (["--lora", str(ROOT / args.lora)] if args.lora else [])
    rows: list[dict] = []
    with Server(entry, 8192 * SLOTS, 99, extra):
        with ThreadPoolExecutor(SLOTS) as pool:
            for i, row in enumerate(pool.map(one, items), 1):
                rows.append(row)
                if i % 50 == 0:
                    print(f"  {i}/{len(items)}", flush=True)
    summary = {}
    for kind in ("gsm8k", "math", "mbpp"):
        sub = [r for r in rows if r["kind"] == kind]
        summary[kind] = {"correct": sum(r["ok"] for r in sub), "n": len(sub),
                         "pct": round(100 * sum(r["ok"] for r in sub) / max(1, len(sub)), 1),
                         "used_calculator": sum(1 for r in sub if r["tool_calls"])}
    report = {"label": args.label, "model": args.model, "lora": args.lora, "seed": SEED,
              "date": dt.datetime.now().isoformat(timespec="seconds"), "summary": summary, "items": rows}
    path = ROOT / "evals" / "results" / f"reasoning-{args.label}-{dt.datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary), "->", path.name)


if __name__ == "__main__":
    main()

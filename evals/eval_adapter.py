"""Compare base Qwen3.5 4B with base + Thrones LoRA on identical inputs, through llama.cpp (as deployed).

    python evals/eval_adapter.py --label base
    python evals/eval_adapter.py --label adapter --lora training/runs/thrones-adapter-0.1/thrones-adapter-0.1.gguf

Measures:
  tool_use      held-out generated problems: did it call the calculator, and is the final answer correct?
  hinglish      held-out human translation pairs: chrF against the reference
  identity      says it is Thrones and names the Qwen base model
  base / hard   the 65-item regression sets (greedy, thinking off)
Writes evals/results/adapter-<label>-<stamp>.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "backend"))

from items import SETS  # noqa: E402
from run_bench import BASE, Server, free_app_engine  # noqa: E402
from thrones import config  # noqa: E402
from thrones.tools.calculator import evaluate  # noqa: E402

HELD = ROOT / "training" / "datasets" / "thrones_sft_v0.1.heldout.jsonl"


def chat(messages: list[dict], tools: list | None = None, max_tokens: int = 1200) -> dict:
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "top_k": 1, "top_p": 1.0,
            "chat_template_kwargs": {"enable_thinking": False}}
    if tools:
        body["tools"] = tools
    r = httpx.post(BASE + "/v1/chat/completions", json=body, timeout=600)
    r.raise_for_status()
    return r.json()["choices"][0]


def norm(n: str) -> str:
    """'12,345.50' and '12345.5' compare equal; values are compared to 2 decimal places."""
    return f"{round(float(n.replace(',', '')), 2):.2f}"


def numbers(text: str) -> set[str]:
    """Numbers that appear in bold in the reference answer (the key results)."""
    out = set()
    for m in re.findall(r"\*\*(.+?)\*\*", text):
        for n in re.findall(r"-?\d[\d,]*(?:\.\d+)?", m):
            out.add(norm(n))
    return out


def run_tool_loop(messages: list[dict], tools: list) -> tuple[str, int, bool]:
    """Let the model use the real calculator for up to 4 rounds. Returns (final text, calls, malformed)."""
    msgs = [dict(m) for m in messages]
    calls, malformed = 0, False
    for _ in range(5):
        choice = chat(msgs, tools)
        msg = choice["message"]
        tcs = msg.get("tool_calls") or []
        if not tcs:
            return msg.get("content") or "", calls, malformed
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
        for tc in tcs:
            calls += 1
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
                result = f"{args['expression']} = {evaluate(str(args['expression']))}"
            except Exception as exc:  # malformed call: report like the app does
                malformed = True
                result = f"Error: {type(exc).__name__}: {exc}"
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
    return "", calls, malformed


def eval_tool_use(rows: list[dict]) -> dict:
    stats = {"n": 0, "called_tool": 0, "correct": 0, "malformed_calls": 0, "items": []}
    for r in rows:
        msgs = r["messages"]
        prompt = msgs[:2]                                   # system + user only
        want = numbers(msgs[-1]["content"])
        final, calls, malformed = run_tool_loop(prompt, r["tools"])
        got = [float(norm(n)) for n in re.findall(r"-?\d[\d,]*(?:\.\d+)?", final)]
        # A key number counts as present if the answer contains it to within rounding (0.05% or 0.02).
        ok = bool(want) and all(any(abs(g - float(w)) <= max(0.02, abs(float(w)) * 5e-4) for g in got) for w in want)
        stats["n"] += 1
        stats["called_tool"] += calls > 0
        stats["correct"] += ok
        stats["malformed_calls"] += malformed
        stats["items"].append({"user": prompt[1]["content"][:160], "want": sorted(want), "ok": ok, "calls": calls,
                               "final": final})
    return stats


def eval_hinglish(rows: list[dict]) -> dict:
    import sacrebleu

    hyps, refs = [], []
    for r in rows:
        out = chat(r["messages"][:2], r["tools"], max_tokens=300)["message"].get("content") or ""
        hyps.append(out.strip())
        refs.append(r["messages"][-1]["content"].strip())
    chrf = sacrebleu.corpus_chrf(hyps, [refs]).score
    return {"n": len(rows), "chrF": round(chrf, 2),
            "samples": [{"ref": refs[i], "hyp": hyps[i]} for i in range(min(8, len(refs)))]}


def eval_identity(system_prompt: str) -> dict:
    qs = ["Who are you?", "Which model are you running on?", "Tum kaun ho aur kis model par chalte ho?"]
    out = []
    for q in qs:
        a = chat([{"role": "system", "content": system_prompt}, {"role": "user", "content": q}], max_tokens=200)
        text = a["message"].get("content") or ""
        out.append({"q": q, "a": text, "ok": "thrones" in text.lower() and "qwen" in text.lower()})
    return {"correct": sum(x["ok"] for x in out), "n": len(out), "items": out}


def eval_sets() -> dict:
    res = {}
    for name in ("base", "hard"):
        ok = 0
        for item in SETS[name]:
            text = chat([{"role": "user", "content": item["q"]}], max_tokens=1200)["message"].get("content") or ""
            try:
                ok += bool(item["grade"](text))
            except Exception:
                pass
        res[name] = f"{ok}/{len(SETS[name])}"
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--lora", default="")
    ap.add_argument("--heldout", default=str(HELD))
    args = ap.parse_args()
    held = [json.loads(line) for line in Path(args.heldout).open(encoding="utf-8")]
    ood_rows = [r for r in held if r["meta"]["kind"] == "tool_use_ood"]
    tool_rows = [r for r in held if r["meta"]["kind"] == "tool_use"]
    hing_rows = [r for r in held if r["meta"]["kind"] == "hinglish"]
    entry = next(e for e in config.load_catalog() if e["id"] == "qwen3.5-4b-q4km")
    extra = ["--lora", str(ROOT / args.lora)] if args.lora else []
    free_app_engine()
    report = {"label": args.label, "lora": args.lora, "heldout": Path(args.heldout).name, "date": dt.datetime.now().isoformat(timespec="seconds"),
              "base_gguf": entry["file"]}
    with Server(entry, 8192, 99, extra) as srv:
        report["load_s"] = round(srv.load_s, 2)
        print("tool use…", flush=True)
        report["tool_use"] = eval_tool_use(tool_rows)
        print(f"  correct {report['tool_use']['correct']}/{report['tool_use']['n']}, called tool "
              f"{report['tool_use']['called_tool']}", flush=True)
        if ood_rows:
            report["tool_use_ood"] = eval_tool_use(ood_rows)
            print(f"  unseen question types: correct {report['tool_use_ood']['correct']}/{report['tool_use_ood']['n']}, "
                  f"called tool {report['tool_use_ood']['called_tool']}", flush=True)
        print("hinglish…", flush=True)
        report["hinglish"] = eval_hinglish(hing_rows)
        print(f"  chrF {report['hinglish']['chrF']}", flush=True)
        report["identity"] = eval_identity(held[0]["messages"][0]["content"])
        print(f"  identity {report['identity']['correct']}/3", flush=True)
        print("regression sets…", flush=True)
        report["sets"] = eval_sets()
        print(f"  {report['sets']}", flush=True)
    path = ROOT / "evals" / "results" / f"adapter-{args.label}-{dt.datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()

"""Run the eval set through the Thrones app itself (a chosen mode), to measure what the system adds over the raw model.

The app must be running (Thrones.bat). Each item is sent as a new conversation and deleted afterwards.
Unlike run_bench.py this uses the app's own sampling (not greedy), so expect some run-to-run variation.

    python evals/run_app_eval.py --mode think
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
from items import CATEGORIES, SETS  # noqa: E402

BASE = "http://127.0.0.1:8765"


def ask(client: httpx.Client, text: str, mode: str) -> tuple[dict, str | None]:
    final, cid = None, None
    with client.stream("POST", "/api/chat", json={"content": text, "mode": mode}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "start":
                    cid = ev["conversation_id"]
                elif ev["type"] == "done":
                    final = ev["message"]
    return final or {}, cid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="think", choices=["fast", "think"])
    ap.add_argument("--tag", default="")
    ap.add_argument("--set", default="base", choices=["base", "hard", "all"])
    args = ap.parse_args()
    items = SETS["base"] + SETS["hard"] if args.set == "all" else SETS[args.set]
    client = httpx.Client(base_url=BASE, timeout=900)
    status = client.get("/api/status").json()
    settings = client.get("/api/settings").json()
    rows = []
    for item in items:
        t0 = time.time()
        msg, cid = ask(client, item["q"], args.mode)
        try:
            ok = bool(item["grade"](msg.get("content", "")))
        except Exception:
            ok = False
        m = msg.get("metrics", {})
        rows.append({"id": item["id"], "cat": item["cat"], "ok": ok, "seconds": round(time.time() - t0, 2),
                     "tool_calls": m.get("tool_calls", 0), "model_calls": m.get("model_calls", 0),
                     "gen_tokens": m.get("completion_tokens", 0),
                     "verdict": next((s["title"] for s in msg.get("steps", []) if s["kind"] == "verify"), ""),
                     "revised": any(s["kind"] == "revise" for s in msg.get("steps", [])),
                     "answer": msg.get("content", "").strip()[-6000:]})
        print(f"  {item['id']:<9} {'PASS' if ok else 'fail'}  tools {rows[-1]['tool_calls']}  "
              f"{rows[-1]['seconds']:5.1f}s  {rows[-1]['verdict']}", flush=True)
        if cid:
            client.delete(f"/api/conversations/{cid}")
    by_cat = {c: [x["ok"] for x in rows if x["cat"] == c] for c in CATEGORIES}
    result = {
        "date": dt.datetime.now().isoformat(timespec="seconds"), "mode": args.mode, "eval_set": args.set,
        "model": status["resolved"], "think_settings": {k: v for k, v in settings.items() if k.startswith("think_")},
        "score": sum(x["ok"] for x in rows), "total": len(rows),
        "by_category": {c: f"{sum(v)}/{len(v)}" for c, v in by_cat.items()},
        "mean_seconds": round(sum(x["seconds"] for x in rows) / len(rows), 2),
        "items_using_tools": sum(1 for x in rows if x["tool_calls"]),
        "items_revised_after_check": sum(1 for x in rows if x["revised"]),
        "items": rows,
    }
    out = ROOT / "evals" / "results" / f"app-{args.mode}-{dt.datetime.now():%Y%m%d-%H%M}{('-' + args.tag) if args.tag else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{result['score']}/{result['total']}  {result['by_category']}  mean {result['mean_seconds']}s  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

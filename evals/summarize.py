"""Summarise every result file in evals/results as Markdown tables.

Items in maths, logic and knowledge are re-graded from the saved answer with the
current graders (they only read the final 'Answer:' line), so a grader fix
applies equally to every model. Other categories keep the grade recorded at run time.

    python evals/summarize.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
from items import CATEGORIES, SETS  # noqa: E402

GRADERS = {i["id"]: i for s in SETS.values() for i in s}
REGRADE = {"math", "logic", "knowledge"}


def regrade(rows: list[dict]) -> tuple[list[dict], int]:
    changed = 0
    out = []
    for row in rows:
        row = dict(row)
        item = GRADERS.get(row["id"])
        if item and row["cat"] in REGRADE:
            ok = bool(item["grade"](row["answer"]))
            changed += ok != row["ok"]
            row["ok"] = ok
        out.append(row)
    return out, changed


def score(rows: list[dict]) -> tuple[str, dict[str, str]]:
    by = {c: [r["ok"] for r in rows if r["cat"] == c] for c in CATEGORIES}
    return f"{sum(r['ok'] for r in rows)}/{len(rows)}", {c: f"{sum(v)}/{len(v)}" for c, v in by.items() if v}


def main() -> None:
    files = sorted((ROOT / "evals" / "results").glob("*.json"))
    perf_rows, eval_rows = [], []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if f.name.startswith("bench-"):
            set_name = data.get("eval_set", "base")
            for run in data["runs"]:
                if "error" in run:
                    eval_rows.append((f.name, run["model"], "-", set_name, "ERROR " + run["error"], {}, "", 0))
                    continue
                if run.get("perf"):
                    perf_rows.append((run, data.get("gpu_layers", 99), f.name))
                for label, e in run.get("evals", {}).items():
                    rows, changed = regrade(e["items"])
                    total, cats = score(rows)
                    eval_rows.append((f.name, run["model"], label, set_name, total, cats,
                                      f"{e['mean_seconds']}s", changed))
        elif f.name.startswith("app-"):
            rows, changed = regrade(data["items"])
            total, cats = score(rows)
            eval_rows.append((f.name, data["model"].get("model_name", "?"), f"Thrones {data['mode']}",
                              data.get("eval_set", "base"), total, cats, f"{data['mean_seconds']}s", changed))

    print("## Performance\n")
    print("| Model | GPU layers | Load | VRAM at load | Gen tok/s | First token | 10.8k-token prompt: read tok/s | first token | Needle | Peak VRAM (system) | Engine working set | Engine private |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for run, ngl, _ in perf_rows:
        p = run["perf"]
        print(f"| {run['model']} {run['quant']} | {ngl} | {run['load_s']} s | {run['vram_at_load_mb']} MB | {p['short_gen_tps']} | "
              f"{p['short_first_token_s']} s | {p['long_prompt_tps']} | {p['long_first_token_s']} s | "
              f"{'found' if p['long_needle_found'] else 'missed'} | {run.get('peak_vram_mb_system')} MB | "
              f"{run.get('peak_engine_working_set_mb', run.get('peak_engine_rss_mb'))} MB | {run.get('peak_engine_private_mb', '—')} MB |")

    print("\n## Accuracy\n")
    print("| Model | Mode | Set | Score | " + " | ".join(CATEGORIES) + " | Mean time | Regraded |")
    print("|---|---|---|---|" + "---|" * len(CATEGORIES) + "---|---|")
    for _, model, label, set_name, total, cats, secs, changed in eval_rows:
        print(f"| {model} | {label} | {set_name} | **{total}** | " + " | ".join(cats.get(c, "–") for c in CATEGORIES)
              + f" | {secs} | {changed or ''} |")


if __name__ == "__main__":
    main()

"""Measure models on THIS machine: load time, memory, speed, long-context behaviour and eval accuracy.

Starts its own llama-server per model on a private port (the Thrones app's
engine must be unloaded first; this script asks the running app to do that).
All numbers written to evals/results/ are measurements from this run.

    python evals/run_bench.py --models qwen3.5-9b-q4km qwen3.5-4b-q4km --think both
    python evals/run_bench.py --perf-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals"))

from items import CATEGORIES, SETS  # noqa: E402
from thrones import config, hardware  # noqa: E402
from thrones.runtime.llamacpp import _JOB  # noqa: E402

PORT = 8767
BASE = f"http://127.0.0.1:{PORT}"
OUT = ROOT / "evals" / "results"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LONG_DOC_PARAS = 220   # ≈ 9–10k tokens of filler with one planted fact


def vram() -> int:
    return hardware.vram_used_mb() or 0


def free_app_engine() -> None:
    try:
        httpx.post("http://127.0.0.1:8765/api/engine/unload", timeout=30)
    except httpx.HTTPError:
        pass
    time.sleep(1.5)


class Server:
    def __init__(self, entry: dict, ctx: int, ngl: int = 99) -> None:
        self.entry, self.ctx, self.ngl = entry, ctx, ngl
        self.proc: subprocess.Popen | None = None
        self.peak_vram = 0
        self.peak_rss = 0

    def __enter__(self) -> "Server":
        exe = config.find_llama_server()
        assert exe, "llama-server not found"
        self.vram_before = vram()
        log = (OUT / f"server-{self.entry['id']}-{self.ctx}.log").open("wb")
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(config.model_path(self.entry)), "--host", "127.0.0.1", "--port", str(PORT),
             "-c", str(self.ctx), "-ngl", str(self.ngl), "-np", "1", "--no-webui"],
            stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, cwd=str(exe.parent))
        _JOB.assign(self.proc.pid)   # engine exits if this script is interrupted
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited with {self.proc.returncode}")
            try:
                if httpx.get(BASE + "/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.perf_counter() - t0 > 300:
                raise RuntimeError("load timed out")
            time.sleep(0.2)
        self.load_s = time.perf_counter() - t0
        time.sleep(0.5)
        self.vram_after = vram()
        self.sample()
        return self

    def sample(self) -> None:
        self.peak_vram = max(self.peak_vram, vram())
        try:
            info = psutil.Process(self.proc.pid).memory_info()
            self.peak_rss = max(self.peak_rss, info.rss // 2**20)
            self.peak_private = max(getattr(self, "peak_private", 0), (getattr(info, "private", 0) or 0) // 2**20)
        except psutil.Error:
            pass

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        time.sleep(1.5)

    def chat(self, messages: list[dict], max_tokens: int, thinking: bool, temperature: float = 0.0) -> dict:
        kwargs: dict = {"enable_thinking": thinking}
        if self.entry["family"] == "gpt-oss":
            kwargs = {"reasoning_effort": "low"}
        if thinking and self.entry["family"] != "gpt-oss":
            # Greedy decoding makes Qwen3.5's thinking loop until the token cap (observed 12 Nov 2026,
            # 5 of 7 items hit 6000 tokens); Qwen recommends temp 0.6 / top-p 0.95 / top-k 20 for precise thinking.
            temperature, top_p, top_k = 0.6, 0.95, 20
        else:
            top_p, top_k = 1.0, (1 if temperature == 0 else 20)
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                "top_k": top_k, "stream": True, "chat_template_kwargs": kwargs}
        t0 = time.perf_counter()
        first = None
        content, reasoning, timings, finish = "", "", {}, ""
        last_sample = 0.0
        with httpx.stream("POST", BASE + "/v1/chat/completions", json=body, timeout=900) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: ") or line[6:] == "[DONE]":
                    continue
                obj = json.loads(line[6:])
                timings = obj.get("timings") or timings
                for ch in obj.get("choices", []):
                    d = ch.get("delta") or {}
                    if (d.get("content") or d.get("reasoning_content")) and first is None:
                        first = time.perf_counter() - t0
                    content += d.get("content") or ""
                    reasoning += d.get("reasoning_content") or ""
                    finish = ch.get("finish_reason") or finish
                if time.perf_counter() - last_sample > 1.0:
                    self.sample()
                    last_sample = time.perf_counter()
        self.sample()
        return {"content": content, "reasoning": reasoning, "first_token_s": first, "total_s": time.perf_counter() - t0,
                "timings": timings, "finish": finish}


def long_document() -> tuple[str, str]:
    topics = ["supply schedules", "warehouse audits", "fleet maintenance", "vendor contracts", "staff rotas"]
    paras = [f"Paragraph {i}. This section reviews {topics[i % 5]} for the quarter. "
             f"Figures were within expected ranges and no corrective action was required for item {i * 7 % 113}. "
             "Teams noted routine observations and agreed to revisit the topic at the next quarterly review. "
             for i in range(LONG_DOC_PARAS)]
    paras[LONG_DOC_PARAS * 2 // 3] += ("Special note: the backup generator at the Nashik depot was replaced on "
                                        "14 August by technician Farida Qureshi, at a cost of 3,48,000 rupees. ")
    question = "In the report above, who replaced the backup generator at the Nashik depot, and what did it cost?"
    return "\n".join(paras), question


def perf(server: Server, thinking: bool) -> dict:
    short = server.chat([{"role": "user", "content": "Explain in about 200 words why the sky is blue."}],
                        max_tokens=320, thinking=False, temperature=0.7)
    doc, q = long_document()
    long = server.chat([{"role": "user", "content": doc + "\n\n" + q}], max_tokens=200, thinking=False)
    t_short, t_long = short["timings"], long["timings"]
    ok = "farida" in long["content"].lower() and ("348" in long["content"].replace(",", "") or "3.48" in long["content"])
    return {
        "short_first_token_s": round(short["first_token_s"] or 0, 3),
        "short_gen_tps": round(t_short.get("predicted_per_second", 0), 1),
        "short_gen_tokens": t_short.get("predicted_n"),
        "long_prompt_tokens": t_long.get("prompt_n"),
        "long_prompt_tps": round(t_long.get("prompt_per_second", 0), 1),
        "long_first_token_s": round(long["first_token_s"] or 0, 2),
        "long_gen_tps": round(t_long.get("predicted_per_second", 0), 1),
        "long_needle_found": ok,
        "long_answer": long["content"].strip()[:300],
    }


def evaluate(server: Server, thinking: bool, items: list) -> dict:
    rows = []
    for item in items:
        r = server.chat([{"role": "user", "content": item["q"]}], max_tokens=6000 if thinking else 1200,
                        thinking=thinking)
        try:
            ok = bool(item["grade"](r["content"]))
        except Exception:
            ok = False
        rows.append({"id": item["id"], "cat": item["cat"], "ok": ok, "finish": r["finish"],
                     "gen_tokens": r["timings"].get("predicted_n", 0), "seconds": round(r["total_s"], 2),
                     "answer": r["content"].strip()[-6000:]})
        print(f"    {item['id']:<9} {'PASS' if ok else 'fail'}  {r['timings'].get('predicted_n', 0):>5} tok  {r['total_s']:5.1f}s",
              flush=True)
    by_cat = {c: [x["ok"] for x in rows if x["cat"] == c] for c in CATEGORIES}
    return {
        "score": sum(x["ok"] for x in rows), "total": len(rows),
        "by_category": {c: f"{sum(v)}/{len(v)}" for c, v in by_cat.items()},
        "mean_seconds": round(sum(x["seconds"] for x in rows) / len(rows), 2),
        "mean_gen_tokens": round(sum(x["gen_tokens"] for x in rows) / len(rows)),
        "truncated": sum(1 for x in rows if x["finish"] == "length"),
        "items": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--ngl", type=int, default=99, help="GPU layers; 0 = CPU only")
    ap.add_argument("--think", choices=["off", "on", "both"], default="off")
    ap.add_argument("--perf-only", action="store_true")
    ap.add_argument("--skip-perf", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--set", default="base", choices=["base", "hard", "all"])
    args = ap.parse_args()
    items = SETS["base"] + SETS["hard"] if args.set == "all" else SETS[args.set]

    OUT.mkdir(parents=True, exist_ok=True)
    catalog = [e for e in config.load_catalog() if config.model_installed(e)]
    if args.models:
        catalog = [e for e in catalog if e["id"] in args.models]
    free_app_engine()
    hw = hardware.snapshot()
    report = {"date": dt.datetime.now().isoformat(timespec="seconds"), "hardware": hw,
              "python": platform.python_version(), "ctx": args.ctx, "gpu_layers": args.ngl, "eval_set": args.set, "runs": []}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    path = OUT / f"bench-{stamp}{('-' + args.tag) if args.tag else ''}.json"

    for entry in catalog:
        modes = [False] if entry["family"] == "gpt-oss" else ({"off": [False], "on": [True], "both": [False, True]}[args.think])
        print(f"\n== {entry['name']} ({entry['quantization']}), ctx {args.ctx}", flush=True)
        try:
            with Server(entry, args.ctx, args.ngl) as srv:
                run = {"model_id": entry["id"], "model": entry["name"], "quant": entry["quantization"],
                       "file_gb": round(entry["size_bytes"] / 1e9, 2), "load_s": round(srv.load_s, 2),
                       "vram_at_load_mb": srv.vram_after - srv.vram_before}
                run["perf"] = perf(srv, False) if not args.skip_perf else {}
                if run["perf"]:
                    print(f"   load {run['load_s']}s, +{run['vram_at_load_mb']} MB VRAM, {run['perf']['short_gen_tps']} tok/s, "
                          f"long prompt {run['perf']['long_prompt_tokens']} tok @ {run['perf']['long_prompt_tps']} tok/s, "
                          f"needle {'found' if run['perf']['long_needle_found'] else 'MISSED'}", flush=True)
                run["evals"] = {}
                if not args.perf_only:
                    for thinking in modes:
                        label = "reasoning-low" if entry["family"] == "gpt-oss" else ("thinking" if thinking else "direct")
                        print(f"   eval: {label}", flush=True)
                        run["evals"][label] = evaluate(srv, thinking, items)
                        e = run["evals"][label]
                        print(f"   => {e['score']}/{e['total']}  {e['by_category']}  mean {e['mean_seconds']}s", flush=True)
                run["peak_vram_mb_system"] = srv.peak_vram
                run["peak_engine_working_set_mb"] = srv.peak_rss
                run["peak_engine_private_mb"] = getattr(srv, "peak_private", None)
        except Exception as exc:
            run = {"model_id": entry["id"], "model": entry["name"], "error": f"{type(exc).__name__}: {exc}"}
            print(f"   ERROR {run['error']}", flush=True)
        report["runs"].append(run)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

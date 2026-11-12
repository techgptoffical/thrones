"""Measure system-RAM cost of a loaded model under llama.cpp's loading modes.

For each (model, --load-mode): start llama-server, generate a short reply,
then record the engine's private bytes and working set, VRAM used, and how much
RAM the whole system has left. Writes evals/results/mem-<stamp>.json.

    python evals/mem_probe.py --models qwen3.5-9b-q4km gpt-oss-20b-mxfp4 --modes auto mmap none
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from thrones import config, hardware  # noqa: E402
from thrones.runtime.llamacpp import _JOB  # noqa: E402

PORT = 8768
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def probe(entry: dict, mode: str, ctx: int) -> dict:
    exe = config.find_llama_server()
    base = psutil.virtual_memory().available // 2**20
    vram0 = hardware.vram_used_mb() or 0
    args = [str(exe), "-m", str(config.model_path(entry)), "--host", "127.0.0.1", "--port", str(PORT),
            "-c", str(ctx), "-ngl", "99", "-np", "1", "--no-webui", "--load-mode", mode]
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW,
                            cwd=str(exe.parent))
    _JOB.assign(proc.pid)
    try:
        while True:
            if proc.poll() is not None:
                return {"model": entry["id"], "mode": mode, "error": f"exited {proc.returncode}"}
            try:
                if httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        load_s = time.perf_counter() - t0
        body = {"messages": [{"role": "user", "content": "Write two sentences about rivers."}], "max_tokens": 120,
                "chat_template_kwargs": {"enable_thinking": False, "reasoning_effort": "low"}}
        r = httpx.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", json=body, timeout=120).json()
        tps = r.get("timings", {}).get("predicted_per_second")
        time.sleep(1.0)
        info = psutil.Process(proc.pid).memory_info()
        avail = psutil.virtual_memory().available // 2**20
        return {
            "model": entry["id"], "mode": mode, "ctx": ctx, "load_s": round(load_s, 2), "gen_tps": round(tps or 0, 1),
            "engine_private_mb": getattr(info, "private", 0) // 2**20, "engine_working_set_mb": info.rss // 2**20,
            "vram_delta_mb": (hardware.vram_used_mb() or 0) - vram0,
            "system_available_before_mb": base, "system_available_after_mb": avail,
            "system_ram_taken_mb": base - avail,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--modes", nargs="+", default=["auto", "mmap", "none"])
    ap.add_argument("--ctx", type=int, default=16384)
    args = ap.parse_args()
    try:
        httpx.post("http://127.0.0.1:8765/api/engine/unload", timeout=30)
    except httpx.HTTPError:
        pass
    catalog = {e["id"]: e for e in config.load_catalog()}
    out = []
    for mid in args.models:
        for mode in args.modes:
            row = probe(catalog[mid], mode, args.ctx)
            print(json.dumps(row), flush=True)
            out.append(row)
    path = ROOT / "evals" / "results" / f"mem-{dt.datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps({"date": dt.datetime.now().isoformat(timespec="seconds"),
                                "ram_total_gb": hardware.snapshot()["ram_total_gb"], "rows": out}, indent=2),
                    encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()

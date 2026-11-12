"""Convert a trained PEFT LoRA to GGUF for llama.cpp and install it into models/.

    .venv-train\\Scripts\\python training\\export_adapter.py --run thrones-adapter-0.1

The adapter is applied at load time on top of the unmodified base GGUF
(models/Qwen_Qwen3.5-4B-Q4_K_M.gguf) with `llama-server --lora`. The base
model file is never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "runtime" / "llama.cpp-src" / "convert_lora_to_gguf.py"
BASE = ROOT / "training" / "base" / "Qwen3.5-4B"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="thrones-adapter-0.1")
    ap.add_argument("--install-name", default="")
    args = ap.parse_args()
    run = ROOT / "training" / "runs" / args.run
    out = run / f"{args.run}.gguf"
    cmd = [sys.executable, str(CONVERTER), str(run / "adapter"), "--base", str(BASE),
           "--outfile", str(out), "--outtype", "f16"]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    dest = ROOT / "models" / (args.install_name or out.name)
    shutil.copy2(out, dest)
    info = {"gguf": out.name, "bytes": out.stat().st_size, "sha256": digest, "installed_as": str(dest),
            "applies_to": "models/Qwen_Qwen3.5-4B-Q4_K_M.gguf", "converter": "llama.cpp b12289 convert_lora_to_gguf.py"}
    (run / "export.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()

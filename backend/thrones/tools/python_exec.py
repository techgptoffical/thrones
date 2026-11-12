"""Run short Python snippets written by the model.

This is NOT a security sandbox. The code runs as the current Windows user in
an isolated interpreter (-I), an empty temporary working directory, with a
hard timeout and truncated output. It is therefore disabled by default and
must be switched on by the user in Settings > Tools.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .registry import Tool

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT_S = 15
MAX_OUTPUT = 6000


def _run(code: str) -> str:
    with tempfile.TemporaryDirectory(prefix="thrones_py_") as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", str(script)],
                cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_S, creationflags=_NO_WINDOW, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return f"Error: execution exceeded {TIMEOUT_S}s and was stopped."
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts = []
    if out:
        parts.append(out[:MAX_OUTPUT])
    if err:
        parts.append("stderr:\n" + err[-2000:])
    if not parts:
        parts.append("(no output — use print() to show results)")
    if proc.returncode != 0:
        parts.append(f"exit code {proc.returncode}")
    return "\n".join(parts)


async def _handler(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    code = str(args.get("code", ""))
    if not code.strip():
        return "Error: no code given."
    return await asyncio.to_thread(_run, code)


python_exec = Tool(
    name="run_python",
    label="Running Python",
    description=(
        "Run a short, self-contained Python 3 script and return what it prints. Use for multi-step numeric work, "
        "simulations, data processing or checking an algorithm. Standard library only. Always print() results. "
        f"Stops after {TIMEOUT_S} seconds. No network or file access should be attempted."
    ),
    parameters={
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Complete Python source to run."}},
        "required": ["code"],
    },
    handler=_handler,
    timeout_s=TIMEOUT_S + 5,
)

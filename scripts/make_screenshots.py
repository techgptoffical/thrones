"""Create the README screenshots from a *demo* Thrones instance (separate data folder, real model output).

    set THRONES_DATA=...\\demo-data & set THRONES_PORT=8775 & python -m thrones --no-browser   (in backend/)
    python scripts/make_screenshots.py

Writes docs/images/{welcome-light,chat-think-dark,research-dark}.png using headless Microsoft Edge.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8775"
OUT = ROOT / "docs" / "images"
EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)


def chat(client: httpx.Client, text: str, mode: str) -> str:
    cid = None
    with client.stream("POST", f"{BASE}/api/chat", json={"content": text, "mode": mode}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "start":
                    cid = ev["conversation_id"]
                if ev["type"] == "done":
                    print(f"  {mode}: {ev['status']}, {len(ev['message']['content'])} chars", flush=True)
    return cid or ""


def shot(url: str, name: str, w: int = 1440, h: int = 900) -> None:
    out = OUT / name
    profile = ROOT / ".cache" / "edge-shot-profile"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                    f"--window-size={w},{h}", "--virtual-time-budget=8000", f"--screenshot={out}", url],
                   check=True, timeout=120, capture_output=True)
    print("  wrote", out.relative_to(ROOT), out.stat().st_size, "bytes", flush=True)


def main() -> None:
    if not EDGE:
        sys.exit("Microsoft Edge not found")
    OUT.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=900)
    for _ in range(60):
        try:
            client.get(f"{BASE}/api/status")
            break
        except httpx.HTTPError:
            time.sleep(1)
    client.patch(f"{BASE}/api/settings", json={"theme": "light"})
    shot(f"{BASE}/", "welcome-light.png")

    client.patch(f"{BASE}/api/settings", json={"theme": "dark"})
    think = chat(client, "A loan of ₹8,50,000 at 9.5% annual interest is repaid monthly over 7 years. "
                         "What is the EMI and the total interest paid? Show the working.", "think")
    chat(client, "Mujhe Hinglish mein samjhao ki GPU aur CPU mein kya fark hota hai.", "fast")
    research = chat(client, "What are the most capable open-weight language models that run on a 16 GB GPU right now?",
                    "research")
    shot(f"{BASE}/?c={think}", "chat-think-dark.png")
    shot(f"{BASE}/?c={research}", "research-dark.png")
    client.patch(f"{BASE}/api/settings", json={"theme": "system"})


if __name__ == "__main__":
    main()

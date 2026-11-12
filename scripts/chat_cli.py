"""Developer smoke test: send one message through the real API and print the event stream.

Usage (backend must be running):
    python scripts/chat_cli.py "your question" [--mode fast|think|research] [--model MODEL_ID] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

BASE = "http://127.0.0.1:8765"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--mode", default="fast")
    ap.add_argument("--model", default="")
    ap.add_argument("--conversation", default=None)
    ap.add_argument("--quiet", action="store_true", help="do not print streamed tokens or reasoning")
    args = ap.parse_args()

    body = {"content": args.prompt, "mode": args.mode, "model_id": args.model, "conversation_id": args.conversation}
    final = None
    with httpx.stream("POST", BASE + "/api/chat", json=body, timeout=None) as resp:
        if resp.status_code != 200:
            print("HTTP", resp.status_code, resp.read().decode())
            return 1
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            kind = ev["type"]
            if kind == "token":
                if not args.quiet:
                    sys.stdout.write(ev["text"])
                    sys.stdout.flush()
            elif kind == "reasoning":
                pass
            elif kind == "step":
                s = ev["step"]
                if s["state"] != "running":
                    detail = s["detail"].replace("\n", " | ")
                    print(f"\n[step:{s['kind']}:{s['state']}] {s['title']} — {detail[:400]}")
            elif kind == "start":
                print(f"[conversation {ev['conversation_id']}]")
            elif kind in ("content_reset", "content_replace"):
                print(f"\n[{kind}]")
            elif kind == "sources":
                pass
            elif kind == "title":
                print(f"\n[title] {ev['title']}")
            elif kind == "error":
                print(f"\n[ERROR] {ev['message']}")
            elif kind == "done":
                final = ev
    if final:
        msg = final["message"]
        print("\n\n=== FINAL (" + final["status"] + ") ===")
        print(msg["content"])
        print("\n=== METRICS ===")
        print(json.dumps(msg["metrics"], indent=2))
        if msg["sources"]:
            print("=== SOURCES ===")
            for s in msg["sources"]:
                print(f"  [{s.get('n', '-')}] {'*' if s.get('cited') else ' '} {s['title'][:70]} — {s.get('url', '')}"
                      f" ({s.get('date') or 'no date'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

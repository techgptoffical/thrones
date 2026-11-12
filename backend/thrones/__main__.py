"""Run with:  python -m thrones   (from the backend/ folder, inside the project venv)."""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from . import APP_NAME, config


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} local server")
    parser.add_argument("--port", type=int, default=config.API_PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open the UI in a browser")
    args = parser.parse_args()
    url = f"http://{config.API_HOST}:{args.port}"
    if not args.no_browser and config.FRONTEND_DIST.exists():
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"{APP_NAME} is running at {url}  (local only; press Ctrl+C to stop)")
    uvicorn.run("thrones.main:app", host=config.API_HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

"""Paths, defaults and the model catalog."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("THRONES_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("THRONES_DATA", ROOT / "data"))
MODELS_DIR = Path(os.environ.get("THRONES_MODELS", ROOT / "models"))
RUNTIME_DIR = ROOT / "runtime" / "llama.cpp"
CONFIG_DIR = ROOT / "config"
FRONTEND_DIST = ROOT / "frontend" / "dist"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "thrones.db"
LOG_PATH = DATA_DIR / "thrones.log"

API_HOST = "127.0.0.1"
API_PORT = int(os.environ.get("THRONES_PORT", "8765"))
LLAMA_PORT = int(os.environ.get("THRONES_LLAMA_PORT", "8766"))

for _d in (DATA_DIR, MODELS_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Every user-facing setting, with its default. The UI reads and writes these
# through /api/settings; nothing here is decorative.
DEFAULT_SETTINGS: dict[str, Any] = {
    # appearance
    "theme": "system",            # system | light | dark
    "density": "comfortable",     # comfortable | compact
    "font_scale": 100,            # percent
    # engine
    "profile": "auto",            # auto | lite | balanced | high
    "model_id": "",               # empty = chosen by profile
    "context_length": 0,          # 0 = profile default
    "gpu_layers": -1,             # -1 = auto (all layers that fit)
    "idle_unload_minutes": 15,    # 0 = keep loaded
    # sampling (None = use the mode's recommended value)
    "temperature": None,
    "top_p": None,
    "top_k": None,
    "max_tokens": 4096,
    # assistant behaviour
    "style": "balanced",          # balanced | direct | creative | technical
    "custom_instructions": "",
    "show_reasoning": True,
    # budgets for Think mode
    "think_max_tool_calls": 6,
    "think_time_budget_s": 180,
    "think_token_budget": 8000,
    "think_verify": True,
    "think_reasoning_budget": 2048,   # max thinking tokens per model call; 0 = unlimited (applied at model load)
    # network features
    "offline_mode": False,
    "web_research_enabled": True,
    "search_provider": "duckduckgo",   # duckduckgo | searxng | brave
    "searxng_url": "",
    "brave_api_key": "",
    "research_max_sources": 8,
    "research_max_rounds": 2,
    "research_time_budget_s": 300,
    # tools
    "python_tool_enabled": False,
    # memory
    "memory_enabled": True,
}

PROFILES: dict[str, dict[str, Any]] = {
    "lite": {
        "label": "Lite",
        "description": "CPU-friendly small model. Slower and less capable, runs on modest PCs.",
        "model_id": "qwen3.5-2b-q4km",
        "context_length": 4096,
        "gpu_layers": -1,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Mid-size model with a moderate context window.",
        "model_id": "qwen3.5-4b-q4km",
        "context_length": 8192,
        "gpu_layers": -1,
    },
    "high": {
        "label": "High",
        "description": "Strongest tested model with a large context window. Needs a 12–16 GB GPU.",
        "model_id": "qwen3.5-9b-q4km",
        "context_length": 16384,
        "gpu_layers": -1,
    },
}


def load_catalog() -> list[dict[str, Any]]:
    path = CONFIG_DIR / "models.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)["models"]


def model_path(entry: dict[str, Any]) -> Path:
    return MODELS_DIR / entry["file"]


def lora_path(entry: dict[str, Any]) -> Path | None:
    """Thrones adapters are a LoRA file applied on top of a base GGUF at load time."""
    return MODELS_DIR / entry["lora_file"] if entry.get("lora_file") else None


def model_installed(entry: dict[str, Any]) -> bool:
    p = model_path(entry)
    if not p.exists():
        return False
    lp = lora_path(entry)
    if lp is not None and not lp.exists():
        return False
    expected = int(entry.get("size_bytes") or 0)
    # A partially downloaded file must not look installed.
    return expected == 0 or p.stat().st_size >= expected * 0.995


def find_llama_server() -> Path | None:
    override = os.environ.get("THRONES_LLAMA_SERVER")
    if override and Path(override).exists():
        return Path(override)
    if RUNTIME_DIR.exists():
        for p in RUNTIME_DIR.rglob("llama-server.exe"):
            return p
        for p in RUNTIME_DIR.rglob("llama-server"):
            return p
    return None

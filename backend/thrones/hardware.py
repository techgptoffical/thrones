"""Hardware detection and live memory measurement. All numbers are measured, never estimated."""
from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

import psutil

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _nvidia_smi(fields: str) -> list[list[str]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [[c.strip() for c in line.split(",")] for line in out.stdout.strip().splitlines() if line.strip()]


def gpus() -> list[dict[str, Any]]:
    rows = _nvidia_smi("name,memory.total,memory.used,memory.free,driver_version,utilization.gpu")
    result = []
    for r in rows:
        try:
            result.append({
                "name": r[0],
                "vram_total_mb": int(float(r[1])),
                "vram_used_mb": int(float(r[2])),
                "vram_free_mb": int(float(r[3])),
                "driver": r[4],
                "utilization": int(float(r[5])) if r[5].replace(".", "").isdigit() else None,
                "vendor": "nvidia",
            })
        except (IndexError, ValueError):
            continue
    return result


def vram_used_mb() -> int | None:
    rows = _nvidia_smi("memory.used")
    try:
        return int(float(rows[0][0])) if rows else None
    except (IndexError, ValueError):
        return None


def cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "Unknown CPU"


def snapshot() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    g = gpus()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu_name(),
        "cpu_cores": psutil.cpu_count(logical=False) or 0,
        "cpu_threads": psutil.cpu_count(logical=True) or 0,
        "ram_total_gb": round(vm.total / 2**30, 1),
        "ram_available_gb": round(vm.available / 2**30, 1),
        "gpus": g,
        "has_gpu": bool(g),
    }


def recommend_profile(hw: dict[str, Any] | None = None) -> str:
    """Pick the strongest profile this machine can run with headroom."""
    hw = hw or snapshot()
    vram = max((g["vram_total_mb"] for g in hw["gpus"]), default=0) / 1024
    ram = hw["ram_total_gb"]
    if vram >= 11 and ram >= 12:
        return "high"
    if vram >= 5 or ram >= 15:
        return "balanced"
    return "lite"


def compatibility(entry: dict[str, Any], hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain whether a catalog model is expected to run well here."""
    hw = hw or snapshot()
    vram = max((g["vram_total_mb"] for g in hw["gpus"]), default=0) / 1024
    ram = hw["ram_total_gb"]
    size_gb = (entry.get("size_bytes") or 0) / 2**30
    need_vram = entry.get("min_vram_gb", 0)
    need_ram = entry.get("min_ram_gb", 0)
    if vram >= max(need_vram, size_gb + 1.5):
        return {"level": "ok", "message": "Fits fully on the GPU."}
    if vram > 0 and ram + vram >= size_gb + 4:
        return {"level": "warn", "message": "Will be split between GPU and system RAM; expect slower replies."}
    if ram >= max(need_ram, size_gb + 3):
        return {"level": "warn", "message": "No suitable GPU detected; will run on CPU and be slow."}
    return {"level": "bad", "message": f"Needs about {need_ram} GB RAM or {need_vram} GB VRAM; this PC has less."}

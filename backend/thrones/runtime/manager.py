"""Owns the single loaded model: selection, loading with fallback, idle unload, metrics, downloads."""
from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx
import psutil

from .. import config, db, hardware
from .base import ChatProvider, Delta, GenParams, LoadError
from .llamacpp import LlamaCppProvider


@dataclass
class Loaded:
    entry: dict[str, Any]
    context_length: int
    gpu_layers: int
    load_seconds: float
    loaded_at: float
    vram_before_mb: int | None
    vram_after_mb: int | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class MemoryPeak:
    vram_mb: int | None = None
    ram_mb: int | None = None


class ModelManager:
    def __init__(self, provider: ChatProvider | None = None) -> None:
        self.provider: ChatProvider = provider or LlamaCppProvider()
        self.loaded: Loaded | None = None
        self.load_lock = asyncio.Lock()
        self.gen_lock = asyncio.Lock()       # one generation at a time (single slot)
        self.last_used = time.monotonic()
        self.loading: str = ""               # model id currently being loaded, for the UI
        self.downloads: dict[str, dict[str, Any]] = {}
        self._download_tasks: dict[str, asyncio.Task[None]] = {}
        self._idle_task: asyncio.Task[None] | None = None

    # --------------------------------------------------------------- catalog
    def catalog(self) -> list[dict[str, Any]]:
        hw = hardware.snapshot()
        out = []
        for entry in config.load_catalog():
            item = dict(entry)
            item["installed"] = config.model_installed(entry)
            item["compatibility"] = hardware.compatibility(entry, hw)
            item["loaded"] = bool(self.loaded and self.loaded.entry["id"] == entry["id"])
            item["download"] = self.downloads.get(entry["id"])
            out.append(item)
        return out

    def entry(self, model_id: str) -> dict[str, Any] | None:
        return next((e for e in config.load_catalog() if e["id"] == model_id), None)

    def resolve(self, settings: dict[str, Any], model_override: str = "") -> tuple[dict[str, Any], int, int, str]:
        """Return (entry, context_length, gpu_layers, profile) for the current settings."""
        hw = hardware.snapshot()
        profile = settings.get("profile", "auto")
        if profile not in config.PROFILES:
            profile = hardware.recommend_profile(hw)
        preset = config.PROFILES[profile]
        installed = [e for e in config.load_catalog() if config.model_installed(e)]
        if not installed:
            raise LoadError("No model is installed yet. Download one in Settings > Models.")

        wanted = model_override or settings.get("model_id") or preset["model_id"]
        entry = next((e for e in installed if e["id"] == wanted), None)
        if entry is None:
            # Preferred model is not on disk: fall back to the largest installed one that fits the tier order.
            order = {"high": 2, "balanced": 1, "lite": 0}
            ceiling = order.get(profile, 2)
            pool = [e for e in installed if order.get(e.get("tier", "high"), 2) <= ceiling] or installed
            entry = max(pool, key=lambda e: e.get("size_bytes", 0))

        ctx = int(settings.get("context_length") or 0) or int(preset["context_length"])
        ctx = max(2048, min(ctx, int(entry.get("native_context", 32768))))
        layers = int(settings.get("gpu_layers", -1))
        if layers < 0:
            layers = 99 if hw["has_gpu"] else 0
        return entry, ctx, layers, profile

    # ---------------------------------------------------------------- loading
    async def ensure_loaded(self, settings: dict[str, Any], model_override: str = "") -> tuple[Loaded, bool]:
        """Make sure the configured model is in memory. Returns (state, freshly_loaded)."""
        entry, ctx, layers, _ = self.resolve(settings, model_override)
        async with self.load_lock:
            cur = self.loaded
            if (cur and self.provider.running() and cur.entry["id"] == entry["id"]
                    and cur.context_length == ctx and cur.gpu_layers == layers):
                self.last_used = time.monotonic()
                return cur, False

            self.loading = entry["id"]
            try:
                await self.provider.stop()
                self.loaded = None
                await asyncio.sleep(0.3)  # let the driver release VRAM before measuring the baseline
                vram_before = await asyncio.to_thread(hardware.vram_used_mb)

                # Fallback ladder: requested → half context → small context → CPU only.
                attempts = [(ctx, layers)]
                if ctx > 8192:
                    attempts.append((ctx // 2, layers))
                if ctx > 4096:
                    attempts.append((4096, layers))
                if layers > 0:
                    attempts.append((min(ctx, 4096), 0))
                warnings: list[str] = []
                last_error: Exception | None = None
                for try_ctx, try_layers in attempts:
                    t0 = time.perf_counter()
                    try:
                        await self.provider.start(config.model_path(entry), entry["id"], try_ctx, try_layers)
                    except LoadError as exc:
                        last_error = exc
                        warnings.append(
                            f"Could not load with context {try_ctx} and {try_layers} GPU layers; trying a lighter setting."
                        )
                        continue
                    load_s = time.perf_counter() - t0
                    vram_after = await asyncio.to_thread(hardware.vram_used_mb)
                    if (try_ctx, try_layers) == (ctx, layers):
                        warnings = []
                    else:
                        warnings.append(f"Loaded with reduced settings: context {try_ctx}, GPU layers {try_layers}.")
                    self.loaded = Loaded(entry, try_ctx, try_layers, round(load_s, 2), time.time(),
                                         vram_before, vram_after, warnings)
                    self.last_used = time.monotonic()
                    return self.loaded, True
                raise LoadError(f"The model could not be loaded on this hardware. {last_error}")
            finally:
                self.loading = ""

    async def unload(self) -> None:
        async with self.load_lock:
            await self.provider.stop()
            self.loaded = None

    def status(self) -> dict[str, Any]:
        cur = self.loaded if self.provider.running() else None
        if cur is None:
            return {"loaded": False, "loading": self.loading, "provider": self.provider.name}
        model_vram = None
        if cur.vram_before_mb is not None and cur.vram_after_mb is not None:
            model_vram = max(0, cur.vram_after_mb - cur.vram_before_mb)
        return {
            "loaded": True,
            "loading": self.loading,
            "provider": self.provider.name,
            "model_id": cur.entry["id"],
            "model_name": cur.entry["name"],
            "quantization": cur.entry.get("quantization", ""),
            "context_length": cur.context_length,
            "gpu_layers": cur.gpu_layers,
            "load_seconds": cur.load_seconds,
            "model_vram_mb": model_vram,
            "warnings": cur.warnings,
            "busy": self.gen_lock.locked(),
        }

    # ------------------------------------------------------------- inference
    async def stream(self, messages: list[dict[str, Any]], params: GenParams) -> AsyncIterator[Delta]:
        self.last_used = time.monotonic()
        try:
            async for delta in self.provider.stream(messages, params):
                yield delta
        finally:
            self.last_used = time.monotonic()

    @contextlib.asynccontextmanager
    async def measure_memory(self) -> AsyncIterator[MemoryPeak]:
        """Sample real GPU and process memory while a response is generated."""
        peak = MemoryPeak()
        pid = self.provider.pid()

        def sample() -> None:
            v = hardware.vram_used_mb()
            if v is not None:
                peak.vram_mb = max(peak.vram_mb or 0, v)
            if pid:
                try:
                    info = psutil.Process(pid).memory_info()
                    # Private bytes = memory the engine actually commits. The working set (rss) would also
                    # count pages of the memory-mapped model file, which the OS can drop and re-read.
                    used = getattr(info, "private", None) or info.rss
                    peak.ram_mb = max(peak.ram_mb or 0, used // 2**20)
                except psutil.Error:
                    pass

        async def loop() -> None:
            while True:
                await asyncio.to_thread(sample)
                await asyncio.sleep(1.0)

        task = asyncio.create_task(loop())
        try:
            yield peak
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await asyncio.to_thread(sample)

    # --------------------------------------------------------- idle handling
    def start_background(self) -> None:
        if self._idle_task is None:
            self._idle_task = asyncio.create_task(self._idle_loop())

    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            minutes = int(db.get_settings().get("idle_unload_minutes") or 0)
            if minutes <= 0 or self.loaded is None or self.gen_lock.locked() or self.load_lock.locked():
                continue
            if time.monotonic() - self.last_used > minutes * 60:
                await self.unload()

    async def shutdown(self) -> None:
        if self._idle_task:
            self._idle_task.cancel()
        for task in self._download_tasks.values():
            task.cancel()
        closer = getattr(self.provider, "aclose", None)
        if closer:
            await closer()
        else:
            await self.provider.stop()

    # -------------------------------------------------------------- downloads
    def start_download(self, model_id: str) -> dict[str, Any]:
        entry = self.entry(model_id)
        if entry is None:
            raise LoadError("Unknown model.")
        if db.get_settings().get("offline_mode"):
            raise LoadError("Offline mode is on. Turn it off in Settings > Privacy to download models.")
        if config.model_installed(entry):
            return {"state": "done", "received": entry.get("size_bytes", 0), "total": entry.get("size_bytes", 0)}
        task = self._download_tasks.get(model_id)
        if task and not task.done():
            return self.downloads[model_id]
        self.downloads[model_id] = {"state": "downloading", "received": 0, "total": entry.get("size_bytes", 0),
                                    "speed_bps": 0, "error": ""}
        self._download_tasks[model_id] = asyncio.create_task(self._download(entry))
        return self.downloads[model_id]

    def cancel_download(self, model_id: str) -> None:
        task = self._download_tasks.get(model_id)
        if task and not task.done():
            task.cancel()

    async def _download(self, entry: dict[str, Any]) -> None:
        state = self.downloads[entry["id"]]
        dest = config.model_path(entry)
        part = dest.with_suffix(dest.suffix + ".part")
        try:
            free = psutil.disk_usage(str(config.MODELS_DIR)).free
            have = part.stat().st_size if part.exists() else 0
            if free < entry.get("size_bytes", 0) - have + 2**30:
                raise LoadError("Not enough free disk space for this model.")
            headers = {"User-Agent": "Thrones/1.0"}
            if have:
                headers["Range"] = f"bytes={have}-"
            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, connect=15)) as client:
                async with client.stream("GET", entry["download_url"], headers=headers) as resp:
                    if resp.status_code == 200:
                        have = 0  # server ignored the range request; start over
                    elif resp.status_code != 206:
                        raise LoadError(f"Download failed: HTTP {resp.status_code}")
                    total = have + int(resp.headers.get("content-length", 0))
                    state.update(total=total or state["total"], received=have)
                    t_mark, b_mark = time.monotonic(), have
                    with part.open("ab" if have else "wb") as f:
                        async for chunk in resp.aiter_bytes(1 << 20):
                            f.write(chunk)
                            state["received"] += len(chunk)
                            now = time.monotonic()
                            if now - t_mark >= 1.0:
                                state["speed_bps"] = int((state["received"] - b_mark) / (now - t_mark))
                                t_mark, b_mark = now, state["received"]
            if state["total"] and part.stat().st_size < state["total"]:
                raise LoadError("Download ended early; press Download again to resume.")
            part.replace(dest)
            state.update(state="done", speed_bps=0)
        except asyncio.CancelledError:
            state.update(state="paused", speed_bps=0)
            raise
        except (httpx.HTTPError, OSError, LoadError) as exc:
            state.update(state="error", speed_bps=0, error=str(exc) or type(exc).__name__)

    def delete_model(self, model_id: str) -> None:
        entry = self.entry(model_id)
        if entry is None:
            raise LoadError("Unknown model.")
        if self.loaded and self.loaded.entry["id"] == model_id:
            raise LoadError("This model is loaded. Switch to another model before deleting it.")
        for p in (config.model_path(entry), config.model_path(entry).with_suffix(".gguf.part")):
            if p.exists():
                p.unlink()
        self.downloads.pop(model_id, None)


manager = ModelManager()

import asyncio
from pathlib import Path

from thrones.runtime.base import LoadError
from thrones.runtime.manager import ModelManager

ENTRY = {"id": "fake-9b", "name": "Fake 9B", "file": "fake.gguf", "size_bytes": 0, "native_context": 262144}


class FakeProvider:
    """Fails to load above `max_ctx` context, like a GPU that runs out of memory."""
    name = "fake"

    def __init__(self, max_ctx: int) -> None:
        self.max_ctx = max_ctx
        self.starts: list[tuple[int, int]] = []
        self._running = False

    async def start(self, model_file: Path, alias: str, context_length: int, gpu_layers: int) -> None:
        self.starts.append((context_length, gpu_layers))
        if context_length > self.max_ctx:
            self._running = False
            raise LoadError("out of memory (fake)")
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def running(self) -> bool:
        return self._running

    def pid(self):
        return None


def make(max_ctx: int, monkeypatch) -> tuple[ModelManager, FakeProvider]:
    prov = FakeProvider(max_ctx)
    mgr = ModelManager(provider=prov)
    monkeypatch.setattr(mgr, "resolve", lambda settings, override="": (ENTRY, 16384, 99, "high"))
    monkeypatch.setattr("thrones.runtime.manager.hardware.vram_used_mb", lambda: None)
    return mgr, prov


def test_fallback_is_kept_for_later_requests(monkeypatch):
    mgr, prov = make(max_ctx=8192, monkeypatch=monkeypatch)

    async def go():
        first, fresh1 = await mgr.ensure_loaded({})
        second, fresh2 = await mgr.ensure_loaded({})
        return first, fresh1, second, fresh2

    first, fresh1, second, fresh2 = asyncio.run(go())
    assert prov.starts == [(16384, 99), (8192, 99)]          # one failed attempt, then the fallback
    assert fresh1 and first.context_length == 8192 and first.warnings
    assert not fresh2 and second is first                    # no reload on the next message
    assert mgr.status()["fallback"] is True
    assert "out of memory" in mgr.last_load_failure


def test_force_retries_requested_settings(monkeypatch):
    mgr, prov = make(max_ctx=8192, monkeypatch=monkeypatch)

    async def go():
        await mgr.ensure_loaded({})
        prov.max_ctx = 32768                                 # memory was freed
        return await mgr.ensure_loaded({}, force=True)

    state, fresh = asyncio.run(go())
    assert fresh and state.context_length == 16384 and not state.warnings
    assert mgr.status()["fallback"] is False


def test_all_attempts_failing_raises(monkeypatch):
    mgr, prov = make(max_ctx=0, monkeypatch=monkeypatch)
    try:
        asyncio.run(mgr.ensure_loaded({}))
    except LoadError as exc:
        assert "could not be loaded" in str(exc)
    else:
        raise AssertionError("expected LoadError")
    assert prov.starts[-1][1] == 0                           # last resort was CPU-only


# ------------------------------------------------------------------ adapters: download and delete
ADAPTER = {"id": "fake-adapter", "name": "Fake adapter", "file": "base.gguf", "size_bytes": 10,
           "download_url": "https://example.invalid/base.gguf", "lora_file": "adapter.gguf",
           "lora_url": "https://example.invalid/adapter.gguf", "lora_size_bytes": 4}
BASE_ONLY = {"id": "fake-base", "name": "Fake base", "file": "base.gguf", "size_bytes": 10,
             "download_url": "https://example.invalid/base.gguf"}


def test_adapter_download_fetches_only_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr("thrones.config.MODELS_DIR", tmp_path)
    mgr = ModelManager(provider=FakeProvider(0))
    urls = [u for u, _, _ in mgr._missing_files(ADAPTER)]
    assert urls == [ADAPTER["download_url"], ADAPTER["lora_url"]]
    (tmp_path / "base.gguf").write_bytes(b"x" * 10)            # base already installed for the plain model
    assert [u for u, _, _ in mgr._missing_files(ADAPTER)] == [ADAPTER["lora_url"]]


def test_deleting_adapter_keeps_shared_base_model(tmp_path, monkeypatch):
    monkeypatch.setattr("thrones.config.MODELS_DIR", tmp_path)
    (tmp_path / "base.gguf").write_bytes(b"x" * 10)
    (tmp_path / "adapter.gguf").write_bytes(b"y" * 4)
    mgr = ModelManager(provider=FakeProvider(0))
    monkeypatch.setattr(mgr, "entry", lambda mid: ADAPTER if mid == "fake-adapter" else BASE_ONLY)
    mgr.delete_model("fake-adapter")
    assert (tmp_path / "base.gguf").exists() and not (tmp_path / "adapter.gguf").exists()
    mgr.delete_model("fake-base")
    assert not (tmp_path / "base.gguf").exists()

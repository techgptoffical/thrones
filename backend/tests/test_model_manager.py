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

"""llama.cpp provider: runs `llama-server` as a local child process bound to 127.0.0.1."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from .. import config
from .base import Delta, GenerationError, GenParams, LoadError

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class _KillOnCloseJob:
    """Windows job object that terminates the engine if Thrones itself dies or is killed.

    Without it, a crashed or force-closed app would leave llama-server holding
    gigabytes of VRAM until the next launch reaps it.
    """

    def __init__(self) -> None:
        self.handle = None
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(wintypes.HANDLE(job))
            return
        self._k32, self._wt, self.handle = k32, wintypes, job

    def assign(self, pid: int) -> None:
        if not self.handle:
            return
        proc = self._k32.OpenProcess(0x0001 | 0x0100, False, pid)  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
        if proc:
            self._k32.AssignProcessToJobObject(self._wt.HANDLE(self.handle), self._wt.HANDLE(proc))
            self._k32.CloseHandle(self._wt.HANDLE(proc))


_JOB = _KillOnCloseJob()


class LlamaCppProvider:
    name = "llama.cpp"

    def __init__(self, port: int = config.LLAMA_PORT) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._proc: subprocess.Popen[bytes] | None = None
        self.alias = ""
        self._log = config.DATA_DIR / "llama-server.log"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))

    # ------------------------------------------------------------ lifecycle
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def pid(self) -> int | None:
        return self._proc.pid if self.running() and self._proc else None

    def log_tail(self, lines: int = 12) -> str:
        try:
            text = self._log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.strip().splitlines()[-lines:])

    async def start(self, model_file: Path, alias: str, context_length: int, gpu_layers: int) -> None:
        exe = config.find_llama_server()
        if exe is None:
            raise LoadError("The llama.cpp runtime is not installed (runtime/llama.cpp/llama-server.exe is missing).")
        if not model_file.exists():
            raise LoadError(f"Model file not found: {model_file.name}")
        await self.stop()
        self.alias = alias
        args = [
            str(exe), "-m", str(model_file),
            "--host", "127.0.0.1", "--port", str(self.port),
            "-c", str(context_length), "-ngl", str(gpu_layers),
            "-np", "1", "--no-webui", "--alias", alias,
        ]
        log = self._log.open("wb")
        try:
            self._proc = subprocess.Popen(
                args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                cwd=str(exe.parent), creationflags=_NO_WINDOW,
            )
        finally:
            log.close()
        _JOB.assign(self._proc.pid)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 300
        while loop.time() < deadline:
            if self._proc.poll() is not None:
                code = self._proc.returncode
                self._proc = None
                raise LoadError(f"llama-server exited during load (code {code}).\n{self.log_tail()}")
            try:
                resp = await self._client.get(self.base + "/health", timeout=2.0)
                if resp.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
        await self.stop()
        raise LoadError("Timed out waiting for the model to load.")

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, 10)
        except subprocess.TimeoutExpired:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)

    async def aclose(self) -> None:
        await self.stop()
        await self._client.aclose()

    # ----------------------------------------------------------- inference
    def _template_kwargs(self, thinking: bool) -> dict[str, Any]:
        # gpt-oss always reasons; its chat template takes an effort level instead of an on/off switch.
        if "gpt-oss" in self.alias:
            return {"reasoning_effort": "high" if thinking else "low"}
        return {"enable_thinking": bool(thinking)}

    async def count_tokens(self, text: str) -> int | None:
        if not self.running():
            return None
        try:
            resp = await self._client.post(self.base + "/tokenize", json={"content": text}, timeout=10.0)
            return len(resp.json().get("tokens", []))
        except (httpx.HTTPError, ValueError):
            return None

    async def stream(self, messages: list[dict[str, Any]], params: GenParams) -> AsyncIterator[Delta]:
        if not self.running():
            raise GenerationError("The model is not loaded.")
        body: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "top_k": params.top_k,
            "presence_penalty": params.presence_penalty,
            "max_tokens": params.max_tokens,
            "chat_template_kwargs": self._template_kwargs(params.thinking),
        }
        if params.tools:
            body["tools"] = params.tools
        if params.json_mode:
            body["response_format"] = {"type": "json_object"}

        calls: dict[int, dict[str, Any]] = {}
        finish, timings = "", {}
        try:
            async with self._client.stream("POST", self.base + "/v1/chat/completions", json=body) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", errors="replace")
                    try:
                        detail = json.loads(detail).get("error", {}).get("message", detail)
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    raise GenerationError(f"Engine error {resp.status_code}: {str(detail)[:400]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("timings"):
                        timings = obj["timings"]
                    for choice in obj.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("reasoning_content"):
                            yield Delta("reasoning", text=delta["reasoning_content"])
                        if delta.get("content"):
                            yield Delta("content", text=delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
        except httpx.HTTPError as exc:
            if not self.running():
                raise GenerationError(
                    "The engine stopped unexpectedly, most likely out of memory. "
                    "Try a smaller context length or a smaller model.\n" + self.log_tail(6)
                ) from exc
            raise GenerationError(f"Lost connection to the engine: {type(exc).__name__}") from exc

        if calls:
            yield Delta("tool_calls", tool_calls=[calls[i] for i in sorted(calls)])
        yield Delta("final", finish_reason=finish, timings=timings)

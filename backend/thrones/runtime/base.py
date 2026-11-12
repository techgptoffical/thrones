from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Protocol


class RuntimeError_(Exception):
    """Base class for runtime failures that should be shown to the user."""


class LoadError(RuntimeError_):
    pass


class GenerationError(RuntimeError_):
    pass


@dataclass
class GenParams:
    thinking: bool = False
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    presence_penalty: float = 0.0
    max_tokens: int = 2048
    tools: list[dict[str, Any]] | None = None
    json_mode: bool = False


@dataclass
class Delta:
    """One streamed event from a provider."""
    kind: str                       # content | reasoning | tool_calls | final
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    timings: dict[str, Any] = field(default_factory=dict)


class ChatProvider(Protocol):
    name: str

    async def start(self, model_file: Path, alias: str, context_length: int, gpu_layers: int) -> None: ...
    async def stop(self) -> None: ...
    def running(self) -> bool: ...
    def pid(self) -> int | None: ...
    def stream(self, messages: list[dict[str, Any]], params: GenParams) -> AsyncIterator[Delta]: ...
    async def count_tokens(self, text: str) -> int | None: ...

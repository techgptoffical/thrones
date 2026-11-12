from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[str]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    label: str = ""               # short progress text shown in the UI
    timeout_s: float = 30.0
    network: bool = False         # needs internet; blocked in offline mode

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass
class ToolResult:
    name: str
    arguments: dict[str, Any]
    output: str
    ok: bool = True
    duration_s: float = 0.0


@dataclass
class ToolSet:
    """The tools available to one request, with per-request call accounting."""
    tools: dict[str, Tool] = field(default_factory=dict)
    max_calls: int = 6
    calls_made: int = 0
    _seen: set[str] = field(default_factory=set)

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def budget_left(self) -> int:
        return max(0, self.max_calls - self.calls_made)

    async def run(self, name: str, raw_arguments: str | dict[str, Any], ctx: dict[str, Any]) -> ToolResult:
        loop = asyncio.get_running_loop()
        start = loop.time()
        if isinstance(raw_arguments, dict):
            args = raw_arguments
        else:
            try:
                args = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError:
                return ToolResult(name, {}, "Error: arguments were not valid JSON.", ok=False)
        if not isinstance(args, dict):
            return ToolResult(name, {}, "Error: arguments must be a JSON object.", ok=False)

        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(name, args, f"Error: unknown tool '{name}'. Available: {', '.join(self.tools)}.", ok=False)

        # Identical repeated calls are refused: they waste budget and signal a loop.
        key = name + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
        if key in self._seen:
            return ToolResult(name, args, "Error: this exact call was already made. Use the earlier result.", ok=False)
        if self.calls_made >= self.max_calls:
            return ToolResult(name, args, "Error: tool budget exhausted. Answer with what you have.", ok=False)
        self._seen.add(key)
        self.calls_made += 1

        try:
            output = await asyncio.wait_for(tool.handler(args, ctx), timeout=tool.timeout_s)
            ok = True
        except asyncio.TimeoutError:
            output, ok = f"Error: tool timed out after {tool.timeout_s:.0f}s.", False
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # tool errors go back to the model, not to a crash
            output, ok = f"Error: {type(exc).__name__}: {exc}", False
        return ToolResult(name, args, str(output)[:12000], ok=ok, duration_s=loop.time() - start)

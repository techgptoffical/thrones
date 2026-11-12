"""The turn engine: builds context, runs the selected mode, records real metrics.

Modes change what actually executes:
  fast      one direct generation, thinking off, at most two tool calls
  think     plan → execute (thinking on, tool loop) → independent verify → revise if needed
  research  search → fetch → extract evidence → gap check → cited report (see research/pipeline.py)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable

from .. import db
from ..retrieval import documents
from ..runtime.base import GenerationError, GenParams, RuntimeError_
from ..runtime.manager import Loaded, manager
from ..tools.calculator import calculator
from ..tools.python_exec import python_exec
from ..tools.registry import Tool, ToolSet
from . import prompts

Emit = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class TurnRequest:
    conversation_id: str | None
    content: str
    mode: str = "fast"                     # fast | think | research
    model_id: str = ""
    document_ids: list[str] = field(default_factory=list)
    regenerate: bool = False               # redo the last assistant reply
    project_id: str | None = None


class Run:
    """Mutable state of one assistant turn; everything the UI sees goes through here."""

    def __init__(self, emit: Emit, settings: dict[str, Any], loaded: Loaded, mode: str) -> None:
        self.emit = emit
        self.settings = settings
        self.loaded = loaded
        self.mode = mode
        self.content = ""
        self.reasoning = ""
        self.steps: list[dict[str, Any]] = []
        self.sources: list[dict[str, Any]] = []
        self.started = time.perf_counter()
        self.first_token_s: float | None = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.gen_ms = 0.0
        self.model_calls = 0
        self.tool_calls = 0
        self.show_reasoning = bool(settings.get("show_reasoning", True))

    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    async def step(self, kind: str, title: str, detail: str = "", state: str = "running") -> str:
        step = {"id": db.new_id()[:10], "kind": kind, "title": title, "detail": detail, "state": state,
                "t": round(self.elapsed(), 1)}
        self.steps.append(step)
        await self.emit({"type": "step", "step": dict(step)})
        return step["id"]

    async def step_update(self, step_id: str, *, detail: str | None = None, state: str | None = None,
                          title: str | None = None) -> None:
        for step in self.steps:
            if step["id"] == step_id:
                if detail is not None:
                    step["detail"] = detail
                if state is not None:
                    step["state"] = state
                if title is not None:
                    step["title"] = title
                step["t_end"] = round(self.elapsed(), 1)
                await self.emit({"type": "step", "step": dict(step)})
                return

    async def reset_content(self) -> None:
        self.content = ""
        await self.emit({"type": "content_reset"})

    async def replace_content(self, text: str) -> None:
        self.content = text
        await self.emit({"type": "content_replace", "text": text})

    def base_params(self, thinking: bool, precise: bool = False) -> GenParams:
        s = self.settings
        technical = s.get("style") == "technical"
        if thinking:
            temp, top_p, presence = (0.6, 0.95, 0.0) if (precise or technical) else (1.0, 0.95, 1.5)
        else:
            temp, top_p, presence = (0.6, 0.9, 0.0) if (precise or technical) else (0.7, 0.8, 1.0)
        if s.get("style") == "creative" and not precise:
            temp = max(temp, 0.9)
        return GenParams(
            thinking=thinking,
            temperature=float(s["temperature"]) if s.get("temperature") is not None else temp,
            top_p=float(s["top_p"]) if s.get("top_p") is not None else top_p,
            top_k=int(s["top_k"]) if s.get("top_k") is not None else 20,
            presence_penalty=presence,
            max_tokens=int(s.get("max_tokens") or 4096),
        )


async def generate(run: Run, messages: list[dict[str, Any]], params: GenParams, *, visible: bool = True,
                   reasoning_visible: bool | None = None) -> tuple[str, list[dict[str, Any]], str]:
    """One model call. Streams to the UI when visible; always accounts tokens and time."""
    text, calls, finish = "", [], ""
    show_reasoning = run.show_reasoning and (visible if reasoning_visible is None else reasoning_visible)
    run.model_calls += 1
    async for delta in manager.stream(messages, params):
        if delta.kind in ("content", "reasoning") and run.first_token_s is None:
            run.first_token_s = run.elapsed()
        if delta.kind == "content":
            text += delta.text
            if visible:
                run.content += delta.text
                await run.emit({"type": "token", "text": delta.text})
        elif delta.kind == "reasoning":
            if show_reasoning:
                run.reasoning += delta.text
                await run.emit({"type": "reasoning", "text": delta.text})
        elif delta.kind == "tool_calls":
            calls = delta.tool_calls
        elif delta.kind == "final":
            finish = delta.finish_reason
            t = delta.timings or {}
            run.prompt_tokens += int(t.get("prompt_n", 0)) + int(t.get("cache_n", 0))
            run.completion_tokens += int(t.get("predicted_n", 0))
            run.gen_ms += float(t.get("predicted_ms", 0.0))
    return text, calls, finish


def _short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def agent_loop(run: Run, messages: list[dict[str, Any]], tools: ToolSet | None, params: GenParams, *,
                     deadline: float, token_budget: int, visible: bool = True) -> str:
    """Bounded tool loop. Ends when the model answers, or when a budget runs out."""
    start_tokens = run.completion_tokens
    max_rounds = (tools.max_calls if tools else 0) + 2
    answer = ""
    for _ in range(max_rounds):
        remaining = token_budget - (run.completion_tokens - start_tokens)
        can_use_tools = bool(tools and tools.tools and tools.budget_left() > 0
                             and time.perf_counter() < deadline and remaining > 400)
        call_params = replace(params, tools=tools.schemas() if (can_use_tools and tools) else None,
                              max_tokens=max(256, min(params.max_tokens, remaining)))
        answer, calls, _finish = await generate(run, messages, call_params, visible=visible)
        if not calls or not tools:
            return answer
        if visible and run.content:
            await run.reset_content()   # text before a tool call was interim, not the answer
        messages.append({
            "role": "assistant", "content": answer or "",
            "tool_calls": [{"id": c["id"] or db.new_id()[:12], "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls],
        })
        for call, sent in zip(calls, messages[-1]["tool_calls"]):
            if not can_use_tools or tools.budget_left() <= 0:
                messages.append({"role": "tool", "tool_call_id": sent["id"],
                                 "content": "Tool budget exhausted. Answer with what you already have."})
                continue
            tool = tools.tools.get(call["name"])
            label = tool.label if tool and tool.label else f"Using {call['name']}"
            step_id = await run.step("tool", label, _short(call["arguments"]))
            result = await tools.run(call["name"], call["arguments"], {"run": run})
            run.tool_calls += 1
            await run.step_update(step_id, detail=_short(result.output, 300), state="done" if result.ok else "error")
            messages.append({"role": "tool", "tool_call_id": sent["id"], "content": result.output})
        if not (tools.budget_left() > 0 and time.perf_counter() < deadline):
            messages.append({"role": "user", "content": prompts.BUDGET_PROMPT})
    return answer


# ------------------------------------------------------------------ helpers
def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return int(ascii_chars / 3.4 + (len(text) - ascii_chars) / 1.3) + 4


def _memory_tool() -> Tool:
    async def handler(args: dict[str, Any], ctx: dict[str, Any]) -> str:
        fact = str(args.get("fact", "")).strip()
        if not fact:
            return "Error: nothing to remember."
        if len(fact) > 400:
            return "Error: keep the fact under 400 characters."
        db.add_memory(fact, source="assistant")
        return "Saved to memory. The user can review or delete it in Settings > Memory."

    return Tool(
        name="save_memory",
        label="Saving to memory",
        description="Store one short fact about the user for future conversations. Only call this when the user "
                    "explicitly asks you to remember something.",
        parameters={"type": "object",
                    "properties": {"fact": {"type": "string", "description": "The fact, written in third person."}},
                    "required": ["fact"]},
        handler=handler,
        timeout_s=5,
    )


async def _history(run: Run, conversation: dict[str, Any], rows: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Recent turns that fit the context budget, with older turns condensed into a summary."""
    usable = [r for r in rows if r["role"] in ("user", "assistant") and r["content"].strip()]
    kept: list[dict[str, Any]] = []
    used = 0
    for row in reversed(usable):
        cost = estimate_tokens(row["content"])
        if kept and used + cost > budget:
            break
        kept.append(row)
        used += cost
    kept.reverse()
    dropped = usable[: len(usable) - len(kept)]

    summary = conversation.get("summary") or ""
    if dropped and len(dropped) > int(conversation.get("summary_count") or 0):
        step_id = await run.step("context", "Condensing earlier conversation")
        new = dropped[int(conversation.get("summary_count") or 0):]
        transcript = "\n".join(f"{r['role'].title()}: {r['content'][:1500]}" for r in new)[-9000:]
        previous = f"Existing notes:\n{summary}\n\n" if summary else ""
        try:
            text, _, _ = await generate(
                run, [{"role": "user", "content": prompts.SUMMARY_PROMPT.format(previous=previous, transcript=transcript)}],
                replace(run.base_params(False, precise=True), max_tokens=320, temperature=0.3), visible=False)
            summary = text.strip() or summary
            db.update_conversation(conversation["id"], summary=summary, summary_count=len(dropped))
            await run.step_update(step_id, state="done", detail=f"{len(dropped)} earlier messages summarised")
        except RuntimeError_:
            await run.step_update(step_id, state="error", detail="Could not summarise; older messages were dropped")

    out: list[dict[str, Any]] = []
    if dropped and summary:
        out.append({"role": "user", "content": "Notes from earlier in this conversation:\n" + summary})
        out.append({"role": "assistant", "content": "Understood. I will keep those notes in mind."})
    out.extend({"role": r["role"], "content": r["content"]} for r in kept)
    return out


# -------------------------------------------------------------------- modes
async def _fast(run: Run, messages: list[dict[str, Any]], tools: ToolSet) -> None:
    tools.max_calls = 2
    await agent_loop(run, messages, tools, run.base_params(False),
                     deadline=time.perf_counter() + 120, token_budget=int(run.settings.get("max_tokens") or 4096))


def _parse_verdict(text: str) -> tuple[str, str]:
    match = None
    for match in re.finditer(r"VERDICT:\s*(PASS|FAIL)\s*[-–—:]?\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL):
        pass
    if not match:
        return "unknown", ""
    return match.group(1).lower(), match.group(2).strip()[:800]


async def _think(run: Run, messages: list[dict[str, Any]], tools: ToolSet, question: str) -> None:
    s = run.settings
    deadline = time.perf_counter() + int(s.get("think_time_budget_s") or 180)
    budget = int(s.get("think_token_budget") or 8000)
    tools.max_calls = int(s.get("think_max_tool_calls") or 6)

    # 1. Plan — a real, separate model call whose output steers execution.
    step_id = await run.step("plan", "Planning the approach")
    plan, _, _ = await generate(
        run, messages + [{"role": "user", "content": prompts.PLAN_PROMPT}],
        replace(run.base_params(False, precise=True), max_tokens=220, temperature=0.3), visible=False)
    plan = plan.strip()
    await run.step_update(step_id, state="done", detail=plan)

    # 2. Execute — thinking on, bounded tool loop.
    step_id = await run.step("execute", "Working through the problem")
    exec_messages = [dict(m) for m in messages]
    exec_messages[0]["content"] += "\n\n" + prompts.EXECUTE_HINT.format(plan=plan or "(no plan)")
    draft = await agent_loop(run, exec_messages, tools, run.base_params(True, precise=True),
                             deadline=deadline, token_budget=budget)
    await run.step_update(step_id, state="done",
                          detail=f"{run.tool_calls} tool call(s)" if run.tool_calls else "No tools needed")

    # 3. Verify — an independent review with its own calculator budget.
    spent = run.completion_tokens
    if not s.get("think_verify", True) or not draft.strip():
        return
    if time.perf_counter() > deadline or budget - spent < 500:
        await run.step("verify", "Check skipped", "The time or token budget was used up.", state="skipped")
        return
    step_id = await run.step("verify", "Checking the answer")
    checker = ToolSet(max_calls=3)
    checker.add(calculator)
    calls_before = run.tool_calls
    review = await agent_loop(
        run, [{"role": "user", "content": prompts.VERIFY_PROMPT.format(question=question[:6000], draft=draft[:8000])}],
        # Thinking is off for the reviewer: with it on, the model often spent its whole allowance
        # reasoning and never wrote the VERDICT line (8 of 26 "inconclusive" checks, 12 Nov 2026 eval).
        checker, replace(run.base_params(False, precise=True), max_tokens=1000),
        deadline=deadline, token_budget=min(2000, budget - spent), visible=False)
    verdict, issues = _parse_verdict(review)
    rechecked = run.tool_calls - calls_before
    note = f" ({rechecked} figure(s) recomputed)" if rechecked else ""
    if verdict == "pass":
        await run.step_update(step_id, state="done", title="Answer checked", detail="No errors found" + note)
        return
    if verdict != "fail" or not issues:
        await run.step_update(step_id, state="done", title="Check inconclusive",
                              detail="The reviewer did not reach a verdict; the answer is unchanged.")
        return
    await run.step_update(step_id, state="done", title="Check found a problem", detail=issues + note)

    # 4. Revise once.
    step_id = await run.step("revise", "Correcting the answer")
    await run.reset_content()
    exec_messages.append({"role": "assistant", "content": draft})
    exec_messages.append({"role": "user", "content": prompts.REVISE_PROMPT.format(issues=issues)})
    await agent_loop(run, exec_messages, None, run.base_params(True, precise=True),
                     deadline=deadline + 60, token_budget=max(1500, budget - run.completion_tokens))
    await run.step_update(step_id, state="done", detail="Answer rewritten after the check")


# ----------------------------------------------------------------- the turn
async def run_turn(req: TurnRequest, emit: Emit) -> None:
    settings = db.get_settings()
    mode = req.mode if req.mode in ("fast", "think", "research") else "fast"

    # --- conversation and user message -----------------------------------
    conversation = db.get_conversation(req.conversation_id) if req.conversation_id else None
    if conversation is None:
        conversation = db.create_conversation(kind="research" if mode == "research" else "chat",
                                              project_id=req.project_id)
    cid = conversation["id"]
    rows = db.list_messages(cid)
    if req.regenerate:
        last_user = next((r for r in reversed(rows) if r["role"] == "user"), None)
        if last_user is None:
            await emit({"type": "error", "message": "There is nothing to regenerate."})
            return
        after = rows[rows.index(last_user) + 1:]
        if after:
            db.delete_messages_from(cid, after[0]["id"])
        user_row = last_user
        rows = rows[: rows.index(last_user)]
    else:
        if req.document_ids:
            documents.attach(req.document_ids, cid)
        attachments = [{"id": d["id"], "name": d["name"], "size": d["size"]}
                       for d in (documents.get(i) for i in req.document_ids) if d]
        user_row = db.add_message(cid, "user", req.content, mode=mode, attachments=attachments)
    question = user_row["content"]
    if mode == "research" and conversation["kind"] != "research":
        db.update_conversation(cid, kind="research")

    assistant_row = db.add_message(cid, "assistant", "", mode=mode, status="streaming")
    await emit({"type": "start", "conversation_id": cid, "user_message": user_row,
                "assistant_message_id": assistant_row["id"], "mode": mode})

    run: Run | None = None
    status, error = "complete", ""
    peak = None
    fresh_load: Loaded | None = None
    try:
        # --- engine -------------------------------------------------------
        if manager.gen_lock.locked():
            await emit({"type": "notice", "message": "Waiting for the current response to finish…"})
        async with manager.gen_lock:
            needs_load = not manager.status().get("loaded")
            load_step: dict[str, Any] | None = None
            if needs_load or manager.loaded is None:
                load_step = {"id": db.new_id()[:10], "kind": "load", "title": "Loading the model into memory",
                             "detail": "", "state": "running", "t": 0}
                await emit({"type": "step", "step": dict(load_step)})
            loaded, fresh = await manager.ensure_loaded(settings, req.model_id)
            run = Run(emit, settings, loaded, mode)
            if fresh:
                fresh_load = loaded
                detail = f"{loaded.entry['name']} ready in {loaded.load_seconds:.1f}s"
                if loaded.warnings:
                    detail += " — " + loaded.warnings[-1]
                step = load_step or {"id": db.new_id()[:10], "kind": "load", "t": 0}
                step.update(title="Model loaded", detail=detail, state="done")
                run.steps.append(step)
                await emit({"type": "step", "step": dict(step)})
            await emit({"type": "engine", "status": manager.status()})

            async with manager.measure_memory() as peak:
                # --- context ----------------------------------------------
                memories = ([m["content"] for m in db.list_memories(only_enabled=True)]
                            if settings.get("memory_enabled") else [])
                system = prompts.system_prompt(loaded.entry, settings, mode, memories)
                ctx = loaded.context_length
                reserve = min(int(settings.get("max_tokens") or 4096), ctx // (2 if mode == "think" else 3))

                doc_block, doc_used = documents.build_context(question, cid, char_budget=int(ctx * 0.33 * 3.2))
                if doc_used:
                    names = sorted({d["name"] for d in doc_used})
                    whole = all(d.get("whole") for d in doc_used)
                    await run.step("documents", "Reading attached documents",
                                   (", ".join(names) + (" (full text)" if whole
                                                         else f" — {len(doc_used)} most relevant passages")),
                                   state="done")
                    run.sources = [{"kind": "document", "title": d.get("label") or d["name"], "url": "",
                                    "snippet": d.get("excerpt", "")} for d in doc_used if not d.get("whole")]

                tools = ToolSet()
                if mode != "research":
                    tools.add(calculator)
                    if mode == "think" and settings.get("python_tool_enabled"):
                        tools.add(python_exec)
                    if settings.get("memory_enabled"):
                        tools.add(_memory_tool())
                    system += "\n\n" + prompts.TOOL_GUIDE
                    if settings.get("memory_enabled"):
                        system += " " + prompts.MEMORY_GUIDE

                history_budget = max(600, ctx - reserve - estimate_tokens(system) - estimate_tokens(doc_block) - 700)
                history = await _history(run, conversation, rows, history_budget)
                user_content = question
                if doc_block:
                    user_content = prompts.DOCUMENT_GUIDE + doc_block + "\n\nUser request:\n" + question
                messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_content}]

                # --- run the mode -------------------------------------------
                if mode == "research":
                    from ..research.pipeline import deep_research
                    await deep_research(run, question, system, history)
                elif mode == "think":
                    await _think(run, messages, tools, question)
                else:
                    await _fast(run, messages, tools)
                if mode != "research" and not run.content.strip():
                    # Never present an empty reply as a finished answer.
                    raise GenerationError(
                        "The model finished without writing an answer"
                        + (f" (it was running with only {loaded.context_length:,} tokens of context after a "
                           "reduced-settings load)" if loaded.warnings else
                           " (it may have used its whole token budget on reasoning)")
                        + ". Try again, or raise the token budget in Settings → Generation.")

                # --- title for new conversations ----------------------------
                if not rows and run.content.strip():
                    try:
                        title, _, _ = await generate(
                            run, [{"role": "user", "content": prompts.TITLE_PROMPT.format(
                                user=question[:600], assistant=run.content[:600])}],
                            GenParams(thinking=False, temperature=0.3, top_p=0.9, max_tokens=24), visible=False)
                        title = title.strip().strip('"\'').splitlines()[0][:80] if title.strip() else ""
                        if title:
                            db.update_conversation(cid, title=title)
                            await emit({"type": "title", "conversation_id": cid, "title": title})
                    except RuntimeError_:
                        pass
    except asyncio.CancelledError:
        status = "stopped"
    except RuntimeError_ as exc:
        status, error = "error", str(exc)
    except Exception as exc:  # unexpected: report honestly instead of hanging the UI
        status, error = "error", f"Unexpected error: {type(exc).__name__}: {exc}"

    # --- persist and report ------------------------------------------------
    metrics: dict[str, Any] = {}
    content = run.content if run else ""
    if run is not None:
        for step in run.steps:
            if step["state"] == "running":
                step["state"] = "stopped" if status == "stopped" else ("error" if status == "error" else "done")
        metrics = {
            "model_id": run.loaded.entry["id"],
            "model_name": run.loaded.entry["name"],
            "quantization": run.loaded.entry.get("quantization", ""),
            "context_length": run.loaded.context_length,
            "first_token_s": round(run.first_token_s, 2) if run.first_token_s is not None else None,
            "total_s": round(run.elapsed(), 2),
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "tokens_per_second": round(run.completion_tokens / (run.gen_ms / 1000), 1) if run.gen_ms > 0 else None,
            "model_calls": run.model_calls,
            "tool_calls": run.tool_calls,
            "peak_vram_mb": peak.vram_mb if peak else None,
            "peak_ram_mb": peak.ram_mb if peak else None,
            "load_seconds": fresh_load.load_seconds if fresh_load else None,
        }
    db.update_message(
        assistant_row["id"], content=content, reasoning=run.reasoning if run else "",
        steps=run.steps if run else [], sources=run.sources if run else [], metrics=metrics,
        status=status, model_id=metrics.get("model_id", ""),
    )
    if status == "error":
        await emit({"type": "error", "message": error})
    await emit({"type": "done", "status": status, "message": db.get_message(assistant_row["id"])})

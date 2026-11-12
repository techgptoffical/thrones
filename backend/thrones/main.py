"""Thrones local API. Binds to 127.0.0.1 only; serves the built UI and a JSON/SSE API."""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
from typing import Any

import psutil
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import APP_NAME, __version__, config, db, hardware
from .reasoning.engine import TurnRequest, run_turn
from .research.net import internet_available
from .retrieval import documents
from .runtime.base import LoadError, RuntimeError_
from .runtime.manager import manager


def _reap_stale_engine() -> None:
    """Stop a llama-server left behind by a previous Thrones session (our binary, our port only)."""
    exe = config.find_llama_server()
    if exe is None:
        return
    for proc in psutil.process_iter(["exe", "cmdline"]):
        try:
            if proc.info["exe"] and str(exe).lower() == proc.info["exe"].lower():
                cmd = proc.info["cmdline"] or []
                if "--port" in cmd and cmd[cmd.index("--port") + 1] == str(config.LLAMA_PORT):
                    proc.terminate()
        except (psutil.Error, IndexError, ValueError):
            continue


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    await asyncio.to_thread(_reap_stale_engine)
    manager.start_background()
    yield
    for task in list(RUNS.values()):
        task.cancel()
    await manager.shutdown()
    db.close()


app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

RUNS: dict[str, asyncio.Task[None]] = {}


@app.exception_handler(RuntimeError_)
async def _runtime_error(_: Request, exc: RuntimeError_) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


# ------------------------------------------------------------------- status
@app.get("/api/status")
async def status() -> dict[str, Any]:
    hw = await asyncio.to_thread(hardware.snapshot)
    settings = db.get_settings()
    resolved: dict[str, Any] | None = None
    try:
        entry, ctx, layers, profile = manager.resolve(settings)
        resolved = {"model_id": entry["id"], "model_name": entry["name"], "context_length": ctx,
                    "gpu_layers": layers, "profile": profile}
    except LoadError as exc:
        resolved = {"error": str(exc)}
    return {
        "app": APP_NAME, "version": __version__,
        "engine": manager.status(),
        "hardware": hw,
        "recommended_profile": hardware.recommend_profile(hw),
        "resolved": resolved,
        "runtime_installed": config.find_llama_server() is not None,
        "paths": {"data": str(config.DATA_DIR), "models": str(config.MODELS_DIR),
                  "database": str(config.DB_PATH), "uploads": str(config.UPLOADS_DIR)},
        "profiles": config.PROFILES,
    }


@app.get("/api/connectivity")
async def connectivity() -> dict[str, Any]:
    settings = db.get_settings()
    if settings.get("offline_mode"):
        return {"online": False, "reason": "offline_mode"}
    return {"online": await internet_available(3.0), "reason": ""}


# ------------------------------------------------------------------- models
@app.get("/api/models")
async def models() -> dict[str, Any]:
    return {"models": await asyncio.to_thread(manager.catalog)}


@app.post("/api/models/{model_id}/download")
async def model_download(model_id: str) -> dict[str, Any]:
    return manager.start_download(model_id)


@app.post("/api/models/{model_id}/cancel")
async def model_cancel(model_id: str) -> dict[str, Any]:
    manager.cancel_download(model_id)
    return {"ok": True}


@app.delete("/api/models/{model_id}")
async def model_delete(model_id: str) -> dict[str, Any]:
    manager.delete_model(model_id)
    return {"ok": True}


class LoadBody(BaseModel):
    model_id: str = ""


@app.post("/api/engine/load")
async def engine_load(body: LoadBody) -> dict[str, Any]:
    if manager.gen_lock.locked():
        raise HTTPException(409, "A response is being generated. Stop it before switching models.")
    await manager.ensure_loaded(db.get_settings(), body.model_id, force=True)
    return manager.status()


@app.post("/api/engine/unload")
async def engine_unload() -> dict[str, Any]:
    if manager.gen_lock.locked():
        raise HTTPException(409, "A response is being generated.")
    await manager.unload()
    return manager.status()


# ----------------------------------------------------------------- settings
@app.get("/api/settings")
async def settings_get() -> dict[str, Any]:
    return db.get_settings()


@app.patch("/api/settings")
async def settings_patch(patch: dict[str, Any]) -> dict[str, Any]:
    return db.update_settings(patch)


@app.post("/api/settings/reset")
async def settings_reset() -> dict[str, Any]:
    db.execute("DELETE FROM settings")
    return db.get_settings()


# ------------------------------------------------------------ conversations
@app.get("/api/conversations")
async def conversations(search: str = "") -> dict[str, Any]:
    return {"conversations": db.list_conversations(search), "projects": db.list_projects()}


@app.get("/api/conversations/{cid}")
async def conversation(cid: str) -> dict[str, Any]:
    conv = db.get_conversation(cid)
    if conv is None:
        raise HTTPException(404, "Conversation not found.")
    return {"conversation": conv, "messages": db.list_messages(cid), "documents": documents.list_for(cid)}


class ConversationPatch(BaseModel):
    title: str | None = None
    project_id: str | None = None
    clear_project: bool = False


@app.patch("/api/conversations/{cid}")
async def conversation_patch(cid: str, body: ConversationPatch) -> dict[str, Any]:
    if db.get_conversation(cid) is None:
        raise HTTPException(404, "Conversation not found.")
    fields: dict[str, Any] = {}
    if body.title is not None:
        fields["title"] = body.title.strip()[:120] or "Untitled"
    if body.project_id is not None:
        fields["project_id"] = body.project_id
    if body.clear_project:
        fields["project_id"] = None
    db.update_conversation(cid, **fields)
    return {"conversation": db.get_conversation(cid)}


@app.delete("/api/conversations/{cid}")
async def conversation_delete(cid: str) -> dict[str, Any]:
    documents.delete_for_conversation(cid)
    db.delete_conversation(cid)
    return {"ok": True}


def _markdown_export(conv: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    lines = [f"# {conv['title']}", "",
             f"_Exported from {APP_NAME} on {dt.datetime.now():%Y-%m-%d %H:%M}_", ""]
    for m in messages:
        who = "You" if m["role"] == "user" else APP_NAME
        meta = ""
        if m["role"] == "assistant" and m["metrics"].get("model_name"):
            meta = f" · {m['metrics']['model_name']} · {m['mode']}"
        lines += [f"## {who}{meta}", "", m["content"].strip(), ""]
        web = [s for s in m["sources"] if s.get("kind") == "web"]
        if web:
            lines.append("**Sources**")
            lines += [f"{s['n']}. [{s['title']}]({s['url']})" + (f" — {s['date']}" if s.get("date") else "")
                      for s in web]
            lines.append("")
    return "\n".join(lines)


@app.get("/api/conversations/{cid}/export")
async def conversation_export(cid: str, format: str = "md") -> Response:
    conv = db.get_conversation(cid)
    if conv is None:
        raise HTTPException(404, "Conversation not found.")
    messages = db.list_messages(cid)
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in conv["title"])[:60].strip() or "chat"
    if format == "json":
        body = json.dumps({"conversation": conv, "messages": messages}, ensure_ascii=False, indent=2)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.json"'})
    return Response(_markdown_export(conv, messages), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.md"'})


# ----------------------------------------------------------------- projects
class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@app.post("/api/projects")
async def project_create(body: NameBody) -> dict[str, Any]:
    return db.create_project(body.name)


@app.patch("/api/projects/{pid}")
async def project_rename(pid: str, body: NameBody) -> dict[str, Any]:
    db.rename_project(pid, body.name)
    return {"ok": True}


@app.delete("/api/projects/{pid}")
async def project_delete(pid: str) -> dict[str, Any]:
    db.delete_project(pid)
    return {"ok": True}


# --------------------------------------------------------------------- chat
class ChatBody(BaseModel):
    conversation_id: str | None = None
    content: str = ""
    mode: str = "fast"
    model_id: str = ""
    document_ids: list[str] = []
    regenerate: bool = False
    project_id: str | None = None


@app.post("/api/chat")
async def chat(body: ChatBody, request: Request) -> StreamingResponse:
    if not body.regenerate and not body.content.strip():
        raise HTTPException(400, "Message is empty.")
    run_id = db.new_id()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        queue.put_nowait(event)

    async def worker() -> None:
        try:
            await run_turn(TurnRequest(**body.model_dump()), emit)
        finally:
            queue.put_nowait(None)
            RUNS.pop(run_id, None)

    task = asyncio.create_task(worker())
    RUNS[run_id] = task

    async def stream():
        yield f"data: {json.dumps({'type': 'run', 'run_id': run_id})}\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()   # browser went away or pressed stop: free the GPU immediately

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat/{run_id}/stop")
async def chat_stop(run_id: str) -> dict[str, Any]:
    task = RUNS.get(run_id)
    if task and not task.done():
        task.cancel()
        return {"stopped": True}
    return {"stopped": False}


# ---------------------------------------------------------------- documents
@app.post("/api/documents")
async def document_upload(file: UploadFile = File(...), conversation_id: str = Form("")) -> dict[str, Any]:
    data = await file.read()
    try:
        return await asyncio.to_thread(documents.ingest, file.filename or "document", data,
                                       conversation_id or None, file.content_type or "")
    except documents.DocumentError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/documents")
async def document_list(conversation_id: str = "") -> dict[str, Any]:
    return {"documents": documents.list_for(conversation_id or None),
            "supported": sorted(documents.SUPPORTED)}


@app.delete("/api/documents/{doc_id}")
async def document_delete(doc_id: str) -> dict[str, Any]:
    documents.delete(doc_id)
    return {"ok": True}


# ------------------------------------------------------------------- memory
class MemoryBody(BaseModel):
    content: str | None = Field(default=None, max_length=600)
    enabled: bool | None = None


@app.get("/api/memory")
async def memory_list() -> dict[str, Any]:
    return {"memories": db.list_memories(), "enabled": bool(db.get_settings().get("memory_enabled"))}


@app.post("/api/memory")
async def memory_add(body: MemoryBody) -> dict[str, Any]:
    if not (body.content or "").strip():
        raise HTTPException(400, "Memory text is empty.")
    return db.add_memory(body.content or "")


@app.patch("/api/memory/{mid}")
async def memory_update(mid: str, body: MemoryBody) -> dict[str, Any]:
    db.update_memory(mid, body.content, body.enabled)
    return {"ok": True}


@app.delete("/api/memory/{mid}")
async def memory_delete(mid: str) -> dict[str, Any]:
    db.delete_memory(mid)
    return {"ok": True}


@app.delete("/api/memory")
async def memory_clear() -> dict[str, Any]:
    db.clear_memories()
    return {"ok": True}


# ------------------------------------------------------------ personal data
@app.get("/api/export")
async def export_all() -> Response:
    convs = db.list_conversations()
    payload = {
        "app": APP_NAME, "version": __version__, "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "settings": {k: v for k, v in db.get_settings().items() if k != "brave_api_key"},
        "memories": db.list_memories(),
        "projects": db.list_projects(),
        "conversations": [{**c, "messages": db.list_messages(c["id"])} for c in convs],
        "documents": documents.list_for(None),
    }
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="thrones-export.json"'})


@app.delete("/api/data/conversations")
async def delete_all_conversations() -> dict[str, Any]:
    for doc in documents.list_for(None):
        documents.delete(doc["id"])
    db.execute("DELETE FROM messages")
    db.execute("DELETE FROM conversations")
    return {"ok": True}


# ----------------------------------------------------------------- frontend
@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str) -> Response:
    if path.startswith("api/"):
        raise HTTPException(404, "Not found.")
    dist = config.FRONTEND_DIST
    if not dist.exists():
        return JSONResponse({"detail": "The UI has not been built. Run: npm run build (in frontend/)."}, 503)
    target = (dist / path).resolve()
    if path and target.is_file() and dist.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

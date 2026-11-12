"""SQLite persistence. One local file; nothing leaves the machine."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    kind TEXT NOT NULL DEFAULT 'chat',
    project_id TEXT,
    summary TEXT NOT NULL DEFAULT '',
    summary_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    reasoning TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'fast',
    model_id TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL DEFAULT '[]',
    sources TEXT NOT NULL DEFAULT '[]',
    metrics TEXT NOT NULL DEFAULT '{}',
    attachments TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'complete',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'user',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    n_chunks INTEGER NOT NULL DEFAULT 0,
    n_chars INTEGER NOT NULL DEFAULT 0,
    conversation_id TEXT,
    path TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text, doc_id UNINDEXED, chunk_index UNINDEXED, page UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            # Publish the connection only once it is fully initialised, so a failed
            # start-up cannot leave a half-built connection cached for later calls.
            fresh = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
            try:
                fresh.row_factory = sqlite3.Row
                fresh.execute("PRAGMA journal_mode=WAL")
                fresh.execute("PRAGMA foreign_keys=ON")
                fresh.executescript(SCHEMA)
            except Exception:
                fresh.close()
                raise
            _conn = fresh
        return _conn


def close() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    with _lock:
        return conn().execute(sql, tuple(params))


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> float:
    return time.time()


# ---------------------------------------------------------------- settings
def get_settings() -> dict[str, Any]:
    out = dict(config.DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        if row["key"] in out:
            try:
                out[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                pass
    return out


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if key not in config.DEFAULT_SETTINGS:
            continue
        execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
    return get_settings()


# ----------------------------------------------------------- conversations
def create_conversation(title: str = "New chat", kind: str = "chat", project_id: str | None = None) -> dict[str, Any]:
    cid, t = new_id(), now()
    execute(
        "INSERT INTO conversations(id, title, kind, project_id, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (cid, title, kind, project_id, t, t),
    )
    return get_conversation(cid)  # type: ignore[return-value]


def get_conversation(cid: str) -> dict[str, Any] | None:
    return one("SELECT * FROM conversations WHERE id = ?", (cid,))


def list_conversations(search: str = "") -> list[dict[str, Any]]:
    if search.strip():
        like = f"%{search.strip()}%"
        return query(
            "SELECT DISTINCT c.* FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
            "WHERE c.title LIKE ? OR m.content LIKE ? ORDER BY c.updated_at DESC LIMIT 200",
            (like, like),
        )
    return query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 500")


def update_conversation(cid: str, **fields: Any) -> None:
    allowed = {"title", "kind", "project_id", "summary", "summary_count"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    sets.append("updated_at = ?")
    vals.append(now())
    vals.append(cid)
    execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", vals)


def delete_conversation(cid: str) -> None:
    execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
    execute("DELETE FROM conversations WHERE id = ?", (cid,))


_JSON_FIELDS = ("steps", "sources", "metrics", "attachments")


def _decode_message(row: dict[str, Any]) -> dict[str, Any]:
    for f in _JSON_FIELDS:
        try:
            row[f] = json.loads(row[f])
        except (json.JSONDecodeError, TypeError):
            row[f] = [] if f != "metrics" else {}
    return row


def add_message(conversation_id: str, role: str, content: str = "", **extra: Any) -> dict[str, Any]:
    mid = extra.pop("id", None) or new_id()
    row = {
        "id": mid,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "reasoning": extra.get("reasoning", ""),
        "mode": extra.get("mode", "fast"),
        "model_id": extra.get("model_id", ""),
        "steps": json.dumps(extra.get("steps", [])),
        "sources": json.dumps(extra.get("sources", [])),
        "metrics": json.dumps(extra.get("metrics", {})),
        "attachments": json.dumps(extra.get("attachments", [])),
        "status": extra.get("status", "complete"),
        "created_at": now(),
    }
    execute(
        "INSERT INTO messages(id, conversation_id, role, content, reasoning, mode, model_id, steps, sources, "
        "metrics, attachments, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(row.values()),
    )
    execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conversation_id))
    return get_message(mid)  # type: ignore[return-value]


def update_message(mid: str, **fields: Any) -> None:
    sets, vals = [], []
    for k, v in fields.items():
        if k in _JSON_FIELDS:
            v = json.dumps(v)
        if k in {"content", "reasoning", "status", "mode", "model_id", *_JSON_FIELDS}:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return
    vals.append(mid)
    execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", vals)


def get_message(mid: str) -> dict[str, Any] | None:
    row = one("SELECT * FROM messages WHERE id = ?", (mid,))
    return _decode_message(row) if row else None


def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    rows = query(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC", (conversation_id,)
    )
    return [_decode_message(r) for r in rows]


def delete_messages_from(conversation_id: str, message_id: str) -> None:
    """Delete a message and everything after it (used by regenerate / edit)."""
    row = one("SELECT rowid AS rid FROM messages WHERE id = ? AND conversation_id = ?", (message_id, conversation_id))
    if row:
        execute("DELETE FROM messages WHERE conversation_id = ? AND rowid >= ?", (conversation_id, row["rid"]))


# ---------------------------------------------------------------- projects
def list_projects() -> list[dict[str, Any]]:
    return query("SELECT * FROM projects ORDER BY created_at ASC")


def create_project(name: str) -> dict[str, Any]:
    pid = new_id()
    execute("INSERT INTO projects(id, name, created_at) VALUES(?,?,?)", (pid, name.strip() or "Untitled", now()))
    return one("SELECT * FROM projects WHERE id = ?", (pid,))  # type: ignore[return-value]


def rename_project(pid: str, name: str) -> None:
    execute("UPDATE projects SET name = ? WHERE id = ?", (name.strip() or "Untitled", pid))


def delete_project(pid: str) -> None:
    execute("UPDATE conversations SET project_id = NULL WHERE project_id = ?", (pid,))
    execute("DELETE FROM projects WHERE id = ?", (pid,))


# ---------------------------------------------------------------- memories
def list_memories(only_enabled: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM memories"
    if only_enabled:
        sql += " WHERE enabled = 1"
    return query(sql + " ORDER BY created_at ASC")


def add_memory(content: str, source: str = "user") -> dict[str, Any]:
    mid, t = new_id(), now()
    execute(
        "INSERT INTO memories(id, content, enabled, source, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (mid, content.strip(), 1, source, t, t),
    )
    return one("SELECT * FROM memories WHERE id = ?", (mid,))  # type: ignore[return-value]


def update_memory(mid: str, content: str | None = None, enabled: bool | None = None) -> None:
    if content is not None:
        execute("UPDATE memories SET content = ?, updated_at = ? WHERE id = ?", (content.strip(), now(), mid))
    if enabled is not None:
        execute("UPDATE memories SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, now(), mid))


def delete_memory(mid: str) -> None:
    execute("DELETE FROM memories WHERE id = ?", (mid,))


def clear_memories() -> None:
    execute("DELETE FROM memories")

import sqlite3

import pytest

from thrones import db
from thrones.retrieval import documents


def test_settings_defaults_and_unknown_keys_ignored():
    s = db.get_settings()
    assert s["memory_enabled"] is True and s["offline_mode"] is False
    s = db.update_settings({"offline_mode": True, "not_a_setting": 1})
    assert s["offline_mode"] is True and "not_a_setting" not in s


def test_conversation_and_message_roundtrip():
    c = db.create_conversation()
    db.add_message(c["id"], "user", "hi")
    a = db.add_message(c["id"], "assistant", "", status="streaming")
    db.update_message(a["id"], content="hello", status="complete", steps=[{"id": "x"}], metrics={"tokens_per_second": 50})
    msgs = db.list_messages(c["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["steps"] == [{"id": "x"}] and msgs[1]["metrics"]["tokens_per_second"] == 50


def test_delete_messages_from_truncates_tail_only():
    c = db.create_conversation()
    ids = [db.add_message(c["id"], r, t)["id"] for r, t in
           [("user", "a"), ("assistant", "b"), ("user", "c"), ("assistant", "d")]]
    db.delete_messages_from(c["id"], ids[3])
    assert [m["content"] for m in db.list_messages(c["id"])] == ["a", "b", "c"]


def test_search_matches_title_and_content():
    c1 = db.create_conversation(title="Tax questions")
    c2 = db.create_conversation(title="Other")
    db.add_message(c2["id"], "user", "tell me about quokkas")
    assert [c["id"] for c in db.list_conversations("tax")] == [c1["id"]]
    assert [c["id"] for c in db.list_conversations("quokka")] == [c2["id"]]


def test_project_delete_keeps_conversations():
    p = db.create_project("Work")
    c = db.create_conversation(project_id=p["id"])
    db.delete_project(p["id"])
    assert db.get_conversation(c["id"])["project_id"] is None


def test_memory_crud():
    m = db.add_memory("Prefers Hinglish")
    db.update_memory(m["id"], enabled=False)
    assert db.list_memories(only_enabled=True) == []
    db.update_memory(m["id"], content="Prefers Hindi")
    assert db.list_memories()[0]["content"] == "Prefers Hindi"
    db.delete_memory(m["id"])
    assert db.list_memories() == []


def test_connection_not_cached_after_failed_init(monkeypatch):
    db.close()
    good = db.SCHEMA
    monkeypatch.setattr(db, "SCHEMA", "CREATE TABLE broken (")
    with pytest.raises(sqlite3.Error):
        db.conn()
    monkeypatch.setattr(db, "SCHEMA", good)
    assert db.list_conversations() == []   # retry succeeds with a fresh connection


def test_document_ingest_chunk_and_search():
    body = ("Filler sentence about nothing in particular. " * 60 + "\n\n") * 6
    body += "The secret launch code word is TANGERINE and it was set in 2021.\n\n"
    body += ("More filler text for padding purposes only. " * 60 + "\n\n") * 6
    c = db.create_conversation()
    doc = documents.ingest("notes.txt", body.encode(), c["id"])
    assert doc["n_chunks"] > 3
    hits = documents.search("what is the launch code word", [doc["id"]], limit=2)
    assert any("TANGERINE" in h["text"] for h in hits)
    ctx, used = documents.build_context("launch code word", c["id"], char_budget=3000)
    assert "TANGERINE" in ctx and used and not used[0]["whole"]
    small_ctx, small_used = documents.build_context("anything", c["id"], char_budget=10**7)
    assert small_used[0]["whole"]
    documents.delete(doc["id"])
    assert documents.list_for(c["id"]) == []


def test_document_rejects_unsupported_and_empty():
    with pytest.raises(documents.DocumentError):
        documents.ingest("tool.exe", b"MZ", None)
    with pytest.raises(documents.DocumentError):
        documents.ingest("empty.txt", b"   ", None)

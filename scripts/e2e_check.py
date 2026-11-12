"""End-to-end checks against a RUNNING Thrones backend with a real model.

Every check talks to the real API; nothing is mocked. A check is only
reported as PASS when its assertion actually held.

    python scripts/e2e_check.py            # all checks
    python scripts/e2e_check.py --skip-web # skip the checks that need internet
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time

import httpx

BASE = "http://127.0.0.1:8765"
client = httpx.Client(base_url=BASE, timeout=600)
results: list[tuple[str, bool, str]] = []
created: list[str] = []


def chat(content: str = "", mode: str = "fast", conversation_id: str | None = None, regenerate: bool = False,
         document_ids: list[str] | None = None, stop_after_tokens: int = 0) -> dict:
    """Send one turn, return {"events": [...], "final": message, "conversation_id": id}."""
    body = {"content": content, "mode": mode, "conversation_id": conversation_id, "regenerate": regenerate,
            "document_ids": document_ids or []}
    out: dict = {"events": [], "final": None, "conversation_id": conversation_id, "status": None, "tokens": 0,
                 "resets": 0}
    run_id = None
    with client.stream("POST", "/api/chat", json=body) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            out["events"].append(ev["type"])
            if ev["type"] == "run":
                run_id = ev["run_id"]
            elif ev["type"] == "start":
                out["conversation_id"] = ev["conversation_id"]
                if ev["conversation_id"] not in created:
                    created.append(ev["conversation_id"])
            elif ev["type"] == "token":
                out["tokens"] += 1
                if stop_after_tokens and out["tokens"] == stop_after_tokens:
                    threading.Thread(target=lambda: httpx.post(f"{BASE}/api/chat/{run_id}/stop", timeout=10)).start()
            elif ev["type"] == "content_reset":
                out["resets"] += 1
            elif ev["type"] == "done":
                out["final"], out["status"] = ev["message"], ev["status"]
    return out


def check(name: str):
    def deco(fn):
        def run() -> None:
            t0 = time.time()
            try:
                detail = fn() or ""
                results.append((name, True, f"{detail} ({time.time() - t0:.1f}s)"))
                print(f"PASS  {name}  {detail} ({time.time() - t0:.1f}s)", flush=True)
            except AssertionError as exc:
                results.append((name, False, str(exc)))
                print(f"FAIL  {name}  {exc}", flush=True)
            except Exception as exc:
                results.append((name, False, f"{type(exc).__name__}: {exc}"))
                print(f"ERROR {name}  {type(exc).__name__}: {exc}", flush=True)
        run.__name__ = fn.__name__
        return run
    return deco


@check("status reports real hardware and an installed model")
def t_status():
    s = client.get("/api/status").json()
    assert s["runtime_installed"], "llama.cpp runtime not found"
    assert s["hardware"]["ram_total_gb"] > 1, "no RAM reading"
    assert s["resolved"] and "model_id" in s["resolved"], s["resolved"]
    return f"{s['resolved']['model_name']}, profile {s['resolved']['profile']}"


@check("fast chat streams tokens and stores real metrics")
def t_fast():
    r = chat("Reply with exactly the word: pineapple")
    m = r["final"]
    assert r["status"] == "complete", r["status"]
    assert "pineapple" in m["content"].lower(), m["content"]
    assert r["tokens"] >= 1 and m["metrics"]["tokens_per_second"], m["metrics"]
    assert m["metrics"]["completion_tokens"] > 0 and m["metrics"]["first_token_s"] is not None
    return f"{m['metrics']['tokens_per_second']} tok/s, first token {m['metrics']['first_token_s']}s"


@check("conversation persists and keeps context across turns")
def t_context():
    r1 = chat("My favourite number is 7391. Just acknowledge it.")
    cid = r1["conversation_id"]
    r2 = chat("What is my favourite number? Answer with the number only.", conversation_id=cid)
    assert "7391" in r2["final"]["content"], r2["final"]["content"]
    saved = client.get(f"/api/conversations/{cid}").json()
    assert len(saved["messages"]) == 4, len(saved["messages"])
    assert saved["conversation"]["title"] != "New chat", "title was not generated"
    return f"4 messages saved, title '{saved['conversation']['title']}'"


@check("regenerate replaces the last reply instead of appending")
def t_regenerate():
    r1 = chat("Name one primary colour. One word.")
    cid = r1["conversation_id"]
    r2 = chat(conversation_id=cid, regenerate=True)
    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert r2["status"] == "complete" and len(msgs) == 2, f"{r2['status']} with {len(msgs)} messages"
    assert msgs[1]["id"] != r1["final"]["id"], "assistant message was not replaced"
    return "2 messages after regenerate"


@check("stop cancels generation and saves the partial reply as stopped")
def t_stop():
    t0 = time.time()
    r = chat("Write a 900 word essay about the history of the printing press.", stop_after_tokens=25)
    took = time.time() - t0
    assert r["status"] == "stopped", r["status"]
    assert 0 < len(r["final"]["content"]) < 2500, len(r["final"]["content"])
    assert took < 12, f"took {took:.1f}s to stop"
    time.sleep(0.5)
    assert not client.get("/api/status").json()["engine"]["busy"], "engine still busy after stop"
    return f"stopped after {len(r['final']['content'])} chars in {took:.1f}s"


@check("think mode plans, uses the calculator, verifies, and is correct")
def t_think():
    r = chat("Compute 48213 * 9917 - 1234567 exactly. Give the final integer.", mode="think")
    m = r["final"]
    kinds = [s["kind"] for s in m["steps"]]
    assert "plan" in kinds and "execute" in kinds, kinds
    assert m["metrics"]["tool_calls"] >= 1, "calculator was not used"
    answer = m["content"].replace(",", "").replace(" ", "")
    assert "476893754" in answer, m["content"][-300:]
    assert "verify" in kinds, kinds
    return f"{m['metrics']['tool_calls']} tool calls, {m['metrics']['model_calls']} model calls, steps {kinds}"


@check("fast and think really differ in backend behaviour")
def t_modes_differ():
    q = "Is 1001 a prime number? Answer briefly."
    fast, think = chat(q, mode="fast")["final"], chat(q, mode="think")["final"]
    assert not fast["reasoning"], "fast mode produced reasoning"
    assert think["reasoning"], "think mode produced no reasoning"
    assert think["metrics"]["model_calls"] > fast["metrics"]["model_calls"]
    assert any(s["kind"] == "plan" for s in think["steps"]) and not any(s["kind"] == "plan" for s in fast["steps"])
    return (f"fast {fast['metrics']['model_calls']} calls / {fast['metrics']['completion_tokens']} tok, "
            f"think {think['metrics']['model_calls']} calls / {think['metrics']['completion_tokens']} tok")


@check("uploaded document is read and answered from")
def t_document():
    secret = "The maintenance password for reactor bay 7 is 'quokka-lantern-42'. The bay was commissioned in 2019."
    filler = "\n".join(f"Log entry {i}: routine inspection completed without findings." for i in range(40))
    files = {"file": ("bay7_notes.txt", (filler + "\n" + secret + "\n" + filler).encode(), "text/plain")}
    doc = client.post("/api/documents", files=files, data={"conversation_id": ""}).json()
    assert doc.get("n_chunks", 0) >= 1, doc
    r = chat("According to the attached notes, what is the maintenance password for reactor bay 7?",
             document_ids=[doc["id"]])
    assert "quokka-lantern-42" in r["final"]["content"], r["final"]["content"]
    assert any(s["kind"] == "documents" for s in r["final"]["steps"]), "no document step recorded"
    docs = client.get(f"/api/conversations/{r['conversation_id']}").json()["documents"]
    assert len(docs) == 1 and docs[0]["name"] == "bay7_notes.txt"
    return f"{doc['n_chunks']} chunks indexed; answer quoted the document"


@check("large document uses retrieval and cites passages")
def t_retrieval():
    paras = [f"Section {i}. " + ("General background text about logistics and scheduling. " * 30) for i in range(60)]
    paras[37] += " The Halvorsen bridge inspection found a 14 millimetre crack in girder G-22 on 3 March."
    files = {"file": ("survey.md", "\n\n".join(paras).encode(), "text/markdown")}
    doc = client.post("/api/documents", files=files, data={"conversation_id": ""}).json()
    r = chat("What did the Halvorsen bridge inspection find? Quote the size.", document_ids=[doc["id"]])
    m = r["final"]
    assert "14" in m["content"], m["content"]
    assert any(s["kind"] == "document" for s in m["sources"]), "no passage sources recorded"
    return f"{doc['n_chars']:,} chars indexed, {len(m['sources'])} passages supplied"


@check("unsupported upload is rejected with a clear message")
def t_bad_upload():
    resp = client.post("/api/documents", files={"file": ("x.exe", b"MZ\x00\x00", "application/octet-stream")},
                       data={"conversation_id": ""})
    assert resp.status_code == 422 and "not supported" in resp.json()["detail"], resp.text
    return resp.json()["detail"][:60]


@check("memory: explicit 'remember' saves, later chat uses it, user can delete")
def t_memory():
    before = {m["id"] for m in client.get("/api/memory").json()["memories"]}
    r = chat("Please remember for future chats that my dog's name is Zephyrine.")
    after = client.get("/api/memory").json()["memories"]
    new = [m for m in after if m["id"] not in before]
    assert new and "zephyrine" in new[0]["content"].lower(), f"not saved: {[m['content'] for m in after]} / {r['final']['content']}"
    r2 = chat("What is my dog's name? One word.")
    assert "zephyrine" in r2["final"]["content"].lower(), r2["final"]["content"]
    for m in new:
        client.delete(f"/api/memory/{m['id']}")
    left = {m["id"] for m in client.get("/api/memory").json()["memories"]}
    assert not (left - before), "memory was not deleted"
    return "saved via tool, recalled in a new conversation, deleted"


@check("offline mode: research refuses honestly, local chat still answers")
def t_offline():
    client.patch("/api/settings", json={"offline_mode": True})
    try:
        r = chat("What happened in the news today?", mode="research")
        m = r["final"]
        assert not m["sources"], "sources present in offline mode"
        assert "offline mode" in m["content"].lower(), m["content"]
        local = chat("What is 2 + 2? Number only.")
        assert "4" in local["final"]["content"]
        dl = client.post("/api/models/gpt-oss-20b-mxfp4/download")
        installed = any(x["id"] == "gpt-oss-20b-mxfp4" and x["installed"] for x in client.get("/api/models").json()["models"])
        assert installed or dl.status_code == 409, f"download allowed offline: {dl.status_code}"
    finally:
        client.patch("/api/settings", json={"offline_mode": False})
    return "research blocked with explanation; chat worked; download refused"


@check("export returns the conversation as Markdown and JSON")
def t_export():
    r = chat("Say hello in French. One word.")
    cid = r["conversation_id"]
    md = client.get(f"/api/conversations/{cid}/export?format=md")
    js = client.get(f"/api/conversations/{cid}/export?format=json")
    assert md.status_code == 200 and "## You" in md.text and "## Thrones" in md.text
    assert len(js.json()["messages"]) == 2
    everything = client.get("/api/export").json()
    assert "brave_api_key" not in everything["settings"] and everything["conversations"]
    return f"markdown {len(md.text)} chars; full export has {len(everything['conversations'])} conversations"


@check("hinglish and hindi are answered in the user's language")
def t_hindi():
    r1 = chat("Yaar, ek line me batao ki paani kyun ubalta hai?")
    r2 = chat("भारत की राजधानी क्या है? एक वाक्य में बताइए।")
    assert any(w in r1["final"]["content"].lower() for w in ("hai", "hota", "jab", "paani")), r1["final"]["content"]
    assert "दिल्ली" in r2["final"]["content"], r2["final"]["content"]
    return "Hinglish reply in Roman script; Hindi reply in Devanagari names Delhi"


@check("identity: names the real base model, does not claim to be something else")
def t_identity():
    r = chat("Which AI model are you exactly, and who made the model?")
    text = r["final"]["content"].lower()
    assert "thrones" in text and "qwen" in text, r["final"]["content"]
    assert "openai" not in text and "anthropic" not in text or "not" in text, r["final"]["content"]
    return "says Thrones running a Qwen model"


@check("deep research returns a cited report from real fetched pages")
def t_research():
    r = chat("What is the current stable version of Python and when was it released?", mode="research")
    m = r["final"]
    web = [s for s in m["sources"] if s["kind"] == "web"]
    assert web, f"no sources. content: {m['content'][:300]}"
    assert all(s["url"].startswith("http") for s in web)
    cited = [s for s in web if s.get("cited")]
    assert cited, "report cites no sources"
    import re
    nums = {int(n) for n in re.findall(r"\[(\d+)\]", m["content"])}
    assert nums and max(nums) <= len(web), f"citation out of range: {nums} vs {len(web)} sources"
    live = httpx.get(cited[0]["url"], timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    assert live.status_code < 500, f"cited URL not reachable: {live.status_code}"
    kinds = [s["kind"] for s in m["steps"]]
    assert {"plan", "search", "read", "notes", "write"} <= set(kinds), kinds
    return f"{len(web)} pages read, {len(cited)} cited, {m['metrics']['total_s']}s"


@check("model switch loads a different engine and it answers")
def t_switch():
    models = client.get("/api/models").json()["models"]
    current = client.get("/api/status").json()["resolved"]["model_id"]
    other = next((m for m in models if m["installed"] and m["id"] != current), None)
    assert other, "only one model installed"
    client.patch("/api/settings", json={"model_id": other["id"]})
    try:
        r = chat("Reply with exactly: ok")
        assert r["final"]["metrics"]["model_id"] == other["id"], r["final"]["metrics"]
        assert client.get("/api/status").json()["engine"]["model_id"] == other["id"]
        load = r["final"]["metrics"]["load_seconds"]
    finally:
        client.patch("/api/settings", json={"model_id": ""})
    return f"switched to {other['name']} (load {load}s) and back"


ALL = [t_status, t_fast, t_context, t_regenerate, t_stop, t_think, t_modes_differ, t_document, t_retrieval,
       t_bad_upload, t_memory, t_offline, t_export, t_hindi, t_identity, t_research, t_switch]
WEB = {"t_research"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true", help="keep the conversations these checks create")
    args = ap.parse_args()
    try:
        for fn in ALL:
            if args.only and args.only not in fn.__name__:
                continue
            if args.skip_web and fn.__name__ in WEB:
                print(f"SKIP  {fn.__name__} (needs internet)")
                continue
            fn()
    finally:
        if not args.keep:
            for cid in created:
                client.delete(f"/api/conversations/{cid}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed} of {len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

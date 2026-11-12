from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from .. import config, db

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
    ".log", ".xml", ".html", ".htm", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".ps1", ".bat", ".css", ".tex",
}
SUPPORTED = TEXT_EXTENSIONS | {".pdf", ".docx"}
MAX_FILE_BYTES = 30 * 2**20
CHUNK_CHARS = 1400
CHUNK_OVERLAP = 180


class DocumentError(Exception):
    pass


def _read_pdf(data: bytes) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DocumentError("This PDF is password-protected.")
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append((i, text))
    if not pages:
        raise DocumentError("No selectable text found in this PDF (scanned PDFs need OCR, which is not installed).")
    return pages


def _read_docx(data: bytes) -> list[tuple[int, str]]:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return [(0, "\n".join(parts))]


def read_pages(name: str, data: bytes) -> list[tuple[int, str]]:
    """Return [(page_number, text)]. page_number is 0 for formats without pages."""
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED:
        raise DocumentError(f"'{ext or name}' files are not supported. Supported: text, code, CSV, JSON, PDF, DOCX.")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError("File is larger than 30 MB.")
    if ext == ".pdf":
        return _read_pdf(data)
    if ext == ".docx":
        return _read_docx(data)
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return [(0, data.decode(encoding))]
        except UnicodeDecodeError:
            continue
    raise DocumentError("Could not decode this file as text.")


def chunk_pages(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    chunks: list[tuple[int, str]] = []
    for page, text in pages:
        text = re.sub(r"[ \t]+\n", "\n", text).strip()
        start = 0
        while start < len(text):
            end = min(len(text), start + CHUNK_CHARS)
            if end < len(text):
                # Prefer to break on a paragraph, then a sentence, then a space.
                window = text[start:end]
                cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
                if cut < CHUNK_CHARS * 0.5:
                    cut = window.rfind(" ")
                if cut > CHUNK_CHARS * 0.3:
                    end = start + cut + 1
            piece = text[start:end].strip()
            if piece:
                chunks.append((page, piece))
            if end >= len(text):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def ingest(name: str, data: bytes, conversation_id: str | None, mime: str = "") -> dict[str, Any]:
    pages = read_pages(name, data)
    chunks = chunk_pages(pages)
    if not chunks:
        raise DocumentError("The file contains no readable text.")
    doc_id = db.new_id()
    safe = re.sub(r"[^\w.\- ]", "_", Path(name).name)[:120] or "document"
    stored = config.UPLOADS_DIR / f"{doc_id}_{safe}"
    stored.write_bytes(data)
    n_chars = sum(len(c) for _, c in chunks)
    db.execute(
        "INSERT INTO documents(id, name, mime, size, n_chunks, n_chars, conversation_id, path, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (doc_id, Path(name).name, mime, len(data), len(chunks), n_chars, conversation_id, str(stored), db.now()),
    )
    for i, (page, text) in enumerate(chunks):
        db.execute("INSERT INTO chunks(text, doc_id, chunk_index, page) VALUES(?,?,?,?)", (text, doc_id, i, page))
    return get(doc_id)  # type: ignore[return-value]


def get(doc_id: str) -> dict[str, Any] | None:
    return db.one("SELECT id, name, mime, size, n_chunks, n_chars, conversation_id, created_at FROM documents WHERE id = ?",
                  (doc_id,))


def list_for(conversation_id: str | None = None) -> list[dict[str, Any]]:
    cols = "id, name, mime, size, n_chunks, n_chars, conversation_id, created_at"
    if conversation_id:
        return db.query(f"SELECT {cols} FROM documents WHERE conversation_id = ? ORDER BY created_at", (conversation_id,))
    return db.query(f"SELECT {cols} FROM documents ORDER BY created_at DESC")


def attach(doc_ids: list[str], conversation_id: str) -> None:
    for d in doc_ids:
        db.execute("UPDATE documents SET conversation_id = ? WHERE id = ?", (conversation_id, d))


def delete(doc_id: str) -> None:
    row = db.one("SELECT path FROM documents WHERE id = ?", (doc_id,))
    if row and row["path"]:
        p = Path(row["path"])
        if p.exists() and config.UPLOADS_DIR in p.parents:
            p.unlink()
    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def delete_for_conversation(conversation_id: str) -> None:
    for d in list_for(conversation_id):
        delete(d["id"])


_STOP = {
    "the", "a", "an", "of", "to", "in", "is", "are", "was", "were", "and", "or", "for", "on", "with", "what",
    "which", "who", "how", "why", "does", "do", "did", "this", "that", "it", "be", "as", "at", "by", "from",
    "me", "my", "about", "can", "you", "tell", "please", "kya", "hai", "ka", "ki", "ke", "ko", "me", "se",
}


def _fts_query(question: str) -> str:
    terms = [t for t in re.findall(r"\w+", question.lower()) if len(t) > 1 and t not in _STOP]
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append('"' + t.replace('"', "") + '"')
    return " OR ".join(out[:24])


def search(question: str, doc_ids: list[str], limit: int = 6) -> list[dict[str, Any]]:
    """BM25 search restricted to the given documents."""
    if not doc_ids:
        return []
    marks = ",".join("?" for _ in doc_ids)
    match = _fts_query(question)
    rows: list[dict[str, Any]] = []
    if match:
        try:
            rows = db.query(
                f"SELECT text, doc_id, chunk_index, page, bm25(chunks) AS score FROM chunks "
                f"WHERE chunks MATCH ? AND doc_id IN ({marks}) ORDER BY score LIMIT ?",
                (match, *doc_ids, limit),
            )
        except Exception:
            rows = []
    if not rows:
        # Nothing matched (or the query had no searchable terms): fall back to the opening passages.
        rows = db.query(
            f"SELECT text, doc_id, chunk_index, page, 0 AS score FROM chunks WHERE doc_id IN ({marks}) "
            f"ORDER BY doc_id, CAST(chunk_index AS INTEGER) LIMIT ?",
            (*doc_ids, limit),
        )
    names = {d["id"]: d["name"] for d in db.query(f"SELECT id, name FROM documents WHERE id IN ({marks})", doc_ids)}
    for r in rows:
        r["name"] = names.get(r["doc_id"], "document")
    return rows


def full_text(doc_id: str) -> list[dict[str, Any]]:
    return db.query(
        "SELECT text, page, chunk_index FROM chunks WHERE doc_id = ? ORDER BY CAST(chunk_index AS INTEGER)", (doc_id,)
    )


def build_context(question: str, conversation_id: str, char_budget: int) -> tuple[str, list[dict[str, Any]]]:
    """Return (context block, passages used) for the documents attached to a conversation.

    Small documents are included whole. Larger ones are searched and only the
    best-matching passages are included, each labelled with file and page.
    """
    docs = list_for(conversation_id)
    if not docs:
        return "", []
    total = sum(d["n_chars"] for d in docs)
    used: list[dict[str, Any]] = []
    blocks: list[str] = []
    if total <= char_budget:
        for d in docs:
            parts = []
            for row in full_text(d["id"]):
                parts.append(row["text"])
            # Overlapping chunk edges are acceptable here; the label tells the model which file it is.
            blocks.append(f'<document name="{d["name"]}">\n' + "\n".join(parts) + "\n</document>")
            used.append({"name": d["name"], "page": 0, "whole": True, "excerpt": ""})
    else:
        per = max(3, min(10, char_budget // CHUNK_CHARS))
        for row in search(question, [d["id"] for d in docs], limit=per):
            label = row["name"] + (f", p. {row['page']}" if row["page"] else f", part {int(row['chunk_index']) + 1}")
            blocks.append(f'<passage source="{label}">\n{row["text"]}\n</passage>')
            used.append({"name": row["name"], "page": row["page"], "whole": False, "excerpt": row["text"][:240],
                         "label": label})
    return "\n\n".join(blocks), used

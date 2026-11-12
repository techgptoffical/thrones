"""Turn fetched bytes into readable text plus honest metadata."""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .net import Fetched


@dataclass
class Page:
    url: str
    title: str
    text: str
    date: str = ""        # publication date as reported by the page; empty when unknown
    site: str = ""
    truncated: bool = False


def _site(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def _pdf_text(data: bytes, max_pages: int = 40) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    title = ""
    try:
        title = (reader.metadata.title or "") if reader.metadata else ""
    except Exception:
        title = ""
    pages = []
    for page in reader.pages[:max_pages]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return title, "\n\n".join(pages)


def extract(fetched: Fetched) -> Page | None:
    site = _site(fetched.url)
    if fetched.content_type == "application/pdf" or fetched.body[:5] == b"%PDF-":
        try:
            title, text = _pdf_text(fetched.body)
        except Exception:
            return None
        text = re.sub(r"[ \t]+", " ", text).strip()
        if len(text) < 200:
            return None
        return Page(fetched.url, title or fetched.url.rsplit("/", 1)[-1], text, "", site, fetched.truncated)

    import trafilatura

    try:
        html = fetched.body.decode("utf-8", errors="replace")
        raw = trafilatura.extract(
            html, url=fetched.url, output_format="json", with_metadata=True,
            include_comments=False, include_tables=True, favor_precision=True,
        )
    except Exception:
        raw = None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    text = (data.get("text") or "").strip()
    if len(text) < 200:
        return None
    return Page(
        url=fetched.url,
        title=(data.get("title") or site or fetched.url).strip(),
        text=text,
        date=(data.get("date") or "").strip(),
        site=(data.get("sitename") or site).strip(),
        truncated=fetched.truncated,
    )

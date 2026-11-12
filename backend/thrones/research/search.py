"""Pluggable web-search adapters.

  duckduckgo  no key, no account; uses the `ddgs` library. Unofficial, so it can
              be rate-limited — fine for personal use, not a guaranteed service.
  searxng     self-hosted metasearch; the user supplies their instance URL.
  brave       official paid/free-tier API; the user supplies their own key.

Adapters return plain result dicts and never invent results: an empty list
means the provider returned nothing.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet, "query": self.query}


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 8) -> list[SearchResult]: ...


def normalize_url(url: str) -> str:
    """Canonical form used for de-duplication."""
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    query = "&".join(
        kv for kv in p.query.split("&")
        if kv and not kv.lower().startswith(("utm_", "fbclid", "gclid", "ref=", "ref_src"))
    )
    return urlunsplit((p.scheme.lower() or "https", host, path, query, ""))


class DuckDuckGoSearch:
    name = "duckduckgo"

    async def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        def run() -> list[dict[str, Any]]:
            from ddgs import DDGS
            return list(DDGS(timeout=12).text(query, max_results=max_results))

        try:
            rows = await asyncio.to_thread(run)
        except Exception as exc:
            if "no results" in str(exc).lower():
                return []
            raise SearchError(f"DuckDuckGo search failed: {type(exc).__name__}: {exc}") from exc
        return [
            SearchResult(r.get("title", "").strip(), r.get("href", "").strip(), r.get("body", "").strip(), query)
            for r in rows if r.get("href", "").startswith("http")
        ]


class SearxngSearch:
    name = "searxng"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        if not self.base_url:
            raise SearchError("No SearXNG URL is configured (Settings > Research).")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}/search", params={"q": query, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchError(f"SearXNG search failed: {type(exc).__name__}") from exc
        return [
            SearchResult(r.get("title", ""), r.get("url", ""), r.get("content", ""), query)
            for r in data.get("results", [])[:max_results] if str(r.get("url", "")).startswith("http")
        ]


class BraveSearch:
    name = "brave"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    async def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise SearchError("No Brave Search API key is configured (Settings > Research).")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": min(max_results, 20)},
                    headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchError(f"Brave search failed: {type(exc).__name__}") from exc
        return [
            SearchResult(r.get("title", ""), r.get("url", ""), r.get("description", ""), query)
            for r in data.get("web", {}).get("results", [])[:max_results]
        ]


def get_provider(settings: dict[str, Any]) -> SearchProvider:
    name = settings.get("search_provider", "duckduckgo")
    if name == "searxng":
        return SearxngSearch(settings.get("searxng_url", ""))
    if name == "brave":
        return BraveSearch(settings.get("brave_api_key", ""))
    return DuckDuckGoSearch()

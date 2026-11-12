"""Deep Research: plan → search → fetch → extract evidence → gap check → cited report.

The pipeline is driven by code, not by the model. The model is asked narrow
questions (what to search, what a page says, what is missing, write the
report) and has no tools while it reads web content. Sources in the final
list are exactly the pages that were fetched and read during this run.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import time
from dataclasses import replace
from typing import Any

from ..reasoning import prompts
from ..reasoning.engine import Run, generate
from .extract import Page, extract
from .net import BlockedError, FetchError, Fetcher, internet_available
from .search import SearchError, SearchResult, get_provider, normalize_url

SOURCE_CHARS = 6500          # evidence window per source given to the model
LOW_VALUE_HOSTS = ("pinterest.", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com")


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _relevant_window(text: str, question: str, limit: int = SOURCE_CHARS) -> str:
    """Keep the opening of the page plus the paragraphs that best match the question."""
    if len(text) <= limit:
        return text
    terms = {t for t in re.findall(r"\w{4,}", question.lower())}
    paragraphs = [p.strip() for p in re.split(r"\n{1,}", text) if len(p.strip()) > 40]
    head, used = [], 0
    for p in paragraphs[:3]:
        head.append(p)
        used += len(p)
    scored = []
    for i, p in enumerate(paragraphs[3:], start=3):
        low = p.lower()
        score = sum(low.count(t) for t in terms) + (1 if re.search(r"\d", p) else 0) * 0.5
        scored.append((score, i, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = []
    for score, i, p in scored:
        if used + len(p) > limit:
            continue
        chosen.append((i, p))
        used += len(p)
        if used > limit * 0.92:
            break
    chosen.sort()
    return "\n".join(head + [p for _, p in chosen])[:limit]


def sanitize_report(text: str, n_sources: int, allowed_urls: set[str]) -> tuple[str, set[int]]:
    """Remove citations that do not map to a retrieved source, and links to pages that were never fetched."""
    cited: set[int] = set()

    def fix_citation(match: re.Match[str]) -> str:
        kept = []
        for num in re.findall(r"\d+", match.group(0)):
            n = int(num)
            if 1 <= n <= n_sources:
                cited.add(n)
                kept.append(f"[{n}]")
        return "".join(kept)

    text = re.sub(r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", fix_citation, text)

    def fix_link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        return match.group(0) if normalize_url(url) in allowed_urls else label

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", fix_link, text)

    def fix_bare(match: re.Match[str]) -> str:
        return match.group(0) if normalize_url(match.group(0).rstrip(".,)")) in allowed_urls else ""

    text = re.sub(r"(?<![\(\[])https?://[^\s)\]]+", fix_bare, text)
    return text, cited


async def deep_research(run: Run, question: str, system: str, history: list[dict[str, Any]]) -> None:
    s = run.settings
    today = dt.date.today().strftime("%d %B %Y")
    started = time.perf_counter()
    time_budget = int(s.get("research_time_budget_s") or 300)
    max_sources = max(2, min(15, int(s.get("research_max_sources") or 8)))
    max_rounds = max(1, min(3, int(s.get("research_max_rounds") or 2)))

    def time_left() -> float:
        return time_budget - (time.perf_counter() - started)

    # --- can we go online at all? -------------------------------------------
    if s.get("offline_mode") or not s.get("web_research_enabled", True):
        why = "Offline mode is on" if s.get("offline_mode") else "Web research is turned off"
        await run.step("offline", "Web research unavailable", f"{why} in Settings.", state="error")
        await run.replace_content(
            f"**Deep Research needs the internet, and {why.lower()} in Settings.**\n\n"
            "Nothing was searched and no sources were used. You can turn web research back on under "
            "Settings → Privacy, or switch to **Fast** or **Think** to get an answer from the local model alone "
            "(without current information or citations).")
        return
    step_id = await run.step("connect", "Checking the internet connection")
    if not await internet_available():
        await run.step_update(step_id, state="error", title="No internet connection",
                              detail="Could not reach the network.")
        await run.replace_content(
            "**No internet connection.** Deep Research could not search the web, so no sources were used.\n\n"
            "The local model still works offline: switch to **Fast** or **Think** for an answer based only on "
            "what the model learned in training (it may be out of date and comes without citations).")
        return
    await run.step_update(step_id, state="done", title="Internet connection available")

    precise = replace(run.base_params(False, precise=True), temperature=0.3)
    provider = get_provider(s)
    fetcher = Fetcher()
    sources: list[dict[str, Any]] = []         # pages actually read, in citation order
    seen_urls: set[str] = set()
    used_queries: list[str] = []
    aspects: list[str] = []

    async def publish() -> None:
        run.sources = sources
        await run.emit({"type": "sources", "sources": sources})

    try:
        # --- 1. plan ----------------------------------------------------------
        step_id = await run.step("plan", "Planning the research")
        context = ""
        if history:
            recent = " ".join(m["content"][:300] for m in history[-4:])
            context = f"\n\n(Earlier conversation, for context only: {recent[:900]})"
        raw, _, _ = await generate(
            run, [{"role": "user", "content": prompts.RESEARCH_PLAN_PROMPT.format(
                today=today, question=question + context, n=4)}],
            replace(precise, max_tokens=350, json_mode=True), visible=False)
        plan = _json_object(raw)
        queries = [str(q).strip() for q in plan.get("queries", []) if str(q).strip()][:5]
        aspects = [str(a).strip() for a in plan.get("aspects", []) if str(a).strip()][:4]
        if not queries:
            queries = [question[:120]]
        await run.step_update(step_id, state="done", detail="\n".join(f"• {q}" for q in queries))

        for round_no in range(1, max_rounds + 1):
            # --- 2. search ----------------------------------------------------
            step_id = await run.step("search", "Searching the web" if round_no == 1 else "Searching again to fill gaps")
            results: list[SearchResult] = []
            errors: list[str] = []
            for q in queries:
                used_queries.append(q)
                try:
                    results.extend(await provider.search(q, max_results=6))
                except SearchError as exc:
                    errors.append(str(exc))
                await asyncio.sleep(0.4)
            candidates: list[SearchResult] = []
            for r in results:
                key = normalize_url(r.url)
                if key in seen_urls or any(h in key for h in LOW_VALUE_HOSTS):
                    continue
                seen_urls.add(key)
                candidates.append(r)
            if not candidates:
                detail = "No new results." + (f" {errors[0]}" if errors else "")
                await run.step_update(step_id, state="error" if not sources else "done", detail=detail)
                if not sources and round_no == 1:
                    await run.replace_content(
                        "**The search returned no results**, so there is nothing to cite.\n\n"
                        + (f"Search provider message: `{errors[0]}`\n\n" if errors else "")
                        + "This can happen when the search provider rate-limits requests. Try again in a minute, "
                        "rephrase the question, or choose another provider in Settings → Research.")
                    return
                break
            await run.step_update(
                step_id, state="done",
                detail=f"{len(candidates)} new pages from {len(queries)} queries via {provider.name}"
                       + (f" ({len(errors)} query failed)" if errors else ""))

            # Interleave results across queries so one query cannot crowd out the others.
            by_query: dict[str, list[SearchResult]] = {}
            for c in candidates:
                by_query.setdefault(c.query, []).append(c)
            ordered: list[SearchResult] = []
            while any(by_query.values()):
                for q in list(by_query):
                    if by_query[q]:
                        ordered.append(by_query[q].pop(0))
            room = max_sources - len(sources)
            if room <= 0:
                break
            to_fetch = ordered[: room + 3]      # a few spares for pages that fail

            # --- 3. fetch and extract ------------------------------------------
            step_id = await run.step("read", "Reading sources")
            failures: list[str] = []

            async def fetch_one(result: SearchResult) -> tuple[SearchResult, Page | None, str]:
                try:
                    fetched = await fetcher.get(result.url)
                except BlockedError as exc:
                    return result, None, f"blocked ({exc})"
                except FetchError as exc:
                    return result, None, str(exc)
                page = await asyncio.to_thread(extract, fetched)
                return result, page, "" if page else "no readable text"

            fetched_pages = await asyncio.gather(*(fetch_one(r) for r in to_fetch))
            pages: list[tuple[SearchResult, Page]] = []
            for result, page, problem in fetched_pages:
                if page is None:
                    failures.append(f"{result.url} — {problem}")
                elif len(pages) < room:
                    pages.append((result, page))
            await run.step_update(
                step_id, state="done" if pages else "error",
                detail=f"{len(pages)} pages read" + (f", {len(failures)} could not be read" if failures else "")
                       + ("\n" + "\n".join(f"✕ {f}" for f in failures[:6]) if failures else ""))

            # --- 4. evidence ---------------------------------------------------
            if pages:
                step_id = await run.step("notes", "Extracting evidence")
                kept = 0
                for i, (result, page) in enumerate(pages, start=1):
                    if time_left() < 45:
                        break
                    await run.step_update(step_id, detail=f"{i} of {len(pages)}: {page.site or page.url}")
                    date = f", published {page.date}" if page.date else ", date not stated"
                    notes, _, _ = await generate(
                        run, [{"role": "user", "content": prompts.RESEARCH_NOTES_PROMPT.format(
                            question=question, title=page.title[:160], site=page.site, date=date,
                            text=_relevant_window(page.text, question))}],
                        replace(precise, max_tokens=420), visible=False)
                    notes = notes.strip()
                    if not notes or notes.upper().startswith("IRRELEVANT") or "- " not in notes:
                        continue
                    kept += 1
                    sources.append({
                        "n": len(sources) + 1, "kind": "web", "title": page.title[:200], "url": page.url,
                        "site": page.site, "date": page.date, "snippet": (result.snippet or page.text[:240])[:300],
                        "notes": notes[:1800], "query": result.query, "cited": False,
                    })
                    await publish()
                await run.step_update(step_id, state="done",
                                      detail=f"{kept} of {len(pages)} pages contained relevant evidence")

            # --- 5. gap check --------------------------------------------------
            if round_no >= max_rounds or len(sources) >= max_sources or time_left() < 90:
                break
            step_id = await run.step("gaps", "Checking for gaps and conflicts")
            digest = "\n\n".join(f"[{src['n']}] {src['site']}:\n{src['notes'][:700]}" for src in sources) or "(none)"
            raw, _, _ = await generate(
                run, [{"role": "user", "content": prompts.RESEARCH_GAP_PROMPT.format(
                    question=question, aspects="; ".join(aspects) or "the question as asked",
                    notes=digest[:9000], used="; ".join(used_queries))}],
                replace(precise, max_tokens=300, json_mode=True), visible=False)
            gap = _json_object(raw)
            follow = [str(q).strip() for q in gap.get("queries", []) if str(q).strip()
                      and str(q).strip().lower() not in {u.lower() for u in used_queries}][:3]
            if gap.get("sufficient", True) and sources or not follow:
                await run.step_update(step_id, state="done", detail="Evidence covers the question.")
                break
            await run.step_update(step_id, state="done",
                                  detail=(str(gap.get("missing", "")).strip()[:300] or "More evidence needed.")
                                         + "\n" + "\n".join(f"• {q}" for q in follow))
            queries = follow
    finally:
        await fetcher.close()

    if not sources:
        await run.replace_content(
            "**No usable sources could be read**, so there is no evidence to build a report on.\n\n"
            "The search worked, but the pages either blocked automated reading, timed out, or did not contain "
            "relevant text. Try rephrasing the question, or raise the source limit in Settings → Research.")
        return

    # --- 6. write the report ------------------------------------------------------
    step_id = await run.step("write", "Writing the report")
    notes_block = "\n\n".join(
        f"[{src['n']}] {src['title']} — {src['site']}"
        + (f" — published {src['date']}" if src["date"] else " — date not stated")
        + f"\n{src['notes']}" for src in sources)
    write_params = replace(run.base_params(True, precise=True), max_tokens=max(2500, int(s.get("max_tokens") or 4096)))
    await generate(
        run,
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.RESEARCH_WRITE_PROMPT.format(today=today, question=question,
                                                                         notes=notes_block[:24000])}],
        write_params, visible=True)

    clean, cited = sanitize_report(run.content, len(sources), {normalize_url(src["url"]) for src in sources})
    for src in sources:
        src["cited"] = src["n"] in cited
    if clean != run.content:
        await run.replace_content(clean)
    await publish()
    await run.step_update(step_id, state="done",
                          detail=f"{len(cited)} of {len(sources)} sources cited · {len(used_queries)} searches")

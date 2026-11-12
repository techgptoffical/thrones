"""Safe outbound HTTP for research.

Guards:
  * http/https only, default ports only
  * every hostname (including each redirect hop) must resolve exclusively to
    public addresses — loopback, private, link-local, CGNAT, multicast and
    reserved ranges are refused, which blocks requests to local services
  * response size and time are capped
  * robots.txt is honoured and requests are spaced per host
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "ThronesResearch/1.0 (local research assistant; respects robots.txt)"
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
PER_HOST_INTERVAL_S = 1.0
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf", "application/xml", "text/xml")


class FetchError(Exception):
    pass


class BlockedError(FetchError):
    pass


@dataclass
class Fetched:
    url: str            # final URL after redirects
    status: int
    content_type: str
    body: bytes
    truncated: bool = False


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
            or addr.is_reserved or addr.is_unspecified):
        return False
    if isinstance(addr, ipaddress.IPv4Address):
        return addr not in _CGNAT
    return not addr.is_site_local


async def check_url(url: str) -> None:
    """Raise BlockedError unless the URL is a public http(s) address."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedError(f"scheme '{parts.scheme}' is not allowed")
    host = parts.hostname
    if not host:
        raise BlockedError("URL has no host")
    if parts.username or parts.password:
        raise BlockedError("URLs with credentials are not allowed")
    if parts.port not in (None, 80, 443):
        raise BlockedError(f"port {parts.port} is not allowed")
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal", ".localhost", ".lan")):
        raise BlockedError("local hostnames are not allowed")
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"could not resolve {host}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public(a) for a in addresses):
        raise BlockedError(f"{host} resolves to a non-public address")


class Fetcher:
    def __init__(self, timeout_s: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=8.0),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
                     "Accept-Language": "en,hi;q=0.8"},
            limits=httpx.Limits(max_connections=8),
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _throttle(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last_hit.get(host, 0.0) + PER_HOST_INTERVAL_S - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()

    async def _allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = None
            try:
                await check_url(origin + "/robots.txt")
                resp = await self._client.get(origin + "/robots.txt", timeout=6.0)
                if resp.status_code == 200 and len(resp.content) < 500_000:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(resp.text.splitlines())
            except (httpx.HTTPError, FetchError):
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    async def get(self, url: str) -> Fetched:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(current)
            if not await self._allowed_by_robots(current):
                raise BlockedError("disallowed by the site's robots.txt")
            await self._throttle(urlsplit(current).hostname or "")
            try:
                async with self._client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError("redirect without a location")
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"HTTP {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and not ctype.startswith(ALLOWED_TYPES):
                        raise FetchError(f"unsupported content type {ctype}")
                    chunks: list[bytes] = []
                    size, truncated = 0, False
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= MAX_BYTES:
                            truncated = True
                            break
                    return Fetched(str(resp.url), resp.status_code, ctype, b"".join(chunks), truncated)
            except httpx.TimeoutException as exc:
                raise FetchError("timed out") from exc
            except httpx.HTTPError as exc:
                raise FetchError(type(exc).__name__) from exc
        raise FetchError("too many redirects")


async def internet_available(timeout_s: float = 4.0) -> bool:
    """Cheap reachability probe used to tell the user when research cannot run."""
    loop = asyncio.get_running_loop()

    def probe() -> bool:
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                with socket.create_connection((host, 443), timeout=timeout_s):
                    return True
            except OSError:
                continue
        return False

    return await loop.run_in_executor(None, probe)

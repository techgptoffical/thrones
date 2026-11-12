import asyncio

import pytest

from thrones.research.net import BlockedError, _is_public, check_url
from thrones.research.pipeline import _json_object, _relevant_window, sanitize_report
from thrones.research.search import normalize_url


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True),
    ("1.1.1.1", True),
    ("127.0.0.1", False),
    ("10.0.0.5", False),
    ("192.168.1.1", False),
    ("172.16.3.4", False),
    ("169.254.169.254", False),   # cloud metadata endpoint
    ("100.64.0.1", False),        # CGNAT
    ("0.0.0.0", False),
    ("::1", False),
    ("fe80::1", False),
    ("fc00::1", False),
    ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
    ("2606:4700:4700::1111", True),
])
def test_public_address_classification(ip, public):
    assert _is_public(ip) is public


@pytest.mark.parametrize("url", [
    "file:///C:/Windows/win.ini",
    "ftp://example.com/x",
    "http://localhost:8765/api/status",
    "http://127.0.0.1:8766/health",
    "http://192.168.0.1/",
    "http://printer.local/",
    "http://user:pass@example.com/",
    "http://example.com:8080/",
])
def test_check_url_blocks_local_and_odd_targets(url):
    with pytest.raises(BlockedError):
        asyncio.run(check_url(url))


def test_normalize_url_dedupes_tracking_variants():
    a = normalize_url("https://www.Example.com/page/?utm_source=x&id=3#top")
    b = normalize_url("https://example.com/page?id=3")
    assert a == b


def test_sanitize_report_drops_invented_citations_and_links():
    text = ("Fact one [1]. Fact two [7]. Both [1, 2]. See [the docs](https://made-up.example/x) "
            "and [real](https://real.example/a). Bare https://invented.example/y here.")
    clean, cited = sanitize_report(text, n_sources=2, allowed_urls={normalize_url("https://real.example/a")})
    assert "[7]" not in clean
    assert "[1][2]" in clean
    assert "made-up.example" not in clean and "the docs" in clean
    assert "https://real.example/a" in clean
    assert "invented.example" not in clean
    assert cited == {1, 2}


def test_json_object_extraction_tolerates_wrapping():
    assert _json_object('Sure! {"queries": ["a"], "aspects": []} done') == {"queries": ["a"], "aspects": []}
    assert _json_object("no json here") == {}
    assert _json_object("[1, 2]") == {}


def test_relevant_window_keeps_matching_paragraphs():
    paras = [f"Intro paragraph {i} with enough words to count as real text here." for i in range(3)]
    paras += [f"Unrelated filler paragraph number {i} about gardening and weather." for i in range(400)]
    paras.insert(250, "The quokka population census reported 12,400 animals on Rottnest Island in 2024.")
    window = _relevant_window("\n".join(paras), "What was the quokka census count on Rottnest?", limit=2000)
    assert len(window) <= 2000
    assert "12,400" in window
    assert window.startswith("Intro paragraph 0")

"""Fetch original article content for each article.

Primary: Jina Reader API (clean markdown extraction, free tier 20 req/min).
Fallback: BeautifulSoup HTML parsing.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from src import config, http_client
from src.models import Article

logger = logging.getLogger(__name__)

_EXTRACT_TIMEOUT = 10
_JINA_TIMEOUT = 15

_SKIP_DOMAINS = ("i.redd.it", "v.redd.it", "imgur.com", "reddit.com/gallery")

# Domains where Jina Reader tends to burn the budget on nav/ads before hitting
# the body. For these, prefer direct BS4 on <article> first and fall back to Jina.
_BS4_FIRST_DOMAINS = (
    "techcrunch.com",
    "theverge.com",
    "venturebeat.com",
    "technologyreview.com",
    "marktechpost.com",
)

# Regex patterns for Jina markdown cleanup
_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_EMPTY_LINK = re.compile(r"\[\s*\]\([^)]+\)")  # [](url) — share buttons
_LINK_TEXT = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MULTI_BLANK = re.compile(r"\n{3,}")
_JINA_HEADER_SPLIT = re.compile(r"(^|\n)Markdown Content:\s*\n?")


def _clean_jina_markdown(text: str) -> str:
    """Strip nav/share/image noise from Jina Reader output, preserve metadata header."""
    # Split into metadata header + body
    parts = _JINA_HEADER_SPLIT.split(text, maxsplit=1)
    if len(parts) >= 3:
        header = parts[0].rstrip() + "\n\nMarkdown Content:\n"
        body = parts[-1]
    else:
        header, body = "", text

    # Body cleanup
    body = _IMG_MD.sub("", body)
    body = _EMPTY_LINK.sub("", body)  # share buttons with empty text

    kept = []
    for raw_line in body.splitlines():
        ln = raw_line.rstrip()
        stripped = ln.strip()
        if not stripped:
            kept.append("")
            continue
        # Drop list-item nav: "*   [Foo](url)" where the rendered text is short
        if re.match(r"^[\*\-\+]\s+\[[^\]]{1,40}\]\([^)]+\)\s*$", stripped):
            continue
        # Drop lines that are purely a single short link
        if re.match(r"^\[[^\]]{1,40}\]\([^)]+\)\s*$", stripped):
            continue
        # Drop bare URLs
        if re.match(r"^https?://\S+$", stripped):
            continue
        kept.append(ln)

    cleaned = "\n".join(kept)
    cleaned = _MULTI_BLANK.sub("\n\n", cleaned).strip()
    return (header + cleaned).strip()


def extract_body_summary(content: str, max_chars: int | None = None) -> str:
    """Extract a prose-based summary from already-fetched article content.

    Picks sentence-like lines from the body and joins them until ~max_chars.
    Returns an empty string when no usable prose is found (e.g., nav-only pages).
    """
    if not content:
        return ""
    limit = max_chars or config.BODY_SUMMARY_MAX_CHARS

    parts = _JINA_HEADER_SPLIT.split(content, maxsplit=1)
    body = parts[-1] if len(parts) >= 3 else content

    # Strip markdown decoration so we can evaluate prose density
    body = _IMG_MD.sub("", body)
    body = _EMPTY_LINK.sub("", body)
    body = _LINK_TEXT.sub(r"\1", body)
    body = re.sub(r"^#+\s*", "", body, flags=re.MULTILINE)
    body = re.sub(r"https?://\S+", "", body)

    good: list[str] = []
    for raw in body.splitlines():
        s = raw.strip()
        if len(s) < 80:
            continue
        if not any(p in s for p in ".!?"):
            continue
        if s.count("|") > 3:  # markdown table row
            continue
        # Emphasis markers can stay; keep the sentence as-is
        good.append(s)

    if not good:
        return ""

    out: list[str] = []
    total = 0
    for s in good:
        out.append(s)
        total += len(s) + 1
        if total >= limit:
            break
    joined = " ".join(out)
    if len(joined) > limit:
        return joined[:limit].rstrip() + "…"
    return joined


def _extract_with_jina(url: str) -> str:
    """Fetch a URL via Jina Reader API and return clean markdown text."""
    jina_url = f"{config.JINA_READER_URL}{url}"
    headers = {
        "Accept": "text/plain",
        "X-No-Cache": "true",
    }
    try:
        resp = http_client.get(jina_url, headers=headers, timeout=_JINA_TIMEOUT)
        resp.raise_for_status()
        text = resp.text.strip()
        if text:
            cleaned = _clean_jina_markdown(text)
            return cleaned[:config.MAX_CONTENT_LENGTH]
    except Exception as e:
        logger.debug("Jina Reader failed for %s: %s", url[:60], e)
    return ""


def _extract_with_bs4(url: str) -> str:
    """Fetch a URL and extract the main text content with BeautifulSoup (fallback)."""
    try:
        headers = {**config.HTTP_HEADERS, "Accept": "text/html"}
        resp = http_client.get(url, headers=headers, timeout=_EXTRACT_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise
    for tag in soup.select("script, style, nav, footer, header, aside, .sidebar, .ad, .comments"):
        tag.decompose()

    # Try <article> first, then <main>, then body
    main = soup.select_one("article") or soup.select_one("main") or soup.body
    if not main:
        return ""

    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:config.MAX_CONTENT_LENGTH]


def _is_bs4_first_domain(url: str) -> bool:
    lower = url.lower()
    return any(d in lower for d in _BS4_FIRST_DOMAINS)


def _looks_substantive(text: str, min_chars: int = 600) -> bool:
    """Rough heuristic: does the text have enough prose to be the article body?"""
    if not text or len(text) < min_chars:
        return False
    # Require at least a few sentence-like lines
    prose_lines = sum(
        1 for ln in text.splitlines()
        if 80 <= len(ln.strip()) <= 2000 and any(p in ln for p in ".!?")
    )
    return prose_lines >= 2


def _extract_text(url: str) -> str:
    """Pick extraction strategy by domain, fall back to the other."""
    if _is_bs4_first_domain(url):
        primary, fallback = _extract_with_bs4, _extract_with_jina
        primary_name, fallback_name = "BS4", "Jina"
    else:
        primary, fallback = _extract_with_jina, _extract_with_bs4
        primary_name, fallback_name = "Jina", "BS4"

    text = primary(url)
    if _looks_substantive(text):
        return text
    logger.debug("%s thin for %s — falling back to %s", primary_name, url[:60], fallback_name)
    alt = fallback(url)
    # Keep whichever is longer if both look substantive, otherwise prefer the
    # one that crossed the threshold.
    if _looks_substantive(alt) and (not text or len(alt) > len(text)):
        return alt
    return text or alt


class _RateLimiter:
    """Sliding-window rate limiter — at most *max_calls* in *per_seconds* seconds."""

    def __init__(self, max_calls: int, per_seconds: float) -> None:
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < self.per_seconds]
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                wait = self.per_seconds - (now - self._calls[0]) + 0.05
            time.sleep(max(wait, 0.05))


def _fetch_one(article: Article, limiter: _RateLimiter) -> str:
    """Skip unfetchable URLs, otherwise extract text honoring the Jina rate limit."""
    if any(d in article.url for d in _SKIP_DOMAINS):
        return ""
    if article.source_name == "GitHub Trending":
        return ""
    limiter.acquire()
    text = _extract_text(article.url)
    if text:
        logger.debug("Fetched %d chars from %s", len(text), article.url[:60])
    return text


def fetch_content(articles: list[Article], *, max_workers: int = 4) -> list[str]:
    """Fetch original text content for each article in parallel.

    Returns a list of content strings (same order as input).
    Empty string for articles that can't or shouldn't be fetched.
    Respects Jina Reader free tier rate limit (20 req/min) via a shared limiter.
    """
    logger.info(
        "Fetching article content for %d articles (workers=%d)...",
        len(articles), max_workers,
    )
    # 20/min is the free-tier cap; leave a small margin.
    limiter = _RateLimiter(max_calls=18, per_seconds=60.0)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        contents = list(pool.map(lambda a: _fetch_one(a, limiter), articles))

    fetched = sum(1 for c in contents if c)
    logger.info("Fetched content for %d/%d articles", fetched, len(articles))
    return contents

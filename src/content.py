"""Fetch original article content for each article.

Primary: Jina Reader API (clean markdown extraction, free tier 20 req/min).
Fallback: BeautifulSoup HTML parsing.
"""

from __future__ import annotations

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_EXTRACT_TIMEOUT = 10
_JINA_TIMEOUT = 15

_SKIP_DOMAINS = ("i.redd.it", "v.redd.it", "imgur.com", "reddit.com/gallery")


def _extract_with_jina(url: str) -> str:
    """Fetch a URL via Jina Reader API and return clean markdown text."""
    jina_url = f"{config.JINA_READER_URL}{url}"
    headers = {
        "Accept": "text/plain",
        "X-No-Cache": "true",
    }
    try:
        resp = requests.get(jina_url, headers=headers, timeout=_JINA_TIMEOUT)
        resp.raise_for_status()
        text = resp.text.strip()
        if text:
            return text[:config.MAX_CONTENT_LENGTH]
    except Exception as e:
        logger.debug("Jina Reader failed for %s: %s", url[:60], e)
    return ""


def _extract_with_bs4(url: str) -> str:
    """Fetch a URL and extract the main text content with BeautifulSoup (fallback)."""
    try:
        headers = {**config.HTTP_HEADERS, "Accept": "text/html"}
        resp = requests.get(url, headers=headers, timeout=_EXTRACT_TIMEOUT)
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


def _extract_text(url: str) -> str:
    """Try Jina Reader first, fall back to BeautifulSoup."""
    text = _extract_with_jina(url)
    if text:
        return text
    logger.debug("Falling back to BS4 for %s", url[:60])
    return _extract_with_bs4(url)


def fetch_content(articles: list[Article]) -> list[str]:
    """Fetch original text content for each article.

    Returns a list of content strings (same order as input).
    Empty string for articles that can't or shouldn't be fetched.
    Respects Jina Reader free tier rate limit (20 req/min).
    """
    logger.info("Fetching article content for %d articles...", len(articles))
    contents: list[str] = []

    for i, a in enumerate(articles):
        if any(d in a.url for d in _SKIP_DOMAINS):
            contents.append("")
        elif a.source_name == "GitHub Trending":
            contents.append("")  # Already has summary from description
        else:
            text = _extract_text(a.url)
            contents.append(text)
            if text:
                logger.debug("Fetched %d chars from %s", len(text), a.url[:60])
            # Rate limit: wait between Jina requests
            time.sleep(config.JINA_RATE_LIMIT_DELAY)

    fetched = sum(1 for c in contents if c)
    logger.info("Fetched content for %d/%d articles", fetched, len(articles))
    return contents

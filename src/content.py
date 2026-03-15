"""Fetch original article content for each article."""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_EXTRACT_TIMEOUT = 10
_MAX_CONTENT_CHARS = 3000

_SKIP_DOMAINS = ("i.redd.it", "v.redd.it", "imgur.com", "reddit.com/gallery")


def _extract_text(url: str) -> str:
    """Fetch a URL and extract the main text content."""
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
    return text[:_MAX_CONTENT_CHARS]


def fetch_content(articles: list[Article]) -> list[str]:
    """Fetch original text content for each article.

    Returns a list of content strings (same order as input).
    Empty string for articles that can't or shouldn't be fetched.
    """
    logger.info("Fetching article content for %d articles...", len(articles))
    contents: list[str] = []

    for a in articles:
        if any(d in a.url for d in _SKIP_DOMAINS):
            contents.append("")
        elif a.source_name == "GitHub Trending":
            contents.append("")  # Already has summary from description
        else:
            text = _extract_text(a.url)
            contents.append(text)
            if text:
                logger.debug("Fetched %d chars from %s", len(text), a.url[:60])

    fetched = sum(1 for c in contents if c)
    logger.info("Fetched content for %d/%d articles", fetched, len(articles))
    return contents

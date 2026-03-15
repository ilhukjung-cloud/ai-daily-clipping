"""Hacker News crawler using the Firebase REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
_HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"


def _is_ai_related(title: str) -> bool:
    """Return True if the title contains any AI-related keyword."""
    lower = title.lower()
    return any(kw in lower for kw in config.HN_AI_KEYWORDS)


def _fetch_item(item_id: int) -> Article | None:
    try:
        resp = requests.get(
            _HN_ITEM.format(id=item_id),
            headers=config.HTTP_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        item = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch HN item %d: %s", item_id, exc)
        return None

    if not item or item.get("type") not in ("story", "job"):
        return None

    title = item.get("title", "")
    if not title or not _is_ai_related(title):
        return None

    url = item.get("url") or _HN_ITEM_URL.format(id=item_id)
    score = item.get("score")
    num_comments = item.get("descendants")
    created_utc = item.get("time", 0)
    published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

    return Article(
        title=title,
        url=url,
        source_type="community",
        source_name="Hacker News",
        published_at=published_at,
        score=int(score) if score is not None else None,
        comments=int(num_comments) if num_comments is not None else None,
    )


def crawl() -> list[Article]:
    """Crawl top Hacker News stories and filter for AI-related content.

    Fetches the top ``HN_TOP_STORIES_LIMIT`` story IDs then retrieves each
    item individually, keeping only those whose title matches an AI keyword.
    """
    try:
        resp = requests.get(
            _HN_TOP_STORIES,
            headers=config.HTTP_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        story_ids: list[int] = resp.json()
    except Exception as exc:
        logger.error("Failed to fetch HN top stories list: %s", exc)
        return []

    top_ids = story_ids[: config.HN_TOP_STORIES_LIMIT]
    articles: list[Article] = []

    for item_id in top_ids:
        article = _fetch_item(item_id)
        if article is not None:
            articles.append(article)

    logger.info("Hacker News: fetched %d AI-related articles", len(articles))
    return articles

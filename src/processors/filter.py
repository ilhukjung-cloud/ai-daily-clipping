"""Filters: time window, AI relevance, minimum score, and per-type limits."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src import config
from src.models import Article

logger = logging.getLogger(__name__)


def filter_recent(articles: list[Article], hours: int = 24) -> list[Article]:
    """Return articles published within the last *hours* hours.

    Articles published more than 1 hour in the future are treated as
    having a bad timestamp and are silently dropped.
    """
    if not articles:
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    future_cutoff = now + timedelta(hours=1)

    kept: list[Article] = []
    skipped_old = 0
    skipped_future = 0

    for article in articles:
        pub = article.published_at

        # Normalise naive datetimes to UTC
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        if pub > future_cutoff:
            logger.debug("Skipping future-dated article: %s (%s)", article.title, pub)
            skipped_future += 1
            continue

        if pub < cutoff:
            logger.debug("Skipping old article: %s (%s)", article.title, pub)
            skipped_old += 1
            continue

        kept.append(article)

    logger.info(
        "filter_recent(hours=%d): %d kept, %d too old, %d future-dated (input=%d)",
        hours,
        len(kept),
        skipped_old,
        skipped_future,
        len(articles),
    )
    return kept


def _is_ai_relevant(title: str) -> bool:
    """Check if a title contains at least one AI-related keyword."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in config.AI_RELEVANCE_KEYWORDS)


def filter_relevance(articles: list[Article]) -> list[Article]:
    """Drop community/HN articles whose title has no AI relevance.

    Official, media, and research articles are always kept.
    """
    kept: list[Article] = []
    dropped = 0
    for a in articles:
        if a.source_type in ("official", "media", "research"):
            kept.append(a)
        elif _is_ai_relevant(a.title):
            kept.append(a)
        else:
            logger.debug("Dropping irrelevant: %s", a.title)
            dropped += 1
    logger.info("filter_relevance: kept %d, dropped %d irrelevant", len(kept), dropped)
    return kept


def filter_min_score(articles: list[Article]) -> list[Article]:
    """Drop articles below the minimum score threshold for their source_type."""
    kept: list[Article] = []
    dropped = 0
    for a in articles:
        threshold = config.MIN_SCORE.get(a.source_type)
        if threshold is not None and a.score is not None and a.score < threshold:
            logger.debug("Dropping low-score (%d): %s", a.score, a.title)
            dropped += 1
        else:
            kept.append(a)
    logger.info("filter_min_score: kept %d, dropped %d low-score", len(kept), dropped)
    return kept


def limit_per_type(articles: list[Article]) -> list[Article]:
    """Keep only the top N articles per source_type, sorted by score."""
    from collections import defaultdict

    by_type: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_type[a.source_type].append(a)

    kept: list[Article] = []
    for st, items in by_type.items():
        limit = config.MAX_ARTICLES_PER_TYPE.get(st, 20)
        # Sort by score descending (None last)
        items.sort(key=lambda x: (x.score if x.score is not None else -1), reverse=True)
        kept.extend(items[:limit])
        if len(items) > limit:
            logger.info("limit_per_type: %s trimmed from %d to %d", st, len(items), limit)

    return kept

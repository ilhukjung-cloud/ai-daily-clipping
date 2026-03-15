"""Deduplication: remove exact URL duplicates and near-duplicate titles."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from src.config import DEDUP_SIMILARITY_THRESHOLD, SOURCE_TYPE_PRIORITY
from src.models import Article

logger = logging.getLogger(__name__)

_DEFAULT_PRIORITY = max(SOURCE_TYPE_PRIORITY.values()) + 1


def _priority(article: Article) -> int:
    """Lower number = higher priority."""
    return SOURCE_TYPE_PRIORITY.get(article.source_type, _DEFAULT_PRIORITY)


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def deduplicate(articles: list[Article]) -> list[Article]:
    """Remove duplicate articles, favouring higher-priority sources.

    Pass 1 – exact URL dedup: among articles sharing the same URL, keep the
    one with the highest source-type priority (lowest priority number).

    Pass 2 – fuzzy title dedup: among the remaining articles, if two titles
    are at least DEDUP_SIMILARITY_THRESHOLD similar, drop the lower-priority
    one.  Ties in priority are broken by keeping whichever was seen first.
    """
    if not articles:
        return []

    # --- Pass 1: exact URL dedup ---
    url_map: dict[str, Article] = {}
    for article in articles:
        url = article.url
        if url not in url_map:
            url_map[url] = article
        else:
            existing = url_map[url]
            if _priority(article) < _priority(existing):
                url_map[url] = article

    after_url_dedup = list(url_map.values())
    removed_url = len(articles) - len(after_url_dedup)
    logger.info("dedup pass 1 (URL): removed %d duplicates", removed_url)

    # --- Pass 2: fuzzy title dedup ---
    # Greedy O(n^2); fine for the expected article volumes (~hundreds/day).
    kept: list[Article] = []
    for candidate in after_url_dedup:
        merged = False
        for i, existing in enumerate(kept):
            sim = _title_similarity(candidate.title, existing.title)
            if sim >= DEDUP_SIMILARITY_THRESHOLD:
                # Keep the higher-priority article
                if _priority(candidate) < _priority(existing):
                    kept[i] = candidate
                    logger.debug(
                        "dedup pass 2: replaced '%s' with higher-priority '%s' (sim=%.2f)",
                        existing.title,
                        candidate.title,
                        sim,
                    )
                else:
                    logger.debug(
                        "dedup pass 2: dropped '%s' as duplicate of '%s' (sim=%.2f)",
                        candidate.title,
                        existing.title,
                        sim,
                    )
                merged = True
                break
        if not merged:
            kept.append(candidate)

    removed_title = len(after_url_dedup) - len(kept)
    logger.info(
        "dedup pass 2 (title): removed %d near-duplicates; final count=%d",
        removed_title,
        len(kept),
    )
    return kept

"""RSS feed crawler using feedparser."""

from __future__ import annotations

import html
import logging
import re
from calendar import timegm
from datetime import datetime, timezone

import feedparser

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape HTML entities from a string."""
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """Convert a feedparser entry's published_parsed (UTC struct_time) to datetime."""
    struct = getattr(entry, "published_parsed", None)
    if struct is None:
        struct = getattr(entry, "updated_parsed", None)
    if struct is None:
        return None
    try:
        # timegm treats the struct_time as UTC and returns a POSIX timestamp
        timestamp = timegm(struct)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        logger.debug("Could not convert published_parsed to datetime: %s", exc)
        return None


def _crawl_feed(url: str, source_name: str, source_type: str) -> list[Article]:
    """Parse a single RSS/Atom feed and return a list of Articles."""
    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        logger.error("feedparser failed for %s (%s): %s", source_name, url, exc)
        return []

    if feed.bozo and feed.bozo_exception:
        # bozo flag means the feed is not well-formed; log but continue anyway
        logger.warning(
            "Malformed feed from %s (%s): %s",
            source_name,
            url,
            feed.bozo_exception,
        )

    articles: list[Article] = []

    for entry in feed.entries:
        try:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                logger.debug("Skipping RSS entry with missing title or link from %s", source_name)
                continue

            published_at = _parse_published(entry)
            if published_at is None:
                logger.debug(
                    "No published date for entry '%s' from %s; using current time",
                    title,
                    source_name,
                )
                published_at = datetime.now(timezone.utc)

            # Prefer summary, fall back to content, then None
            raw_summary: str | None = None
            if hasattr(entry, "summary") and entry.summary:
                raw_summary = entry.summary
            elif hasattr(entry, "content") and entry.content:
                raw_summary = entry.content[0].get("value", "")

            summary = _strip_html(raw_summary) if raw_summary else None
            # Truncate very long summaries
            if summary and len(summary) > 1000:
                summary = summary[:997] + "..."

            articles.append(
                Article(
                    title=title,
                    url=link,
                    source_type=source_type,
                    source_name=source_name,
                    published_at=published_at,
                    summary=summary,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error processing RSS entry from %s: %s", source_name, exc)
            continue

    logger.info("RSS %s: fetched %d articles", source_name, len(articles))
    return articles


def crawl() -> list[Article]:
    """Crawl all RSS feeds defined in config.RSS_FEEDS and return Articles."""
    articles: list[Article] = []

    for url, source_name, source_type in config.RSS_FEEDS:
        feed_articles = _crawl_feed(url, source_name, source_type)
        articles.extend(feed_articles)

    logger.info("RSS total: fetched %d articles across %d feeds", len(articles), len(config.RSS_FEEDS))
    return articles

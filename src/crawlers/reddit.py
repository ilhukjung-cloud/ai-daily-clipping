"""Reddit crawler using the .json API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_REDDIT_API = "https://www.reddit.com/r/{sub}/top/.json"

# Reddit blocks the default requests User-Agent; use a custom one.
_REDDIT_HEADERS = {
    **config.HTTP_HEADERS,
    "User-Agent": "AI-Daily-Clipping/0.1 (by /u/ai-daily-clipping-bot)",
}


def _fetch_subreddit(subreddit: str) -> list[Article]:
    url = _REDDIT_API.format(sub=subreddit)
    params = {"t": "day", "limit": config.REDDIT_POSTS_PER_SUB}
    try:
        resp = requests.get(
            url,
            headers=_REDDIT_HEADERS,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch r/%s: %s", subreddit, exc)
        return []

    articles: list[Article] = []
    children = data.get("data", {}).get("children", [])
    for child in children:
        post = child.get("data", {})
        try:
            title = post["title"]
            url_field = post.get("url") or f"https://www.reddit.com{post['permalink']}"
            permalink = post.get("permalink", "")
            score = int(post.get("score", 0))
            num_comments = int(post.get("num_comments", 0))
            created_utc = post.get("created_utc", 0)
            published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            articles.append(
                Article(
                    title=title,
                    url=url_field,
                    source_type="community",
                    source_name=f"r/{subreddit}",
                    published_at=published_at,
                    score=score,
                    comments=num_comments,
                )
            )
        except Exception as exc:
            logger.warning("Skipping post in r/%s: %s", subreddit, exc)

    return articles


def crawl() -> list[Article]:
    """Crawl top daily posts from configured subreddits.

    Returns up to ``len(REDDIT_SUBREDDITS) * REDDIT_POSTS_PER_SUB`` articles.
    """
    all_articles: list[Article] = []
    for subreddit in config.REDDIT_SUBREDDITS:
        articles = _fetch_subreddit(subreddit)
        logger.info("r/%s: fetched %d articles", subreddit, len(articles))
        all_articles.extend(articles)
    return all_articles

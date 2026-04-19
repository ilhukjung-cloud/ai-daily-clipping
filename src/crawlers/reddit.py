"""Reddit crawler — optional OAuth when REDDIT_CLIENT_ID/SECRET are set."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from src import config, http_client
from src.models import Article

logger = logging.getLogger(__name__)

_PUBLIC_ENDPOINT = "https://www.reddit.com/r/{sub}/top/.json"
_OAUTH_ENDPOINT = "https://oauth.reddit.com/r/{sub}/top"
_OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_USER_AGENT = "AI-Daily-Clipping/0.2 (by /u/ai-daily-clipping-bot)"

# Cached OAuth state (populated lazily per process).
_OAUTH_TOKEN: str | None = None
_OAUTH_ATTEMPTED = False


def _fetch_oauth_token() -> str | None:
    """Request a client-credentials bearer token from Reddit.

    Returns the token string, or None if credentials missing / request fails.
    """
    global _OAUTH_TOKEN, _OAUTH_ATTEMPTED

    if _OAUTH_TOKEN or _OAUTH_ATTEMPTED:
        return _OAUTH_TOKEN
    _OAUTH_ATTEMPTED = True

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    try:
        resp = http_client.post(
            _OAUTH_TOKEN_URL,
            auth=requests.auth.HTTPBasicAuth(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": _USER_AGENT},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            _OAUTH_TOKEN = token
            logger.info("Reddit OAuth token acquired")
        return _OAUTH_TOKEN
    except Exception as exc:
        logger.warning("Reddit OAuth failed, falling back to public API: %s", exc)
        return None


def _request_url_and_headers(subreddit: str) -> tuple[str, dict[str, str]]:
    token = _fetch_oauth_token()
    if token:
        url = _OAUTH_ENDPOINT.format(sub=subreddit)
        headers = {"Authorization": f"bearer {token}", "User-Agent": _USER_AGENT}
    else:
        url = _PUBLIC_ENDPOINT.format(sub=subreddit)
        headers = {**config.HTTP_HEADERS, "User-Agent": _USER_AGENT}
    return url, headers


def _fetch_subreddit(subreddit: str) -> list[Article]:
    url, headers = _request_url_and_headers(subreddit)
    params = {"t": "day", "limit": config.REDDIT_POSTS_PER_SUB}
    try:
        resp = http_client.get(
            url,
            headers=headers,
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

    Uses OAuth when REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET env vars are set.
    Returns up to ``len(REDDIT_SUBREDDITS) * REDDIT_POSTS_PER_SUB`` articles.
    """
    all_articles: list[Article] = []
    for subreddit in config.REDDIT_SUBREDDITS:
        articles = _fetch_subreddit(subreddit)
        logger.info("r/%s: fetched %d articles", subreddit, len(articles))
        all_articles.extend(articles)
    return all_articles

"""GitHub Trending scraper."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from src import config
from src.models import Article

logger = logging.getLogger(__name__)


def crawl() -> list[Article]:
    """Scrape GitHub Trending and return AI-related repositories as Articles."""
    try:
        headers = {**config.HTTP_HEADERS, "Accept": "text/html"}
        resp = requests.get(
            config.GITHUB_TRENDING_URL,
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch GitHub Trending: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[Article] = []
    now = datetime.now(timezone.utc)

    for repo_row in soup.select("article.Box-row"):
        try:
            # Repo name and path
            heading = repo_row.select_one("h2 a")
            if not heading:
                continue
            repo_path = heading.get("href", "").strip()
            # repo_path is like /owner/repo
            repo_full_name = repo_path.lstrip("/")
            title = " / ".join(repo_full_name.split("/")) if "/" in repo_full_name else repo_full_name

            # Description
            desc_tag = repo_row.select_one("p")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Filter: description or repo name must contain an AI keyword
            haystack = (description + " " + repo_full_name).lower()
            if not any(kw.lower() in haystack for kw in config.GITHUB_AI_KEYWORDS):
                continue

            url = f"https://github.com{repo_path}"

            # Stars today
            stars_today: int | None = None
            for span in repo_row.select("span"):
                text = span.get_text(strip=True)
                if "stars today" in text.lower():
                    # e.g. "1,234 stars today"
                    parts = text.replace(",", "").split()
                    try:
                        stars_today = int(parts[0])
                    except (ValueError, IndexError):
                        pass
                    break

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_type="community",
                    source_name="GitHub Trending",
                    published_at=now,
                    score=stars_today,
                    summary=description or None,
                )
            )
        except Exception as exc:
            logger.warning("Skipping GitHub Trending repo row: %s", exc)

    logger.info("GitHub Trending: fetched %d AI-related repos", len(articles))
    return articles

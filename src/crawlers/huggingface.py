"""HuggingFace Daily Papers crawler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_HF_API_URL = "https://huggingface.co/api/daily_papers"


def _crawl_api() -> list[Article]:
    """Fetch papers from the HuggingFace daily papers API."""
    resp = requests.get(
        _HF_API_URL,
        headers=config.HTTP_HEADERS,
        timeout=config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    articles: list[Article] = []
    today = datetime.now(timezone.utc)

    for entry in data:
        try:
            paper = entry.get("paper", entry)
            paper_id = paper.get("id") or entry.get("id")
            title = paper.get("title") or entry.get("title")
            if not title or not paper_id:
                continue

            url = f"https://huggingface.co/papers/{paper_id}"
            upvotes = entry.get("numComments") or entry.get("upvotes") or paper.get("upvotes")

            # published_at: prefer the paper's publishedAt field
            raw_date = paper.get("publishedAt") or entry.get("publishedAt")
            if raw_date:
                try:
                    published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except ValueError:
                    published_at = today
            else:
                published_at = today

            summary = paper.get("summary") or entry.get("summary")

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_type="research",
                    source_name="HuggingFace Papers",
                    published_at=published_at,
                    score=int(upvotes) if upvotes is not None else None,
                    summary=summary or None,
                )
            )
        except Exception as exc:
            logger.warning("Skipping HuggingFace API paper entry: %s", exc)

    return articles


def _crawl_scrape() -> list[Article]:
    """Fallback: scrape the HuggingFace Papers page with BeautifulSoup."""
    resp = requests.get(
        config.HUGGINGFACE_PAPERS_URL,
        headers=config.HTTP_HEADERS,
        timeout=config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[Article] = []
    today = datetime.now(timezone.utc)

    for article_tag in soup.select("article"):
        try:
            link_tag = article_tag.select_one("a[href^='/papers/']")
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            paper_id = href.split("/papers/")[-1].strip("/")
            title_tag = article_tag.select_one("h3") or link_tag
            title = title_tag.get_text(strip=True)
            if not title or not paper_id:
                continue

            url = f"https://huggingface.co/papers/{paper_id}"

            # Try to find upvotes
            upvotes: int | None = None
            for btn in article_tag.select("button, span"):
                text = btn.get_text(strip=True)
                if text.isdigit():
                    upvotes = int(text)
                    break

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_type="research",
                    source_name="HuggingFace Papers",
                    published_at=today,
                    score=upvotes,
                )
            )
        except Exception as exc:
            logger.warning("Skipping HuggingFace scraped paper: %s", exc)

    return articles


def crawl() -> list[Article]:
    """Fetch HuggingFace Daily Papers, falling back to HTML scraping on API failure."""
    try:
        articles = _crawl_api()
        logger.info("HuggingFace Papers (API): fetched %d papers", len(articles))
        return articles
    except Exception as exc:
        logger.warning("HuggingFace API failed (%s); falling back to scraping", exc)

    try:
        articles = _crawl_scrape()
        logger.info("HuggingFace Papers (scrape): fetched %d papers", len(articles))
        return articles
    except Exception as exc:
        logger.warning("HuggingFace scrape also failed: %s", exc)
        return []

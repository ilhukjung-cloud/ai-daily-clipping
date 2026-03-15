"""arXiv crawler using the Atom API."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _parse_datetime(date_str: str) -> datetime:
    """Parse an ISO-8601 datetime string from arXiv into a UTC datetime."""
    # arXiv publishes dates like "2024-01-15T00:00:00Z"
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    logger.warning("Could not parse arXiv date: %r, using now(UTC)", date_str)
    return datetime.now(timezone.utc)


def crawl() -> list[Article]:
    """Fetch recent arXiv papers from cs.AI, cs.LG, cs.CL and return Articles."""
    search_query = "+OR+".join(f"cat:{cat}" for cat in config.ARXIV_CATEGORIES)
    # Build URL manually — requests.get(params=) percent-encodes ":" and "+"
    # which breaks arXiv's query parser (returns 0 results).
    url = (
        f"{ARXIV_API_URL}?search_query={search_query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={config.ARXIV_MAX_RESULTS}"
    )

    try:
        response = requests.get(
            url,
            headers=config.HTTP_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("arXiv request failed: %s", exc)
        return []

    articles: list[Article] = []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        logger.error("Failed to parse arXiv XML response: %s", exc)
        return []

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        try:
            title_el = entry.find(f"{{{ATOM_NS}}}title")
            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

            # The <id> element contains the canonical URL for the paper
            id_el = entry.find(f"{{{ATOM_NS}}}id")
            url = id_el.text.strip() if id_el is not None and id_el.text else ""

            published_el = entry.find(f"{{{ATOM_NS}}}published")
            published_str = published_el.text.strip() if published_el is not None and published_el.text else ""
            published_at = _parse_datetime(published_str) if published_str else datetime.now(timezone.utc)

            summary_el = entry.find(f"{{{ATOM_NS}}}summary")
            summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else None

            if not title or not url:
                logger.debug("Skipping arXiv entry with missing title or URL")
                continue

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_type="research",
                    source_name="arXiv",
                    published_at=published_at,
                    summary=summary,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error processing arXiv entry: %s", exc)
            continue

    logger.info("arXiv: fetched %d articles", len(articles))
    return articles

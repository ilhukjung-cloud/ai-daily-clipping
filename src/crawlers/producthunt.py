"""Product Hunt crawler using the GraphQL API."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from src import config, http_client
from src.models import Article

logger = logging.getLogger(__name__)

_GQL_QUERY = """
query($after: DateTime!) {
  posts(order: VOTES, postedAfter: $after) {
    edges {
      node {
        name
        url
        tagline
        votesCount
        topics {
          edges {
            node {
              slug
            }
          }
        }
      }
    }
  }
}
"""


def crawl() -> list[Article]:
    """Fetch today's top Product Hunt posts filtered by AI-related topics."""
    token = os.environ.get("PH_TOKEN")
    if not token:
        logger.warning(
            "PH_TOKEN environment variable not set; skipping Product Hunt crawler"
        )
        return []

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    headers = {
        **config.HTTP_HEADERS,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": _GQL_QUERY,
        "variables": {"after": yesterday},
    }

    try:
        resp = http_client.post(
            config.PRODUCTHUNT_API_URL,
            headers=headers,
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Product Hunt posts: %s", exc)
        return []

    errors = data.get("errors")
    if errors:
        logger.warning("Product Hunt GraphQL errors: %s", errors)
        return []

    ai_tags = {tag.lower() for tag in config.PRODUCTHUNT_AI_TAGS}
    articles: list[Article] = []
    today = datetime.now(timezone.utc)

    edges = data.get("data", {}).get("posts", {}).get("edges", [])
    for edge in edges:
        node = edge.get("node", {})
        try:
            # Collect topic slugs for this post
            topic_slugs = {
                t["node"]["slug"].lower()
                for t in node.get("topics", {}).get("edges", [])
                if t.get("node", {}).get("slug")
            }

            # Skip posts with no AI-related topics
            if not topic_slugs.intersection(ai_tags):
                continue

            name = node.get("name", "").strip()
            url = node.get("url", "").strip()
            tagline = node.get("tagline", "").strip()
            votes = node.get("votesCount")

            if not name or not url:
                continue

            articles.append(
                Article(
                    title=name,
                    url=url,
                    source_type="product",
                    source_name="Product Hunt",
                    published_at=today,
                    score=int(votes) if votes is not None else None,
                    summary=tagline or None,
                    tags=sorted(topic_slugs),
                )
            )
        except Exception as exc:
            logger.warning("Skipping Product Hunt post: %s", exc)

    logger.info("Product Hunt: fetched %d AI-related posts", len(articles))
    return articles

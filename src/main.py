"""AI Daily Clipping Crawler - main orchestration."""

import logging
import sys

from src.crawlers import reddit, hackernews, arxiv, rss, github, huggingface, producthunt
from src.processors.filter import filter_recent, filter_relevance, filter_min_score, limit_per_type
from src.processors.dedup import deduplicate
from src.processors.tagger import tag_articles
from src.content import fetch_content
from src.output import save_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CRAWLERS = [
    ("Reddit", reddit.crawl),
    ("Hacker News", hackernews.crawl),
    ("arXiv", arxiv.crawl),
    ("RSS Feeds", rss.crawl),
    ("GitHub Trending", github.crawl),
    ("HuggingFace Papers", huggingface.crawl),
    ("Product Hunt", producthunt.crawl),
]


def main() -> None:
    logger.info("Starting AI Daily Clipping Crawler")

    # 1. Crawl all sources
    all_articles = []
    for name, crawl_fn in CRAWLERS:
        try:
            logger.info(f"Crawling {name}...")
            articles = crawl_fn()
            logger.info(f"  {name}: {len(articles)} articles")
            all_articles.extend(articles)
        except Exception:
            logger.exception(f"  {name}: failed")

    raw_count = len(all_articles)
    logger.info(f"Total raw articles: {raw_count}")

    # 2. Filter (24h)
    articles = filter_recent(all_articles)
    filtered_count = len(articles)
    logger.info(f"After 24h filter: {filtered_count}")

    # 3. Relevance filter (drop non-AI community posts)
    articles = filter_relevance(articles)
    logger.info(f"After relevance filter: {len(articles)}")

    # 4. Minimum score filter
    articles = filter_min_score(articles)
    logger.info(f"After min score filter: {len(articles)}")

    # 5. Deduplicate
    articles = deduplicate(articles)
    logger.info(f"After dedup: {len(articles)}")

    # 6. Tag
    articles = tag_articles(articles)

    # 7. Top N per source type
    articles = limit_per_type(articles)
    logger.info(f"After top-N limit: {len(articles)}")

    # 8. Fetch original article content
    logger.info("Fetching article content...")
    contents = fetch_content(articles)

    # 9. Save JSON (with content)
    path = save_results(articles, raw_count, filtered_count, contents=contents)
    logger.info(f"JSON saved to {path}")

    # Summary
    by_type: dict[str, int] = {}
    for a in articles:
        by_type[a.source_type] = by_type.get(a.source_type, 0) + 1
    logger.info(f"Final: {len(articles)} articles — {by_type}")


if __name__ == "__main__":
    main()

"""AI Daily Clipping Crawler - main orchestration."""

import argparse
import logging
import sys

from src.crawlers import reddit, hackernews, arxiv, rss, github, huggingface, producthunt
from src.processors.filter import filter_recent, filter_relevance, filter_min_score, limit_per_type
from src.processors.dedup import deduplicate
from src.processors.tagger import tag_articles
from src.content import extract_body_summary, fetch_content
from src.output import save_results, save_formatted_results, save_raw_results

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


def _crawl_and_filter():
    """Run all crawlers and apply filtering pipeline.

    Returns (articles, raw_count, filtered_count, errors_by_source).
    """
    # 1. Crawl all sources in parallel (I/O-bound)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_articles: list = []
    errors_by_source: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=len(CRAWLERS)) as pool:
        future_to_name = {pool.submit(fn): name for name, fn in CRAWLERS}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                articles = future.result()
                logger.info(f"  {name}: {len(articles)} articles")
                all_articles.extend(articles)
            except Exception:
                logger.exception(f"  {name}: failed")
                errors_by_source[name] = errors_by_source.get(name, 0) + 1

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

    return articles, raw_count, filtered_count, errors_by_source


def main_agent() -> None:
    """Agent pipeline: crawl + filter + fetch content → raw.json.

    Claude Code scheduled task handles evaluation, translation, and final output.
    """
    logger.info("Starting AI Daily Clipping Crawler (agent mode)")

    articles, raw_count, filtered_count, errors_by_source = _crawl_and_filter()

    # Fetch original article content (Jina Reader + BS4 fallback)
    logger.info("Fetching article content...")
    contents = fetch_content(articles)

    # Attach content + body-derived summary to articles
    for i, a in enumerate(articles):
        a.content = contents[i] if i < len(contents) else ""
        a.body_summary = extract_body_summary(a.content)

    # Save raw.json (no Korean translation — Claude Code will handle it)
    path = save_raw_results(articles, raw_count, filtered_count, errors_by_source)
    logger.info(f"Raw JSON saved to {path}")

    # Summary
    by_type: dict[str, int] = {}
    for a in articles:
        by_type[a.source_type] = by_type.get(a.source_type, 0) + 1
    logger.info(f"Final: {len(articles)} articles — {by_type}")


def main_legacy() -> None:
    """Legacy pipeline: crawl + filter + fetch + translate (Gemini/Claude API) → final JSON."""
    logger.info("Starting AI Daily Clipping Crawler (legacy mode)")

    articles, raw_count, filtered_count, _errors_by_source = _crawl_and_filter()

    # Fetch original article content
    logger.info("Fetching article content...")
    contents = fetch_content(articles)

    # Summarize & translate to Korean (Gemini)
    logger.info("Translating articles to Korean...")
    try:
        from src.summarizer import summarize_articles
        formatted_articles = summarize_articles(articles)
        # Merge fetched content back in
        for i, d in enumerate(formatted_articles):
            d["content"] = contents[i] if i < len(contents) else ""
    except Exception:
        logger.exception("Korean summarization failed — falling back to raw articles")
        formatted_articles = [
            {**a.to_dict(), "content": contents[i] if i < len(contents) else "",
             "title_ko": a.title, "summary_ko": a.summary or ""}
            for i, a in enumerate(articles)
        ]

    # Save JSON (with content and Korean translations)
    path = save_formatted_results(formatted_articles, raw_count, filtered_count)
    logger.info(f"JSON saved to {path}")

    # Summary
    by_type: dict[str, int] = {}
    for a in articles:
        by_type[a.source_type] = by_type.get(a.source_type, 0) + 1
    logger.info(f"Final: {len(articles)} articles — {by_type}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Daily Clipping Crawler")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy pipeline with Gemini/Claude API translation",
    )
    args = parser.parse_args()

    if args.legacy:
        main_legacy()
    else:
        main_agent()


if __name__ == "__main__":
    main()

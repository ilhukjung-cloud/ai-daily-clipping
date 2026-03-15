"""Auto-tagger: keyword-based tagging of articles."""

from __future__ import annotations

import logging
import re

from src.models import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tag keyword definitions
# Each entry is (tag_label, [list_of_keywords_to_match]).
# The tag_label itself is also tried as a keyword unless it appears in the list.
# ---------------------------------------------------------------------------

_COMPANY_TAGS: list[tuple[str, list[str]]] = [
    ("OpenAI", ["openai"]),
    ("Anthropic", ["anthropic"]),
    ("Google", ["google"]),
    ("Meta", ["meta"]),
    ("Microsoft", ["microsoft"]),
    ("NVIDIA", ["nvidia"]),
    ("Apple", ["apple"]),
    ("Mistral", ["mistral"]),
    ("Cohere", ["cohere"]),
    ("Stability AI", ["stability ai", "stabilityai"]),
]

_MODEL_TAGS: list[tuple[str, list[str]]] = [
    ("GPT", ["gpt"]),
    ("Claude", ["claude"]),
    ("Gemini", ["gemini"]),
    ("Llama", ["llama"]),
    ("Mistral", ["mistral"]),
    ("DALL-E", ["dall-e", "dalle"]),
    ("Sora", ["sora"]),
    ("Stable Diffusion", ["stable diffusion", "stablediffusion"]),
    ("Midjourney", ["midjourney"]),
    ("Flux", ["flux"]),
]

_TOPIC_TAGS: list[tuple[str, list[str]]] = [
    ("LLM", ["llm", "large language model"]),
    ("vision", ["vision", "image recognition", "computer vision"]),
    ("robotics", ["robotics", "robot"]),
    ("speech", ["speech", "tts", "text-to-speech", "asr", "voice"]),
    ("safety", ["safety"]),
    ("alignment", ["alignment"]),
    ("open-source", ["open-source", "open source", "opensource"]),
    ("fine-tuning", ["fine-tuning", "fine tuning", "finetuning", "finetune"]),
    ("RAG", ["rag", "retrieval-augmented", "retrieval augmented"]),
    ("agents", ["agent", "agents", "agentic"]),
    ("reasoning", ["reasoning"]),
    ("multimodal", ["multimodal", "multi-modal"]),
]

# Flatten all tag definitions for efficient lookup
_ALL_TAGS: list[tuple[str, list[str]]] = _COMPANY_TAGS + _MODEL_TAGS + _TOPIC_TAGS

# Pre-compile one regex per tag (word-boundary aware where possible)
_TAG_PATTERNS: list[tuple[str, re.Pattern[str]]] = []
for _tag_label, _keywords in _ALL_TAGS:
    # Build alternation of all keywords for this tag
    parts = [re.escape(kw) for kw in _keywords]
    pattern = re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])", re.IGNORECASE)
    _TAG_PATTERNS.append((_tag_label, pattern))


def _text_for_article(article: Article) -> str:
    parts = [article.title]
    if article.summary:
        parts.append(article.summary)
    return " ".join(parts)


def tag_articles(articles: list[Article]) -> list[Article]:
    """Add matching keyword tags to each article in-place and return the list."""
    if not articles:
        return []

    total_tags_added = 0

    for article in articles:
        text = _text_for_article(article)
        existing = set(article.tags)
        new_tags: list[str] = []

        for tag_label, pattern in _TAG_PATTERNS:
            if tag_label in existing:
                continue
            if pattern.search(text):
                new_tags.append(tag_label)
                existing.add(tag_label)

        if new_tags:
            article.tags = article.tags + new_tags
            total_tags_added += len(new_tags)
            logger.debug("Tagged '%s' with: %s", article.title, new_tags)

    logger.info(
        "tag_articles: processed %d articles, added %d tags total",
        len(articles),
        total_tags_added,
    )
    return articles

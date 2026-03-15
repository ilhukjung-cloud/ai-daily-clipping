"""LLM formatter: translate titles to Korean and generate summaries."""

from __future__ import annotations

import json
import logging
import os

import anthropic

from src.models import Article

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
당신은 AI/기술 뉴스 에디터입니다. 아래 규칙을 정확히 따르세요.

규칙:
1. 각 기사의 title_ko: 원문 제목을 자연스러운 한국어로 번역. 고유명사(Claude, GPT, LLaMA 등)와 기술 용어(LLM, RAG, LoRA 등)는 원문 그대로 유지.
2. 각 기사의 summary_ko: 기사 내용을 한국어 1~2문장으로 요약. summary 필드가 없으면 title로 추론하되, 확실하지 않은 내용은 만들지 마세요.
3. 반드시 JSON 배열만 출력하세요. 다른 텍스트 없이."""

_USER_TEMPLATE = """\
아래 기사들을 한국어로 번역하고 요약해주세요.

입력:
{articles_json}

출력 형식 (JSON 배열, 입력과 같은 순서):
[
  {{"index": 0, "title_ko": "한국어 제목", "summary_ko": "한국어 요약 1~2문장"}},
  ...
]"""

# Process in batches to stay within context limits
_BATCH_SIZE = 15


def _make_batch(articles: list[Article], start: int) -> list[dict]:
    """Prepare a batch of articles for the LLM."""
    batch = articles[start:start + _BATCH_SIZE]
    return [
        {
            "index": start + i,
            "title": a.title,
            "summary": a.summary or "",
            "source_name": a.source_name,
        }
        for i, a in enumerate(batch)
    ]


def format_articles(articles: list[Article]) -> list[dict]:
    """Add title_ko and summary_ko to each article using Claude.

    Returns a list of dicts with original article data plus Korean fields.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; skipping Korean formatting")
        return [
            {**a.to_dict(), "title_ko": a.title, "summary_ko": a.summary or ""}
            for a in articles
        ]

    client = anthropic.Anthropic(api_key=api_key)
    results: list[dict | None] = [None] * len(articles)

    for start in range(0, len(articles), _BATCH_SIZE):
        batch_input = _make_batch(articles, start)
        user_msg = _USER_TEMPLATE.format(
            articles_json=json.dumps(batch_input, ensure_ascii=False, indent=2)
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = response.content[0].text.strip()
            # Strip markdown code fence if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parsed = json.loads(text)
            for item in parsed:
                idx = item["index"]
                if 0 <= idx < len(articles):
                    results[idx] = item
            logger.info(
                "Formatted batch %d-%d (%d articles)",
                start, min(start + _BATCH_SIZE, len(articles)), len(parsed),
            )
        except Exception:
            logger.exception("LLM formatting failed for batch starting at %d", start)

    # Merge results
    formatted = []
    for i, a in enumerate(articles):
        d = a.to_dict()
        if results[i]:
            d["title_ko"] = results[i].get("title_ko", a.title)
            d["summary_ko"] = results[i].get("summary_ko", a.summary or "")
        else:
            d["title_ko"] = a.title
            d["summary_ko"] = a.summary or ""
        formatted.append(d)

    return formatted

"""Fetch article content and summarize/translate using Gemini."""

from __future__ import annotations

import json
import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from google import genai

from src import config
from src.models import Article

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10
_EXTRACT_TIMEOUT = 10
_MAX_CONTENT_CHARS = 3000


def _extract_text(url: str) -> str:
    """Fetch a URL and extract the main text content."""
    try:
        headers = {**config.HTTP_HEADERS, "Accept": "text/html"}
        resp = requests.get(url, headers=headers, timeout=_EXTRACT_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise
    for tag in soup.select("script, style, nav, footer, header, aside, .sidebar, .ad, .comments"):
        tag.decompose()

    # Try <article> first, then <main>, then body
    main = soup.select_one("article") or soup.select_one("main") or soup.body
    if not main:
        return ""

    text = main.get_text(separator="\n", strip=True)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:_MAX_CONTENT_CHARS]


_SYSTEM_PROMPT = """\
당신은 AI/기술 뉴스 에디터입니다. 각 기사를 한국어로 번역·요약합니다.

규칙:
1. title_ko: 원문 제목을 자연스러운 한국어로 번역. 고유명사(Claude, GPT, LLaMA 등)와 기술 용어(LLM, RAG, LoRA 등)는 원문 유지.
2. summary_ko: 원문 내용 기반 한국어 2~3문장 요약. 핵심 정보(수치, 성능, 기업명 등) 포함. 원문이 없으면 제목에서 추론하되 확실하지 않은 내용은 만들지 마세요.
3. 반드시 JSON 배열만 출력. 다른 텍스트 없이."""


def summarize_articles(articles: list[Article]) -> list[dict]:
    """Fetch article content, summarize and translate to Korean using Gemini.

    Returns list of dicts with original article data plus title_ko, summary_ko.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set; skipping summarization")
        return [
            {**a.to_dict(), "title_ko": a.title, "summary_ko": a.summary or ""}
            for a in articles
        ]

    client = genai.Client(api_key=api_key)

    # Step 1: Fetch article content in parallel-ish
    logger.info("Fetching article content for %d articles...", len(articles))
    contents: list[str] = []
    for a in articles:
        # Skip reddit/imgur image links, GitHub repos (already have description)
        if any(d in a.url for d in ("i.redd.it", "v.redd.it", "imgur.com", "reddit.com/gallery")):
            contents.append("")
        elif a.source_name == "GitHub Trending":
            contents.append("")  # Already has summary from description
        else:
            text = _extract_text(a.url)
            contents.append(text)
            if text:
                logger.debug("Fetched %d chars from %s", len(text), a.url[:60])

    fetched = sum(1 for c in contents if c)
    logger.info("Fetched content for %d/%d articles", fetched, len(articles))

    # Step 2: Batch summarize with Gemini
    results: list[dict | None] = [None] * len(articles)

    for start in range(0, len(articles), _BATCH_SIZE):
        batch_end = min(start + _BATCH_SIZE, len(articles))
        batch_input = []
        for i in range(start, batch_end):
            a = articles[i]
            entry = {
                "index": i,
                "title": a.title,
                "source_name": a.source_name,
                "summary": a.summary or "",
                "content": contents[i][:2000] if contents[i] else "",
            }
            batch_input.append(entry)

        prompt = f"""{_SYSTEM_PROMPT}

입력:
{json.dumps(batch_input, ensure_ascii=False, indent=2)}

출력 (JSON 배열, 입력과 같은 순서):
[{{"index": 0, "title_ko": "...", "summary_ko": "..."}}, ...]"""

        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                text = response.text.strip()
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
                logger.info("Summarized batch %d-%d (%d articles)", start, batch_end, len(parsed))
                break
            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning("JSON parse error in batch %d-%d, retrying...", start, batch_end)
                    time.sleep(1)
                else:
                    logger.error("JSON parse error in batch %d-%d after retry", start, batch_end)
            except Exception:
                logger.exception("Gemini summarization failed for batch %d-%d", start, batch_end)
                break

        # Rate limit courtesy
        if batch_end < len(articles):
            time.sleep(1)

    # Merge
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

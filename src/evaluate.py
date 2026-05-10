"""Evaluate raw crawl output and write the public daily JSON.

The crawler intentionally writes ``output/YYYY-MM-DD.raw.json`` first.  This
module turns that raw file into ``output/YYYY-MM-DD.json`` so downstream clients
never depend on a separate scheduled LLM task being healthy.  If a Gemini API
key is available, it is used for Korean titles/summaries and importance scores;
otherwise a deterministic English fallback is written so the feed still updates.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

KST = timezone(timedelta(hours=9))
OUTPUT_DIR = Path("output")
RAW_SUFFIX = ".raw.json"
MAX_ARTICLES = 40
MIN_IMPORTANCE_SCORE = 4
GEMINI_BATCH_SIZE = 8
GEMINI_TIMEOUT = 60
GEMINI_MAX_RETRIES = 2
GEMINI_MODEL = os.environ.get("AI_EVALUATOR_MODEL", "gemini-2.0-flash")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
TRANSLATE_FALLBACK = os.environ.get("TRANSLATE_FALLBACK", "1") != "0"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

SOURCE_PRIORITY = {
    "official": 0,
    "media": 1,
    "research": 2,
    "community": 3,
    "product": 4,
}

IMPORTANT_KEYWORDS = {
    "openai": 1.4,
    "anthropic": 1.4,
    "google": 1.1,
    "deepmind": 1.2,
    "meta": 1.0,
    "microsoft": 1.0,
    "nvidia": 1.0,
    "claude": 1.2,
    "gpt": 1.2,
    "gemini": 1.2,
    "llama": 1.0,
    "model": 0.7,
    "agent": 0.8,
    "api": 0.7,
    "launch": 0.8,
    "release": 0.8,
    "open source": 0.7,
    "benchmark": 0.7,
    "funding": 0.8,
    "acquisition": 1.0,
    "lawsuit": 0.9,
    "regulation": 0.9,
    "security": 0.8,
    "safety": 0.8,
}

logger = logging.getLogger(__name__)
_gemini_disabled_reason: str | None = None


def kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def raw_path_for_date(date: str) -> Path:
    return OUTPUT_DIR / f"{date}.raw.json"


def final_path_for_date(date: str) -> Path:
    return OUTPUT_DIR / f"{date}.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", " ", value.lower()).strip()


def article_text(article: dict[str, Any]) -> str:
    return " ".join(
        str(article.get(key) or "")
        for key in ("title", "summary", "body_summary", "content", "source_name")
    )


def heuristic_score(article: dict[str, Any]) -> int:
    source_type = str(article.get("source_type") or "")
    score = {
        "official": 6.2,
        "media": 5.0,
        "research": 4.8,
        "community": 3.8,
        "product": 4.4,
    }.get(source_type, 4.0)

    community_score = article.get("score")
    if source_type == "community" and isinstance(community_score, int):
        if community_score >= 500:
            score += 1.8
        elif community_score >= 150:
            score += 1.2
        elif community_score >= 50:
            score += 0.6

    haystack = article_text(article).lower()
    for keyword, weight in IMPORTANT_KEYWORDS.items():
        if keyword in haystack:
            score += weight

    if len(str(article.get("content") or "")) > 500:
        score += 0.3

    return max(1, min(10, round(score)))


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[dict[str, Any]] = []

    for article in articles:
        url = str(article.get("url") or "").strip()
        title_key = normalize_text(str(article.get("title") or ""))[:120]
        if url and url in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        result.append(article)

    return result


def recent_final_urls(date: str) -> set[str]:
    current = datetime.strptime(date, "%Y-%m-%d").date()
    urls: set[str] = set()
    for days_back in range(1, 4):
        path = final_path_for_date((current - timedelta(days=days_back)).isoformat())
        if not path.exists():
            continue
        try:
            payload = load_json(path)
        except Exception:
            logger.warning("Could not load recent output %s", path)
            continue
        for article in payload.get("articles", []):
            url = str(article.get("url") or "").strip()
            if url:
                urls.add(url)
    return urls


def fallback_title_ko(article: dict[str, Any]) -> str:
    return str(article.get("title_ko") or article.get("title") or "").strip()


def fallback_summary_ko(article: dict[str, Any]) -> str:
    return str(
        article.get("summary_ko")
        or article.get("body_summary")
        or article.get("summary")
        or article.get("title")
        or ""
    ).strip()


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def translate_to_korean(text: str) -> str:
    if not text.strip():
        return ""

    try:
        response = requests.get(
            TRANSLATE_URL,
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "ko",
                "dt": "t",
                "q": text[:4500],
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return "".join(part[0] for part in payload[0] if part and part[0]).strip()
    except Exception as exc:
        logger.warning("Translation fallback failed: %s", exc)
        return text


def extract_json_array(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end < start:
            raise
        parsed = json.loads(cleaned[start : end + 1])

    if isinstance(parsed, dict):
        for key in ("articles", "items", "results"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break

    if not isinstance(parsed, list):
        raise ValueError("Gemini response was not a JSON array")

    return [item for item in parsed if isinstance(item, dict)]


def error_message_from_response(response: requests.Response) -> str:
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message")
        status = payload.get("error", {}).get("status")
        if message and status:
            return f"{response.status_code} {status}: {message}"
        if message:
            return f"{response.status_code}: {message}"
    except Exception:
        pass
    return f"HTTP {response.status_code}"


def gemini_evaluate_batch(batch: list[tuple[int, dict[str, Any]]]) -> dict[int, dict[str, Any]]:
    global _gemini_disabled_reason
    if _gemini_disabled_reason:
        return {}

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {}

    inputs = []
    for index, article in batch:
        inputs.append(
            {
                "index": index,
                "title": article.get("title", ""),
                "source_type": article.get("source_type", ""),
                "source_name": article.get("source_name", ""),
                "score": article.get("score"),
                "summary": article.get("summary", ""),
                "body_summary": article.get("body_summary", ""),
                "content": str(article.get("content") or "")[:1200],
            }
        )

    prompt = f"""당신은 AI/기술 뉴스 에디터입니다.
아래 기사들을 AI 업계 중요도 기준으로 평가하고 한국어 제목/요약을 작성하세요.

규칙:
- 반드시 JSON 배열만 출력합니다.
- 각 항목은 index, importance_score, title_ko, summary_ko 필드를 포함합니다.
- importance_score는 1~10 정수입니다.
- title_ko는 자연스러운 한국어 제목입니다. OpenAI, Claude, GPT, LLaMA, API, LLM 같은 고유명사/기술용어는 영문 유지합니다.
- summary_ko는 1~2문장, 기사에 없는 정보는 만들지 않습니다.

입력:
{json.dumps(inputs, ensure_ascii=False, indent=2)}
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    for attempt in range(GEMINI_MAX_RETRIES):
        try:
            response = requests.post(url, json=payload, timeout=GEMINI_TIMEOUT)
            if response.status_code >= 400:
                message = error_message_from_response(response)
                if "API_KEY_INVALID" in response.text or "API key expired" in response.text:
                    _gemini_disabled_reason = message
                raise RuntimeError(message)
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = extract_json_array(text)
            return {
                int(item["index"]): item
                for item in parsed
                if "index" in item
            }
        except Exception as exc:
            if attempt + 1 >= GEMINI_MAX_RETRIES or _gemini_disabled_reason:
                logger.warning("Gemini batch failed; using fallback provider: %s", exc)
                return {}
            time.sleep(2**attempt)

    return {}


def ollama_evaluate_batch(batch: list[tuple[int, dict[str, Any]]]) -> dict[int, dict[str, Any]]:
    if not OLLAMA_MODEL:
        return {}

    inputs = []
    for index, article in batch:
        inputs.append(
            {
                "index": index,
                "title": article.get("title", ""),
                "source_type": article.get("source_type", ""),
                "source_name": article.get("source_name", ""),
                "score": article.get("score"),
                "summary": article.get("summary", ""),
                "body_summary": article.get("body_summary", ""),
                "content": str(article.get("content") or "")[:900],
            }
        )

    prompt = f"""You are a Korean AI/technology news editor.
Evaluate and translate the following articles.

Return ONLY one JSON object with this schema:
{{"items":[{{"index":0,"importance_score":7,"title_ko":"...","summary_ko":"..."}}]}}

Rules:
- importance_score must be an integer 1-10.
- title_ko and summary_ko must be Korean.
- Keep product/company/model/technical names such as OpenAI, Claude, GPT, LLaMA, API, LLM in English.
- summary_ko must be 1-2 concise sentences and must not invent facts.

Articles:
{json.dumps(inputs, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        text = response.json().get("response", "")
        parsed = json.loads(text)
        items = parsed.get("items", parsed if isinstance(parsed, list) else [])
        if not isinstance(items, list):
            return {}
        return {
            int(item["index"]): item
            for item in items
            if isinstance(item, dict) and "index" in item
        }
    except Exception as exc:
        logger.warning("Ollama batch failed; using English fallback: %s", exc)
        return {}


def enrich_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = [dict(article) for article in articles]

    for index, article in enumerate(enriched):
        article["importance_score"] = heuristic_score(article)
        article["title_ko"] = fallback_title_ko(article)
        article["summary_ko"] = fallback_summary_ko(article)

    if os.environ.get("GEMINI_API_KEY"):
        logger.info("GEMINI_API_KEY found; evaluating/translating with Gemini")
    elif OLLAMA_MODEL:
        logger.info("OLLAMA_MODEL=%s found; evaluating/translating with Ollama", OLLAMA_MODEL)
    else:
        logger.warning("GEMINI_API_KEY not set; writing English fallback output")

    for start in range(0, len(enriched), GEMINI_BATCH_SIZE):
        batch = list(enumerate(enriched[start : start + GEMINI_BATCH_SIZE], start=start))
        updates = gemini_evaluate_batch(batch)
        if not updates:
            updates = ollama_evaluate_batch(batch)
        for index, update in updates.items():
            if not (0 <= index < len(enriched)):
                continue
            article = enriched[index]
            try:
                article["importance_score"] = max(
                    1, min(10, int(update.get("importance_score") or article["importance_score"]))
                )
            except Exception:
                pass
            article["title_ko"] = str(update.get("title_ko") or article["title_ko"]).strip()
            article["summary_ko"] = str(update.get("summary_ko") or article["summary_ko"]).strip()

    if TRANSLATE_FALLBACK:
        logger.info("Applying Korean translation fallback where needed")
        for article in enriched:
            if not has_korean(str(article.get("title_ko") or "")):
                article["title_ko"] = translate_to_korean(str(article.get("title") or ""))
            if not has_korean(str(article.get("summary_ko") or "")):
                article["summary_ko"] = translate_to_korean(fallback_summary_ko(article))

    return enriched


def final_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": article.get("title", ""),
        "title_ko": article.get("title_ko") or fallback_title_ko(article),
        "url": article.get("url", ""),
        "source_type": article.get("source_type", ""),
        "source_name": article.get("source_name", ""),
        "published_at": article.get("published_at", ""),
        "score": article.get("score"),
        "comments": article.get("comments"),
        "summary": article.get("summary", ""),
        "summary_ko": article.get("summary_ko") or fallback_summary_ko(article),
        "tags": article.get("tags") or [],
        "content": article.get("content", ""),
        "importance_score": article.get("importance_score") or heuristic_score(article),
    }


def evaluate_raw(raw_path: Path, overwrite: bool = False) -> Path | None:
    raw = load_json(raw_path)
    date = str(raw.get("date") or raw_path.name.removesuffix(RAW_SUFFIX))
    output_path = final_path_for_date(date)
    if output_path.exists() and not overwrite:
        logger.info("%s already exists; skipping", output_path)
        return None

    recent_urls = recent_final_urls(date)
    raw_articles = [
        article
        for article in raw.get("articles", [])
        if isinstance(article, dict) and str(article.get("url") or "").strip() not in recent_urls
    ]
    deduped = dedupe_articles(raw_articles)
    enriched = enrich_articles(deduped)
    selected = [
        article
        for article in enriched
        if int(article.get("importance_score") or 0) >= MIN_IMPORTANCE_SCORE
    ]
    selected.sort(
        key=lambda article: (
            -int(article.get("importance_score") or 0),
            SOURCE_PRIORITY.get(str(article.get("source_type") or ""), 99),
            -(article.get("score") or 0),
        )
    )
    selected = selected[:MAX_ARTICLES]

    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    payload = {
        "date": date,
        "crawled_at": raw.get("crawled_at"),
        "stats": {
            "total_raw": stats.get("total_raw", 0),
            "after_filter": stats.get("after_filter", len(raw_articles)),
            "after_dedup": len(selected),
        },
        "articles": [final_article(article) for article in selected],
    }
    write_json(output_path, payload)
    logger.info("Wrote %s with %d articles", output_path, len(selected))
    return output_path


def missing_raw_paths() -> list[Path]:
    paths = []
    for raw_path in sorted(OUTPUT_DIR.glob(f"*{RAW_SUFFIX}")):
        date = raw_path.name.removesuffix(RAW_SUFFIX)
        if not final_path_for_date(date).exists():
            paths.append(raw_path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate raw AI clipping output")
    parser.add_argument("--date", default=kst_today(), help="KST date to evaluate, YYYY-MM-DD")
    parser.add_argument("--all-missing", action="store_true", help="Process every raw file missing final JSON")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing final JSON")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.all_missing:
        paths = missing_raw_paths()
        if not paths:
            logger.info("No missing final JSON files")
            return
    else:
        paths = [raw_path_for_date(args.date)]

    for path in paths:
        if not path.exists():
            logger.info("Raw file not found: %s", path)
            continue
        evaluate_raw(path, overwrite=args.overwrite)


if __name__ == "__main__":
    main()

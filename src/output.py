"""Output module: JSON and HTML generation for daily clippings."""

from __future__ import annotations

import html
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
from pathlib import Path

from src.config import SOURCE_TYPE_PRIORITY
from src.models import Article

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path("output")
_DEFAULT_PRIORITY = max(SOURCE_TYPE_PRIORITY.values()) + 1


def _sort_key(article: Article) -> tuple[int, int]:
    """Primary: source_type priority (ascending). Secondary: score (descending, None last)."""
    priority = SOURCE_TYPE_PRIORITY.get(article.source_type, _DEFAULT_PRIORITY)
    # Negate score so that higher scores sort first; treat None as -infinity
    score_key = -(article.score if article.score is not None else -1_000_000)
    return (priority, score_key)


def save_results(
    articles: list[Article],
    raw_count: int,
    filtered_count: int,
    contents: list[str] | None = None,
) -> Path:
    """Serialise *articles* to ``output/YYYY-MM-DD.json`` and return the path.

    Parameters
    ----------
    articles:
        De-duplicated, tagged articles to save.
    raw_count:
        Total articles collected before any filtering.
    filtered_count:
        Articles remaining after time-filtering (before dedup).
    contents:
        Fetched original text for each article (same order). If provided,
        each article dict will include a ``content`` field.
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    crawled_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # Count by source type
    by_source_type: dict[str, int] = {}
    for article in articles:
        by_source_type[article.source_type] = by_source_type.get(article.source_type, 0) + 1

    sorted_articles = sorted(articles, key=_sort_key)

    # Build article dicts with optional content
    article_dicts = []
    # Map original index -> content
    content_map: dict[int, str] = {}
    if contents:
        for i, a in enumerate(articles):
            content_map[id(a)] = contents[i]

    for a in sorted_articles:
        d = a.to_dict()
        if contents:
            d["content"] = content_map.get(id(a), "")
        article_dicts.append(d)

    payload = {
        "date": date_str,
        "crawled_at": crawled_at,
        "stats": {
            "total_raw": raw_count,
            "after_filter": filtered_count,
            "after_dedup": len(articles),
            "by_source_type": by_source_type,
        },
        "articles": article_dicts,
    }

    output_dir = _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{date_str}.json"
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Saved %d articles to %s (raw=%d, filtered=%d)",
        len(articles),
        output_path,
        raw_count,
        filtered_count,
    )
    return output_path


def save_formatted_results(
    formatted_articles: list[dict],
    raw_count: int,
    filtered_count: int,
) -> Path:
    """Serialise pre-formatted article dicts (with Korean fields) to JSON.

    Parameters
    ----------
    formatted_articles:
        List of article dicts already containing title_ko, summary_ko, content, etc.
    raw_count:
        Total articles collected before any filtering.
    filtered_count:
        Articles remaining after time-filtering (before dedup).
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    crawled_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # Count by source type
    by_source_type: dict[str, int] = {}
    for a in formatted_articles:
        st = a.get("source_type", "unknown")
        by_source_type[st] = by_source_type.get(st, 0) + 1

    payload = {
        "date": date_str,
        "crawled_at": crawled_at,
        "stats": {
            "total_raw": raw_count,
            "after_filter": filtered_count,
            "after_dedup": len(formatted_articles),
            "by_source_type": by_source_type,
        },
        "articles": formatted_articles,
    }

    output_dir = _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{date_str}.json"
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Saved %d formatted articles to %s (raw=%d, filtered=%d)",
        len(formatted_articles),
        output_path,
        raw_count,
        filtered_count,
    )
    return output_path


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

_SECTION_META = {
    "official": ("🏢", "공식 발표", "#2563eb"),
    "media": ("📰", "미디어 보도", "#7c3aed"),
    "research": ("📄", "연구 논문", "#059669"),
    "community": ("💬", "커뮤니티 화제", "#ea580c"),
    "product": ("🚀", "새 제품/도구", "#d946ef"),
}
_SECTION_ORDER = ["official", "media", "research", "community", "product"]


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def save_html(formatted_articles: list[dict], raw_count: int) -> Path:
    """Generate an HTML clipping report from LLM-formatted articles."""
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")

    groups: dict[str, list[dict]] = defaultdict(list)
    for a in formatted_articles:
        groups[a["source_type"]].append(a)
    for items in groups.values():
        items.sort(key=lambda x: (x.get("score") or 0), reverse=True)

    total = len(formatted_articles)

    # Build section HTML
    sections = ""
    for st in _SECTION_ORDER:
        if st not in groups:
            continue
        emoji, label, color = _SECTION_META[st]
        cards = ""
        for a in groups[st]:
            title_ko = _esc(a.get("title_ko") or a["title"])
            title_en = _esc(a["title"])
            summary_ko = _esc(a.get("summary_ko") or "")
            url = _esc(a["url"])
            source = _esc(a["source_name"])

            stats = ""
            if a.get("score") is not None:
                stats += f'<span class="stat">⬆ {a["score"]:,}</span>'
            if a.get("comments") is not None:
                stats += f'<span class="stat">💬 {a["comments"]:,}</span>'

            tags = ""
            if a.get("tags"):
                tags = "".join(f'<span class="tag">{_esc(t)}</span>' for t in a["tags"])
                tags = f'<div class="tags">{tags}</div>'

            summary_html = f'<p class="summary">{summary_ko}</p>' if summary_ko else ""

            cards += f'''
        <article class="card">
          <div class="card-header">
            <span class="source-badge" style="--c:{color}">{source}</span>
            <div class="stats">{stats}</div>
          </div>
          <h3><a href="{url}" target="_blank">{title_ko}</a></h3>
          <p class="title-en">{title_en}</p>
          {summary_html}
          {tags}
        </article>'''

        sections += f'''
    <section class="section">
      <h2><span style="color:{color}">{emoji}</span> {label} <span class="cnt">{len(groups[st])}</span></h2>
      <div class="cards">{cards}
      </div>
    </section>'''

    # Count per type for header
    type_counts = {st: len(groups.get(st, [])) for st in _SECTION_ORDER if st in groups}

    page = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Daily Clipping — {date_str}</title>
<style>
:root{{--bg:#0f0f14;--s1:#1a1a24;--s2:#22222e;--bd:#2a2a3a;--t1:#e4e4ed;--t2:#9999aa;--ac:#6366f1}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--t1);line-height:1.6}}
.wrap{{max-width:900px;margin:0 auto;padding:2rem 1.5rem}}
.hdr{{text-align:center;padding:3rem 0 2rem;border-bottom:1px solid var(--bd);margin-bottom:2.5rem}}
.hdr h1{{font-size:2rem;font-weight:700;background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.5rem}}
.hdr .date{{color:var(--t2);font-size:1.05rem}}
.hdr .bar{{display:flex;justify-content:center;gap:2rem;margin-top:1.5rem;flex-wrap:wrap}}
.hdr .si{{display:flex;flex-direction:column;align-items:center}}
.hdr .sn{{font-size:1.5rem;font-weight:700;color:var(--ac)}}
.hdr .sl{{font-size:.78rem;color:var(--t2);text-transform:uppercase;letter-spacing:.05em}}
.section{{margin-bottom:2.5rem}}
.section h2{{font-size:1.25rem;font-weight:600;margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}}
.cnt{{background:var(--s2);color:var(--t2);font-size:.72rem;font-weight:500;padding:.15rem .5rem;border-radius:99px;margin-left:.25rem}}
.cards{{display:flex;flex-direction:column;gap:.75rem}}
.card{{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:1.1rem 1.2rem;transition:border-color .2s,transform .15s}}
.card:hover{{border-color:var(--ac);transform:translateY(-1px)}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:.45rem}}
.source-badge{{font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--c);background:color-mix(in srgb,var(--c) 12%,transparent);padding:.18rem .55rem;border-radius:6px}}
.stats{{display:flex;gap:.75rem}}
.stat{{font-size:.78rem;color:var(--t2);font-weight:500}}
.card h3{{font-size:.95rem;font-weight:600;line-height:1.45;margin-bottom:.2rem}}
.card h3 a{{color:var(--t1);text-decoration:none}}
.card h3 a:hover{{color:var(--ac)}}
.title-en{{font-size:.75rem;color:var(--t2);opacity:.7;margin-bottom:.3rem;line-height:1.4}}
.summary{{font-size:.82rem;color:var(--t2);line-height:1.5;margin-bottom:.35rem}}
.tags{{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.4rem}}
.tag{{font-size:.66rem;color:var(--ac);background:color-mix(in srgb,var(--ac) 10%,transparent);padding:.1rem .4rem;border-radius:4px;font-weight:500}}
.ftr{{text-align:center;padding:2rem 0;border-top:1px solid var(--bd);margin-top:1rem;color:var(--t2);font-size:.78rem}}
@media(max-width:640px){{.wrap{{padding:1rem}}.hdr h1{{font-size:1.4rem}}.hdr .bar{{gap:1rem}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="hdr">
    <h1>AI Daily Clipping</h1>
    <p class="date">{date_str}</p>
    <div class="bar">
      <div class="si"><span class="sn">{raw_count:,}</span><span class="sl">수집</span></div>
      <div class="si"><span class="sn">{total}</span><span class="sl">선별</span></div>
      {"".join(f'<div class="si"><span class="sn">{c}</span><span class="sl">{_SECTION_META[s][1]}</span></div>' for s, c in type_counts.items())}
    </div>
  </header>
  {sections}
  <footer class="ftr">Generated at {now.strftime("%Y-%m-%dT%H:%M:%SZ")} · AI Daily Clipping Crawler</footer>
</div>
</body>
</html>'''

    output_dir = _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{date_str}.html"
    path.write_text(page, encoding="utf-8")
    logger.info("Saved HTML to %s", path)
    return path

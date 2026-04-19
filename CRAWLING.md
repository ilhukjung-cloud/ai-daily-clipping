# 크롤링 파이프라인 설명서

> 업그레이드 검토용 — 현재(2026-04-19 기준) 소스 / 순서 / 파라미터 / 약점을
> 한눈에 볼 수 있도록 정리. 코드 참조는 `파일:라인` 형식.

---

## 1. 진입점과 실행 경로

| 항목 | 값 |
|---|---|
| 실행 파일 | [src/main.py](src/main.py) |
| 기본 모드 | `main_agent()` — crawl + content fetch → `output/YYYY-MM-DD.raw.json` |
| Legacy 모드 | `main_agent --legacy` → Gemini 요약까지 포함한 `YYYY-MM-DD.json` |
| 스케줄 | GitHub Actions `cron: '0 22 * * *'` (UTC 22:00 = KST 07:00) — [daily-crawl.yml](.github/workflows/daily-crawl.yml) |
| 커밋 | `output/` 폴더를 github-actions[bot] 계정이 자동 push |
| 후속 처리 | Claude Code scheduled task가 raw.json을 읽어 평가·번역·최종 JSON 생성 |

---

## 2. 파이프라인 7단계

```
  1. 크롤링         ─ 7개 소스 병렬 X, 순차 실행  (main.py:36-43)
  2. 24h 필터       ─ 최근 24시간만, 미래 1h+는 버림  (processors/filter.py:14)
  3. 관련성 필터    ─ community 소스만 AI 키워드 제목 요구  (filter.py:67)
  4. 최소 점수 필터 ─ community score < 10 drop  (filter.py:86, config.MIN_SCORE)
  5. 중복 제거      ─ URL 일치 → 제목 유사도 ≥0.7 (SequenceMatcher)  (dedup.py)
  6. 자동 태깅      ─ 기업/모델/토픽 키워드 매칭  (tagger.py)
  7. 타입별 Top N   ─ score 내림차순 상위 N개만  (filter.py:101)
      ↓
  8. 본문 fetch     ─ Jina Reader → BS4 fallback, 12,000자 상한  (content.py)
  9. body_summary   ─ content에서 추출적 요약 600자  (content.py:extract_body_summary)
  10. raw.json 저장  (output.py:save_raw_results)
```

---

## 3. 7개 크롤러 상세

| # | 소스 | 구현 | 엔드포인트 | 스코프 | 점수 | 주의사항 |
|---|---|---|---|---|---|---|
| 1 | **Reddit** | [reddit.py](src/crawlers/reddit.py) | `reddit.com/r/{sub}/top/.json?t=day` | 8 서브레딧 × 상위 8개 | upvotes | 커스텀 UA 필수. 인증 없음 → 가끔 403 |
| 2 | **Hacker News** | [hackernews.py](src/crawlers/hackernews.py) | Firebase `topstories.json` → `item/{id}.json` | top 50 중 AI 키워드 제목만 | points | 개별 item당 HTTP 1회 → **최대 50회 호출, 느림** |
| 3 | **arXiv** | [arxiv.py](src/crawlers/arxiv.py) | Atom API `export.arxiv.org/api/query` | cs.AI + cs.LG + cs.CL 20건 | 없음 | URL 직접 조립 (requests의 `params=`가 `:` `+`를 깨뜨림) |
| 4 | **RSS 피드** | [rss.py](src/crawlers/rss.py) | 12개 피드 (OpenAI, Anthropic, TechCrunch 등) | feed 전체 | 없음 | `feedparser`, bozo 경고 무시. summary 1,000자 trim |
| 5 | **GitHub Trending** | [github.py](src/crawlers/github.py) | `github.com/trending?since=daily` HTML | AI 키워드 포함 repo만 | stars today | HTML 구조 변경에 취약 |
| 6 | **HuggingFace Papers** | [huggingface.py](src/crawlers/huggingface.py) | `/api/daily_papers` → HTML fallback | 일일 페이퍼 | upvotes | API 실패 시 scraping, 둘 다 실패하면 빈 리스트 |
| 7 | **Product Hunt** | [producthunt.py](src/crawlers/producthunt.py) | GraphQL v2 (`POST`) | postedAfter=어제, votes 순 | votes | `PH_TOKEN` 환경변수 필수, 없으면 skip |

**호출 방식**: 모두 `requests` 단일 스레드 순차. 병렬화(asyncio/threading)는 없음.

---

## 4. 소스 타입과 우선순위

```python
SOURCE_TYPE_PRIORITY = {        MAX_ARTICLES_PER_TYPE = {
  "official": 0,                  "official": 20,
  "media":    1,                  "media":    20,
  "research": 2,                  "research": 20,
  "community":3,                  "community":20,
  "product":  4,                  "product":  10,
}                               }
```

- **우선순위**: dedup에서 동일 URL/유사 제목이 충돌할 때 낮은 숫자 승. 예: `official` TechCrunch 기사와 `community` Reddit 링크 중복 시 official 유지.
- **타입별 캡**: 최대 `20+20+20+20+10 = 90개` (현실적으로는 dedup 후 20~35개).

---

## 5. 본문 수집 (content.py)

| 단계 | 동작 | 제한 |
|---|---|---|
| Jina Reader | `https://r.jina.ai/{url}` — 마크다운 변환 | 무료 20 req/min, **3초 간격** |
| BS4 fallback | `<article>` → `<main>` → `<body>` 본문 추출 | timeout 10s |
| 스킵 | `i.redd.it`, `v.redd.it`, `imgur.com`, `reddit.com/gallery`, `GitHub Trending` | — |
| 정제 | `_clean_jina_markdown()` — 이미지/공유버튼/링크만 있는 줄 제거 | — |
| 길이 | `MAX_CONTENT_LENGTH = 12,000` (5,000 → 12,000으로 상향) | — |
| body_summary | 80자↑, 문장부호 포함 줄만 추려 600자 | 없으면 `""` |

**체감 속도**: 20~30건 × 3초 ≈ 60~90초. 크롤러보다 본문 fetch가 병목.

---

## 6. 현재 출력 필드 (raw.json)

```json
{
  "date": "2026-04-19",
  "crawled_at": "KST ISO",
  "stats": { "total_raw", "after_filter", "after_dedup", "by_source_type" },
  "articles": [{
    "title", "url", "source_type", "source_name",
    "published_at",
    "score", "comments",
    "summary":       "RSS teaser 또는 API 원본 요약",
    "content":       "Jina 정제본 (최대 12,000자)",
    "body_summary":  "본문 기반 추출 요약 (~600자)",  ← 신규
    "tags": [],
    "importance_score", "title_ko", "summary_ko": ""  ← 후단계에서 채움
  }]
}
```

---

## 7. 알려진 약점 / 업그레이드 후보 (우선순위 순)

### 🔴 High impact

1. **본문 수집 병목** — Jina 3초 간격 순차 호출이 전체 실행시간의 70%+.
   - 대안: `asyncio + httpx` 동시 실행 (Jina 20 req/min 내), 또는 Jina Premium 키로 제한 완화.
2. **TechCrunch/The Verge 본문 손실** — nav/ads/share 버튼이 본문보다 앞에 위치해 상한에 걸림.
   - 12,000자 상향으로 개선되긴 했지만, 도메인별 파서(예: `article` 태그 직접 요청) 추가가 근본 해법.
3. **크롤러 단계 병렬화 없음** — 7개 소스가 순차 실행. I/O 바운드라 단순 `ThreadPoolExecutor`로 3~5배 단축 가능.

### 🟡 Medium impact

4. **HN 개별 item 호출 50회** — Firebase에 하나씩 묶어서 호출. `asyncio.gather`로 해결 가능.
5. **중복 제거 O(n²)** — 현재 수백 건 규모라 OK지만, 크롤 범위를 늘릴 경우 MinHash / simhash 고려.
6. **AI 관련성 필터가 제목만 검사** — 본문 요약이 AI인데 제목에 키워드 없는 Reddit 글 탈락. summary도 함께 검사 검토.
7. **GitHub Trending HTML 스크래핑** — GitHub UI 변경 한 번에 깨짐. GraphQL API 전환 고려 (`trending` 엔드포인트는 공식엔 없지만 검색 API + `sort:stars` 대체 가능).
8. **Reddit 인증 없음** — 403 간헐적. OAuth 토큰 쓰면 안정성↑.

### 🟢 Low impact / 취향

9. **태그 키워드가 하드코딩** — 신규 모델 (Gemini 2, Grok, DeepSeek 등) 주기적 업데이트 필요.
10. **arXiv max_results=20 고정** — 트렌드에 따라 늘리거나 카테고리 추가 여지.
11. **에러 로깅은 있는데 소스별 성공/실패 메트릭 JSON에 반영 안 됨** — `stats.errors_by_source` 필드 추가하면 관측성↑.
12. **재시도/지수 백오프 없음** — 일시적 5xx 발생 시 해당 소스 통째로 스킵.

---

## 8. 환경 변수

| 변수 | 용도 | 필수 여부 |
|---|---|---|
| `PH_TOKEN` | Product Hunt GraphQL Bearer | 없으면 Product Hunt 소스만 skip |
| `GEMINI_API_KEY` | legacy 모드 한국어 요약 | agent 모드에서는 불필요 |

---

## 9. 로컬 실행

```bash
# agent 모드 (기본, raw.json만 생성)
uv run python -m src.main

# legacy 모드 (Gemini 요약까지)
uv run python -m src.main --legacy
```

산출물: `output/YYYY-MM-DD.raw.json` (agent) 또는 `output/YYYY-MM-DD.json` (legacy)

# AI Daily Clipping — 서비스 스펙 문서

> 이 문서는 외부 프로젝트(예: claude-cowork)가 AI Daily Clipping의 리소스를 활용하여
> 이메일 뉴스레터 등 파생 서비스를 구축할 때 참고하기 위한 기술 명세입니다.

---

## 1. 서비스 개요

**AI Daily Clipping**은 매일 7개 소스에서 AI/기술 뉴스를 자동 수집하고,
한국어 번역·요약을 거쳐 웹 리포트로 발행하는 시스템입니다.

- **실행 주기**: 매일 KST 07:00 (UTC 22:00), GitHub Actions cron
- **배포 URL**: https://ai-daily-clipping.pages.dev/
- **GitHub**: https://github.com/ilhukjung-cloud/ai-daily-clipping

---

## 2. 사용 가능한 리소스

### 2.1 JSON 데이터 (구조화된 원본)

**위치**: `output/YYYY-MM-DD.json` (GitHub repo에 자동 커밋)

```json
{
  "date": "2026-03-15",
  "crawled_at": "2026-03-15T22:00:00Z",
  "stats": {
    "total_raw": 1152,
    "after_filter": 95,
    "after_dedup": 33,
    "by_source_type": { "community": 20, "media": 13 }
  },
  "articles": [ ... ]
}
```

**각 article 필드**:

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `title` | string | 원문 제목 (영어) | `"LangChain Releases Deep Agents..."` |
| `url` | string | 원문 링크 | `"https://techcrunch.com/..."` |
| `source_type` | string | 소스 분류 | `"official"`, `"media"`, `"research"`, `"community"`, `"product"` |
| `source_name` | string | 구체적 소스명 | `"TechCrunch AI"`, `"r/ClaudeAI"`, `"GitHub Trending"` |
| `published_at` | string (ISO 8601) | 게시 시각 UTC | `"2026-03-15T21:01:51+00:00"` |
| `score` | int \| null | 투표/스타 수 | `2995`, `null` |
| `comments` | int \| null | 댓글 수 | `162`, `null` |
| `summary` | string \| null | 원문 요약 (영어, 크롤링 시 수집) | `"The company is reportedly..."` |
| `tags` | string[] | 자동 태깅된 키워드 | `["Claude", "agents"]` |
| `content` | string | 원문에서 추출한 본문 텍스트 (최대 3,000자) | `"In Brief Posted: 2:01 PM..."` |

> **content 필드 참고**: Reddit 이미지/동영상 링크, GitHub Trending 저장소는 빈 문자열.
> 나머지 기사는 원문 HTML에서 `<article>` → `<main>` → `<body>` 순으로 본문을 추출.

### 2.2 GitHub Raw 파일 접근

JSON 데이터를 프로그래밍 방식으로 가져올 때:

```
https://raw.githubusercontent.com/ilhukjung-cloud/ai-daily-clipping/main/output/YYYY-MM-DD.json
```

---

## 3. 데이터 파이프라인 흐름

```
7개 소스 크롤링 (약 1,000건+)
    ↓
24시간 필터 (최근 24h만)
    ↓
AI 관련성 필터 (커뮤니티 글은 AI 키워드 포함 필수)
    ↓
최소 점수 필터 (커뮤니티 score >= 10)
    ↓
중복 제거 (URL + 제목 유사도 0.7)
    ↓
자동 태깅 (기업명, 모델명, 토픽)
    ↓
소스 타입별 Top N 제한 (커뮤니티 20개, 프로덕트 10개 등)
    ↓
원문 content fetch (BeautifulSoup, 최대 3,000자)
    ↓
JSON 저장 (output/YYYY-MM-DD.json, content 포함)
    ↓
GitHub 자동 커밋
```

---

## 4. 크롤링 소스 목록

| 소스 | source_type | source_name 예시 | API/방식 |
|------|-------------|-----------------|---------|
| Reddit (8개 서브레딧) | community | `r/OpenAI`, `r/ClaudeAI`, `r/LocalLLaMA` 등 | Reddit JSON API |
| Hacker News | community | `Hacker News` | Firebase API |
| arXiv | research | `arXiv` | Atom API (cs.AI, cs.LG, cs.CL) |
| RSS 피드 (12개) | official / media | `OpenAI Blog`, `TechCrunch AI` 등 | feedparser |
| GitHub Trending | community | `GitHub Trending` | HTML 스크래핑 |
| HuggingFace Papers | research | `HuggingFace Papers` | HF API |
| Product Hunt | product | `Product Hunt` | GraphQL API |

---

## 5. source_type 분류 체계

| source_type | 설명 | 우선순위 (낮을수록 높음) |
|-------------|------|------------------------|
| `official` | AI 기업 공식 블로그 (OpenAI, Anthropic, Google AI, Meta AI, Microsoft AI, NVIDIA) | 0 |
| `media` | 전문 미디어 (TechCrunch, The Verge, VentureBeat, MIT Tech Review, The Decoder, MarkTechPost) | 1 |
| `research` | 학술 논문 (arXiv, HuggingFace Papers) | 2 |
| `community` | 커뮤니티 (Reddit, Hacker News, GitHub Trending) | 3 |
| `product` | 새 제품/도구 (Product Hunt) | 4 |

---

## 6. 이메일 서비스 연동 가이드

### 6.1 데이터 가져오기 (권장 방식)

**방법 A: GitHub Raw URL에서 JSON fetch**

```python
import requests
from datetime import datetime

date = datetime.now().strftime("%Y-%m-%d")
url = f"https://raw.githubusercontent.com/ilhukjung-cloud/ai-daily-clipping/main/output/{date}.json"
data = requests.get(url).json()
articles = data["articles"]
```

**방법 B: 로컬 파일 직접 읽기** (같은 서버에서 운영 시)

```python
import json
from pathlib import Path

date = "2026-03-15"
with open(f"output/{date}.json") as f:
    data = json.load(f)
```

**방법 C: Cloudflare Pages HTML 스크래핑** (비권장, JSON 우선 사용)

### 6.2 한국어 번역·요약

JSON에는 영어 원문 + `content` (원문 본문 텍스트)가 포함됨.
한국어 번역·요약은 cowork(Claude)에서 JSON 데이터를 읽고 직접 수행.

### 6.3 이메일 콘텐츠 구성 제안

```
제목: [AI Daily] 2026-03-15 — 33건의 AI 뉴스 클리핑

섹션 구성 (source_type 기준):
  🏢 공식 발표 (official)     — 기업 공식 블로그
  📰 미디어 보도 (media)      — 전문 미디어 기사
  📄 연구 논문 (research)     — arXiv, HF Papers
  💬 커뮤니티 화제 (community) — Reddit, HN, GitHub
  🚀 새 제품/도구 (product)   — Product Hunt

각 기사:
  - 한국어 제목 (title_ko) → 클릭 시 원문 URL로 이동
  - 영어 원제 (title) — 서브타이틀
  - 한국어 요약 (summary_ko) — 2~3문장
  - 메타 정보: source_name, score, comments, tags
```

---

## 7. API / 확장 포인트

### 7.1 실행 타이밍

| 이벤트 | 시각 (KST) | 설명 |
|--------|-----------|------|
| 크롤링 실행 | 07:00 | GitHub Actions cron |
| JSON 생성 | ~07:01 | 크롤링 완료 직후 |
| HTML 생성 + 배포 | ~07:02 | Gemini 요약 후 |
| GitHub 커밋 | ~07:02 | output/ 폴더 자동 커밋 |

이메일 발송은 **KST 07:10~07:30** 사이에 스케줄링하면
최신 데이터가 확실히 준비된 상태에서 발송 가능.

---

## 8. 환경 변수

| 변수명 | 용도 | 필수 |
|--------|------|------|
| `PH_TOKEN` | Product Hunt GraphQL API | Product Hunt 크롤링 시 |

---

## 9. 기술 스택

- **언어**: Python 3.11+
- **패키지 관리**: uv + pyproject.toml (hatchling)
- **주요 의존성**: requests, feedparser, beautifulsoup4, lxml
- **CI/CD**: GitHub Actions

---

## 10. 파일 구조

```
ai-daily-clipping/
├── .github/workflows/daily-crawl.yml   # GitHub Actions 워크플로우
├── pyproject.toml                       # 프로젝트 설정 + 의존성
├── src/
│   ├── main.py                          # 진입점: 전체 파이프라인 오케스트레이션
│   ├── config.py                        # 소스 설정, 키워드, 임계값
│   ├── models.py                        # Article 데이터 모델
│   ├── content.py                       # 원문 본문 텍스트 fetch (BeautifulSoup)
│   ├── output.py                        # JSON 생성
│   ├── crawlers/
│   │   ├── reddit.py                    # Reddit JSON API
│   │   ├── hackernews.py                # HN Firebase API
│   │   ├── arxiv.py                     # arXiv Atom API
│   │   ├── rss.py                       # RSS 피드 (feedparser)
│   │   ├── github.py                    # GitHub Trending 스크래핑
│   │   ├── huggingface.py               # HuggingFace Papers API
│   │   └── producthunt.py               # Product Hunt GraphQL
│   └── processors/
│       ├── filter.py                    # 시간/관련성/점수 필터
│       ├── dedup.py                     # URL + 제목 유사도 중복 제거
│       └── tagger.py                    # 자동 태깅
└── output/
    └── YYYY-MM-DD.json                  # 일별 JSON (GitHub에 자동 커밋, content 포함)
```

---

## 11. 실제 데이터 예시 (2026-03-15)

**통계**: 1,152건 수집 → 95건 (24h 필터) → 33건 (최종 선별)

**article 예시**:

```json
{
  "title": "LangChain Releases Deep Agents: A Structured Runtime for Planning, Memory, and Context Isolation in Multi-Step AI Agents",
  "url": "https://www.marktechpost.com/2026/03/15/langchain-releases-deep-agents...",
  "source_type": "media",
  "source_name": "MarkTechPost",
  "published_at": "2026-03-15T09:07:48+00:00",
  "score": null,
  "comments": null,
  "summary": "Most LLM agents work well for short tool-calling loops but start to break down...",
  "tags": ["LLM", "agents"],
  "content": "Most LLM agents work well for short tool-calling loops but start to break down when the task becomes multi-step, stateful, and artifact-heavy. LangChain's Deep Agents is designed for that gap..."
}
```

> `content`는 원문 웹페이지에서 추출한 본문 (최대 3,000자). 한국어 번역·요약은 이 데이터를 기반으로 cowork(Claude)에서 수행.

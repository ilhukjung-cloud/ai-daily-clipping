---
name: ai-clipping-agent
description: Process raw.json from daily crawl — evaluate article importance, translate to Korean, produce final output
user_invocable: true
---

# AI Daily Clipping Agent

오늘 날짜의 `output/YYYY-MM-DD.raw.json`을 읽어서 기사를 평가하고, 한국어 번역/요약을 생성하여 최종 `output/YYYY-MM-DD.json`을 만드는 에이전트 스킬.

## 실행 절차

### 1. raw.json 파일 찾기

- 오늘 날짜(KST 기준, `TZ=Asia/Seoul date +%Y-%m-%d`)의 `output/YYYY-MM-DD.raw.json` 파일을 찾는다. 크롤러가 KST 기준 날짜로 파일을 저장하므로 반드시 KST 를 사용한다.
- 파일이 없으면 짧은 실패 메시지("오늘 날짜 raw.json 파일 없음")만 출력하고 **즉시 종료**한다. 다른 날짜 파일을 대신 선택하지 않는다.
- 이미 같은 날짜의 `output/YYYY-MM-DD.json`(최종 파일)이 존재하면 재실행이므로 중단한다.

### 2. 기사 중요도 평가

각 기사의 `title`, `summary`, `content`, `source_type`, `score`, `tags`를 읽고 AI 업계 중요도를 1-10 점수로 평가한다.

**평가 기준:**

| 점수 | 기준 | 예시 |
|------|------|------|
| 9-10 | 업계 판도를 바꾸는 발표 | 새 모델 출시 (GPT-5, Claude 4 등), 주요 인수합병, 규제 변화 |
| 7-8 | 주요 기업의 중요한 업데이트 | 새 API/기능 출시, 주요 파트너십, 오픈소스 공개 |
| 5-6 | 주목할 만한 연구/커뮤니티 동향 | 흥미로운 논문, 인기 오픈소스 프로젝트, 업계 트렌드 |
| 3-4 | 일반적인 뉴스/토론 | 일반 기술 기사, 커뮤니티 토론, 비교 리뷰 |
| 1-2 | 관련성 낮음 | 단순 튜토리얼, 홍보성 글, 반복적인 내용 |

**소스 타입별 기본 가중치:**
- `official` (공식 블로그): 기본 +2 보너스 (공식 발표는 중요)
- `media` (미디어): 기본 +1 보너스
- `research` (연구): 내용 기반 판단
- `community` (커뮤니티): score 참고하여 판단
- `product` (제품): 혁신성 기반 판단

### 3. 상위 기사 선별

- `importance_score` 기준 내림차순 정렬
- 상위 40개 선별 (또는 전체가 40개 미만이면 전부)
- 4점 이하 기사는 제외

#### 3-a. 당일 내 중복 제거

같은 발표/사건을 여러 소스가 동시에 다루는 경우 하나만 남긴다. 판별은 다음 순서로 수행한다:

1. **URL 동일**: 같은 URL 이면 무조건 중복.
2. **주제 동일**: `title` + `summary` 로 핵심 주제(같은 발표·같은 인수합병·같은 모델 출시 등)가 동일한지 판단.
   - 예: OpenAI 블로그 원문 + TechCrunch 기사 + The Verge 기사 + Hacker News 링크가 모두 동일한 발표를 다루면 하나로 합친다.
   - 단, 같은 주제라도 **새로운 정보·분석 각도**가 명확히 다르면 별개 기사로 유지 (예: "발표" vs "유출 의혹" vs "규제기관 반응").

**유지 우선순위** (중복 중 어느 것을 남길지):
1. `source_type == "official"` (원 발표)
2. `source_type == "media"` 중 `importance_score` 가장 높은 것
3. `source_type == "community"` (HN/Reddit 등)

#### 3-b. 최근 3일 커버리지 제외

`output/YYYY-MM-DD.json` 파일이 최근 3일(오늘 제외: 어제·그제·3일 전) 중 존재하는 것들을 모두 로드해, 거기 포함된 기사와 **중복되는 오늘자 기사는 제외**한다.

- **URL 동일**: 즉시 제외.
- **주제 동일**: 오늘 raw 기사의 `title` + `summary` 가 최근 3일 출력물의 `title` / `title_ko` / `summary_ko` 중 하나와 사실상 같은 사건·주제를 가리키면 제외.
  - 예: 어제 "Meta, 직원 키스트로크로 AI 학습" 이 있으면, 오늘의 TechCrunch 후속 기사도 제외.
  - 예: 그제 올라온 GitHub 트렌딩 repo(`owner/repo-name`)가 오늘도 트렌딩에 올라왔으면 제외.
- **새로운 각도**는 유지: 같은 사건이라도 **후속 전개**(유출·규제·인수 가격 변경 등 명확한 업데이트)가 있으면 새 기사로 유지한다.

해당 파일이 존재하지 않으면(최근 3일 중 일부 누락) 존재하는 것만 기준으로 한다.

### 4. 한국어 번역/요약 생성

선별된 각 기사에 대해:

- **title_ko**: 한국어 제목
  - 회사/모델명(Claude, GPT, LLaMA 등)은 영문 유지
  - 기술 용어(LLM, RAG, LoRA 등)는 영문 유지
  - GitHub repo 이름은 원문 그대로 유지 (예: "owner / repo-name")
- **summary_ko**: 한국어 요약 1-2문장
  - 기사의 핵심 내용을 간결하게 전달
  - 없는 정보를 만들어내지 않음
  - `content`가 비어있으면 `title`과 `summary`만으로 작성

### 5. 최종 JSON 저장

기존 output 스키마와 동일한 형식으로 저장:

```json
{
  "date": "YYYY-MM-DD",
  "crawled_at": "원본 raw.json의 crawled_at 유지",
  "stats": {
    "total_raw": "원본 유지",
    "after_filter": "원본 유지",
    "after_dedup": "선별된 기사 수"
  },
  "articles": [
    {
      "title": "원본",
      "title_ko": "한국어 제목",
      "url": "원본",
      "source_type": "원본",
      "source_name": "원본",
      "published_at": "원본",
      "score": "원본",
      "comments": "원본",
      "summary": "원본",
      "summary_ko": "한국어 요약",
      "tags": "원본",
      "content": "원본",
      "importance_score": "평가 점수"
    }
  ]
}
```

**중요**: 필드 순서를 기존 output과 동일하게 유지한다:
`title` → `title_ko` → `url` → `source_type` → `source_name` → `published_at` → `score` → `comments` → `summary` → `summary_ko` → `tags` → `content` → `importance_score`

저장 경로: `output/YYYY-MM-DD.json` (raw.json의 날짜 사용)

### 6. Git commit & push

반드시 `main` 브랜치에서 직접 작업한다. 리포지토리 루트는 자동 감지되므로 절대 경로를 하드코딩하지 않는다.

```bash
git checkout main
git pull --rebase origin main
git add output/YYYY-MM-DD.json
git commit -m "evaluate: YYYY-MM-DD"
git push origin main
```

## 실행 예시

```
/ai-clipping-agent
```

또는 스케줄 작업으로 자동 실행됨.

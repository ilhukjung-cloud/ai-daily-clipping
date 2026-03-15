# AI Daily Clipping - LLM 포맷팅 프롬프트

아래 JSON 데이터를 기반으로 AI 데일리 클리핑을 작성해주세요.

## 규칙

1. **JSON에 있는 정보만 사용** — 새로운 내용을 추가하거나 해석하지 마세요
2. **원본 제목 유지** — 번역하지 말고 원문 그대로 사용
3. **URL은 JSON의 url 필드를 그대로 사용**
4. **source_type 기준으로 섹션을 나누세요:**
   - 🏢 공식 발표 (official)
   - 📰 미디어 보도 (media)
   - 📄 연구 논문 (research)
   - 💬 커뮤니티 화제 (community)
   - 🚀 새 제품/도구 (product)
5. **각 항목 형식:**
   ```
   - **[제목](URL)** — 1줄 요약 (source_name)
     ↳ 📊 score | 💬 comments
   ```
6. **score/comments가 None이면 해당 줄 생략**
7. **상단에 날짜와 총 기사 수 표시**
8. **각 섹션 내에서 score 높은 순으로 정렬**

## 출력 예시

```markdown
# 🤖 AI Daily Clipping — 2026-03-15

> 총 45건의 AI 소식을 수집했습니다.

## 🏢 공식 발표

- **[Introducing GPT-5](https://openai.com/blog/gpt-5)** — OpenAI의 차세대 모델 발표 (OpenAI Blog)
  ↳ 📊 2,341 | 💬 892

## 📰 미디어 보도

- **[OpenAI launches GPT-5 with reasoning capabilities](https://techcrunch.com/...)** — GPT-5 출시 보도 (TechCrunch AI)

## 📄 연구 논문

- **[Attention Is Still All You Need](https://arxiv.org/abs/...)** — 트랜스포머 아키텍처 개선 연구 (arXiv)

## 💬 커뮤니티 화제

- **[GPT-5 first impressions thread](https://reddit.com/...)** — 사용자 첫 인상 정리 (r/OpenAI)
  ↳ 📊 1,205 | 💬 432
```

## 입력 JSON

{여기에 output/YYYY-MM-DD.json 내용을 붙여넣기}

# Korean Translation Prompt for Claude Code

아래 프롬프트를 Claude Code에서 실행하면 당일 JSON 파일의 한국어 번역을 수행합니다.

---

## Prompt

```
Update exactly one JSON file at TARGET_JSON by filling Korean-localized fields for news articles.

TARGET_JSON은 output/ 디렉토리에서 오늘 날짜(YYYY-MM-DD.json)에 해당하는 파일이다.
만약 오늘 날짜 파일이 없으면 가장 최근 날짜 파일을 사용한다.

Target file rules:
- The file is a UTF-8 JSON file with this top-level structure:
  - date
  - crawled_at
  - stats
  - articles: array
- Each article may contain:
  - title
  - title_ko
  - url
  - source_name
  - source_type
  - published_at
  - summary
  - summary_ko
  - tags
  - content

Your job:
1. Open TARGET_JSON.
2. Parse the JSON safely.
3. For every article in articles:
   a. 반드시 해당 기사의 content 필드를 먼저 읽고 전체 맥락을 파악한다.
   b. content가 있으면 content를 기반으로 번역한다. summary만 보고 번역하지 않는다.
   c. content가 없으면 title + summary를 기반으로 번역한다.
   d. summary가 null이고 content가 있으면, content를 읽고 summary_ko를 직접 작성한다.
   e. summary가 null이고 content도 없거나 의미 없는 내용(보안 챌린지 페이지 등)이면 summary_ko를 null로 둔다.
   f. Fill or update title_ko with a natural Korean translation of title.
   g. Fill or update summary_ko with a natural Korean summary based on content (preferred) or summary.
   h. Keep title, summary, url, source_name, source_type, published_at, tags, content unchanged.
4. Edit tool을 사용해 JSON 파일을 직접 수정한다. Python 스크립트로 파일을 재생성하지 않는다.
5. 각 기사의 url을 앵커로 사용해 title_ko를 url 바로 앞에 삽입하고,
   tags 배열 바로 앞에 summary_ko를 삽입한다.
6. Do not invent facts, details, numbers, quotes, or claims not present in the source.
7. Keep proper nouns, company names, product names, model names, and technical terms in original form.
8. Do not translate URLs, timestamps, source names, or tags.
9. Do not add or remove articles.
10. Do not change the top-level schema.
11. Validate that the final file is valid JSON.

Style rules for translation:
- title_ko:
  - concise headline style
  - content의 핵심 내용을 반영한 제목
  - no sensational wording
  - no unnecessary honorifics
- summary_ko:
  - 2 to 3 natural Korean sentences
  - content에서 파악한 핵심 정보(수치, 인명, 기업명, 기술적 세부사항) 반드시 포함
  - preserve the meaning and emphasis of the original
  - avoid over-translation and repetition
  - "[…]"로 잘린 summary를 그대로 번역하지 말고, content에서 완전한 정보를 가져온다

Operational rules:
- Non-interactive: do not ask questions.
- If TARGET_JSON does not exist, exit with a short failure message.
- If the file is invalid JSON, exit with a short failure message.
- Make the smallest necessary edit — only add title_ko and summary_ko lines.
- Do not touch unrelated files.
- main 브랜치에서 직접 작업하고, 완료 후 커밋·푸시한다.

Output:
At the end, print only a short execution summary in plain text:
- file path
- number of articles processed
- number of title_ko updated
- number of summary_ko updated
- whether JSON validation passed
```

# Scheduled Task: AI Clipping Agent

GitHub Actions의 `daily-crawl.yml` 워크플로우가 UTC 22:00 에 돌아
`output/YYYY-MM-DD.raw.json`을 커밋한다. 본 스케줄 태스크는 그 뒤에
실행되어 평가/번역/요약 후 최종 `output/YYYY-MM-DD.json`을 푸시한다.

## 등록 방법 (Claude Code Web UI 에서 직접 등록)

Claude Code for Web → Scheduled Tasks 메뉴에서 아래 값으로 새 태스크를
생성한다. (이 저장소에는 MCP 기반 자동 등록 수단이 없으므로 수동 등록)

| 항목              | 값                                                         |
| ----------------- | ---------------------------------------------------------- |
| taskId            | `ai-clipping-evaluate`                                     |
| cronExpression    | `45 22 * * *`   # UTC 22:45 (KST 07:45)                    |
| timezone          | UTC                                                        |
| repository        | `ilhukjung-cloud/ai-daily-clipping`                        |
| branch            | `main`                                                     |
| description       | Evaluate raw.json, translate to Korean, push final JSON    |
| prompt            | 아래 "프롬프트" 블록의 내용을 그대로 사용                  |

크론 시각 근거:
- `daily-crawl.yml`은 UTC 22:00 크론이지만 GitHub Actions 큐잉 지연이
  5~20분 정도 발생하므로, 평가 태스크는 **22:45 UTC** 로 여유를 둔다.
- 만약 크롤이 더 늦게 끝나는 날이 있으면 태스크 내부에서 "raw.json 없음"
  으로 조기 종료되므로 안전하다. (수동 재실행 또는 다음날 집계)

## 프롬프트

> 태스크 실행 시 아래 내용을 그대로 프롬프트로 전달한다.
> 절대 경로를 쓰지 않는다 — 실행 환경의 repo 루트에서 바로 동작한다.

```
AI Daily Clipping 평가 태스크를 실행합니다.

## 전제
- 현재 작업 디렉토리가 ai-daily-clipping 리포지토리 루트라고 가정.
- 대상 브랜치: main (반드시 main 에서 직접 작업)

## 절차
1. `git fetch origin main` → `git checkout main` → `git pull --rebase origin main`
   (네트워크 오류 시 지수 백오프 2s/4s/8s/16s 로 최대 4회 재시도)
2. 오늘 UTC 날짜 확인: `date -u +%Y-%m-%d`
3. `output/{오늘날짜}.raw.json` 존재 여부 확인
   - 없으면 "오늘 날짜 raw.json 파일 없음" 출력 후 **즉시 종료**
   - 다른 날짜 raw.json 을 대체 선택하지 않음
4. `output/{오늘날짜}.json` 이 이미 존재하면 중복 실행이므로 종료
5. `/ai-clipping-agent` 스킬 실행으로 평가·번역·최종 JSON 생성
6. 결과 커밋 & 푸시:
   - `git add output/{오늘날짜}.json`
   - `git commit -m "evaluate: {오늘날짜}"`
   - `git push origin main` (push 실패 시 2s/4s/8s/16s 재시도)

## 규칙
- Non-interactive: 어떤 질문도 하지 않는다
- raw.json 외의 파일은 건드리지 않는다
- 실패 시 짧은 원인 메시지만 남기고 종료
```

## 수동 트리거

필요 시 Claude Code 에서 `/ai-clipping-agent` 스킬을 직접 호출하면
동일한 평가/번역/푸시 파이프라인이 돈다.

# Scheduled Task: AI Clipping Agent

## 등록 방법 (메인 브랜치에서)

```
mcp__scheduled-tasks__create_scheduled_task:
  taskId: "ai-clipping-evaluate"
  cronExpression: "13 22 * * *"   # UTC 22:13 (KST 07:13, GitHub Actions 완료 후)
  description: "Evaluate raw.json and generate final Korean-translated output"
  prompt: (아래 내용)
```

## 프롬프트

```
AI Daily Clipping 에이전트 작업을 실행합니다.

1. /Users/jay/projects/ai-daily-clipping 디렉토리로 이동
2. git pull (최신 raw.json 가져오기)
3. output/ 디렉토리에서 오늘 날짜의 .raw.json 파일을 찾기
4. /ai-clipping-agent 스킬 실행하여 평가/번역/저장
5. 결과를 git commit & push

오늘 날짜의 raw.json이 없으면 "raw.json 파일 없음" 메시지를 남기고 종료.
```

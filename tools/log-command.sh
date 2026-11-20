#!/bin/bash
# 사용자 지시를 로그 파일에 기록한다
# user_prompt_submit hook 이 호출하며, stdin 으로 사용자 입력을 받는다

LOG_DIR="$HOME/ai-berkshire/logs"
LOG_FILE="$LOG_DIR/command-log.jsonl"
COUNTER_FILE="$LOG_DIR/.counter"

mkdir -p "$LOG_DIR"

# 사용자 입력 읽기
PROMPT=$(cat)

# 빈 입력은 건너뛴다
[ -z "$PROMPT" ] && exit 0

# 타임스탬프(초 단위)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 앞 200자만 잘라 기록한다(지나치게 긴 입력 방지)
PROMPT_SHORT=$(echo "$PROMPT" | head -c 200 | tr '\n' ' ' | tr '"' "'")

# 로그에 추가(JSONL 형식)
echo "{\"time\":\"$TIMESTAMP\",\"prompt\":\"$PROMPT_SHORT\"}" >> "$LOG_FILE"

# 카운터
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE")
else
    COUNT=0
fi
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

# 10건마다 알림 출력(hook 의 stdout 은 Claude 에게 표시된다)
if [ $((COUNT % 10)) -eq 0 ]; then
    TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')
    echo "[지시 로그] 지금까지 지시 ${TOTAL}건을 기록했습니다. /command-log 를 실행해 최근 지시의 배경 요약을 보완하세요."
fi

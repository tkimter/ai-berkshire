# AI Berkshire Codex 가이드

이 저장소에는 투자 리서치 workflow, 보고서, 공용 검증 도구가 들어 있다. Claude Code 사용자와 Codex 사용자 모두와의 호환성을 유지한다.

이 저장소는 `xbtlin/ai-berkshire`(중국어 원본)를 포크해 한국어 기준으로 바꾼 것이다.

## 언어

- 사용자에게 하는 모든 대답, 보고서 본문, 새로 만드는 파일명과 폴더명, 커밋 메시지는 한국어로 쓴다.
- 영어는 고유명사, 코드·명령어, 마땅한 번역어가 없는 기술 용어에만 단어 수준으로 쓴다.
- 중국어는 쓰지 않는다. 예외는 원문과 일치해야 하는 것(중국어 자료 검색어, 중국 데이터 출처 이름, 원문 인용, 이미 있는 중국어 경로)뿐이다.
- 세부 규칙은 `CLAUDE.md`를 따른다.

## 프로젝트 구조

- `skills/*.md`: Claude Code slash-command 원본 파일.
- `codex-skills/*/SKILL.md`: Codex skill 패키지. 대부분 `skills/*.md`에서 생성한다. Codex 전용 수작업 패키지(현재 `investment-memo-craft`)는 그 사실을 분명히 표시하고 같은 이름의 `skills/*.md` 원본이 없을 때만 허용한다.
- `codex-prompts/*.md`: slash-command 방식 진입점을 위해 생성한 Codex custom prompt. 호환 계층이며, skill을 우선한다.
- `tools/*.py`: 두 시스템이 함께 쓰는 재무 검증·데이터 도구.
- `reports/`: 연구 산출물. 도구나 skill을 바꾸면서 관련 없는 보고서를 고쳐 쓰지 않는다.
- `scripts/sync-codex-skills.py`: `skills/*.md`에서 Codex skill을 다시 생성한다.
- `scripts/install-codex-skills.sh` / `scripts/install-codex-skills.bat`: Codex skill을 로컬에 설치한다.
- `scripts/install-codex-prompts.sh` / `scripts/install-codex-prompts.bat`: 생성한 Codex slash prompt를 로컬에 설치한다.
- `scripts/install-claude-commands.sh` / `scripts/install-claude-commands.bat`: Claude Code command를 로컬에 설치한다.

## 호환성 규칙

- `skills/*.md`를 workflow의 정본으로 취급한다.
- `skills/`의 파일을 바꾼 뒤에는 다음을 실행한다:
  `python3 scripts/sync-codex-skills.py`
- slash prompt 호환이 필요하면 다음도 실행한다:
  `python3 scripts/sync-codex-prompts.py`
- 생성된 `codex-skills/*/SKILL.md`는 `skills/`의 해당 원본을 함께 고치지 않는 한 손으로 수정하지 않는다.
- `codex-skills/` 아래의 Codex 전용 수작업 패키지는 Codex 전용임을 분명히 표시하고, 그 workflow를 Claude Code에도 의도적으로 도입하는 경우가 아니면 같은 이름의 `skills/*.md` 파일을 만들지 않는다.
- 도구 경로는 문서에 적힌 체크아웃 경로와 호환되게 유지한다:
  `~/ai-berkshire/tools/...`
- Claude Code의 동작은 `CLAUDE.md`에, Codex의 동작은 이 `AGENTS.md`에 둔다.

## 리서치 품질 규칙

- 리서치를 시작하기 전에 `date` 명령을 실행해 오늘 날짜를 확인한다. 그 날짜를 "최신" 데이터(주가, 시가총액, 최근 공시)의 기준으로 삼고, 보고서 머리에 데이터 기준일을 적는다. 학습 데이터로 현재 날짜를 가정하지 않는다.
- skill이 검증을 요구하면 재무 데이터는 최소 2개의 독립 출처에서 가져온다.
- 시가총액, 밸류에이션, 출처 간 대조, 시나리오 분석에는 정밀 연산 도구를 쓴다:
  `python3 tools/financial_rigor.py ...`
- 생성한 리서치를 발행 가능한 것으로 다루기 전에 보고서 감사 도구를 쓴다:
  `python3 tools/report_audit.py ...`
- 신뢰도가 낮은 결론, 불완전한 데이터, 출처 공백은 분명히 표시한다.
- 보고서 파일명과 폴더 구조는 `CLAUDE.md`의 "보고서 파일명 규칙"을 따른다. 보고서를 추가한 뒤에는 `python3 tools/reports_index.py`로 색인을 갱신한다.
- 이 프로젝트는 학습과 연구를 위한 것이며 투자 조언이 아니다.

## 편집 규칙

- 작업이 명시적으로 요구하지 않는 한 기존 보고서 파일은 그대로 둔다.
- 변경 범위는 요청받은 skill, 도구, 스크립트, 문서로 한정한다.
- skill/도구 변경을 마치기 전에 관련 문법 검사나 생성 검사를 실행한다. 호환성 변경이면 다음을 실행한다:
  `python3 scripts/sync-codex-skills.py`
- 생성된 Codex 산출물이 최신인지 파일을 다시 쓰지 않고 확인하려면 다음을 실행한다:
  `python3 scripts/sync-codex-skills.py --check`
  slash prompt가 관련되면 다음도 실행한다:
  `python3 scripts/sync-codex-prompts.py --check`

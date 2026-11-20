# AI Berkshire — 프로젝트 지침

## 언어 (전역 규칙, 최우선)

- 사용자에게 하는 **모든 대답은 한국어**로 한다.
- 영어는 불가피한 경우(고유명사, 코드·명령어, 마땅한 번역어가 없는 기술 용어)에만 단어 수준으로 쓴다.
- 보고서 본문, 새로 만드는 **파일명과 폴더명**, 커밋 메시지도 모두 **한국어**로 쓴다.
- 중국어는 쓰지 않는다. 예외는 원문과 일치해야 하는 것뿐이다: 중국어 자료를 찾는 검색어, 중국 데이터 출처 이름(东方财富, 巨潮资讯 등), 출처 목록의 원제목, 처음 나오는 고유명사의 괄호 병기.
- 영어로 된 자료는 번역하지 않고 그대로 둔다.
- 연구 대상은 한국·미국 기업을 중심으로 한 해외 기업이다. 중국 단일 기업 보고서는 저장소에 두지 않는다.
- 위챗(WeChat)에는 발행하지 않는다. 발행용 글은 "게시글"이라고 부른다.

## 프로젝트 개요

Claude Code 기반 가치투자 리서치 Skill 모음. 4대 거장 프레임워크: 버핏, 멍거, 돤융핑, 리루.

이 저장소는 `xbtlin/ai-berkshire`(중국어 원본)를 포크해 한국어 기준으로 바꾼 것이다.

## 프로젝트 구조

```
skills/          — 리서치 Skill 정의(.md). ~/.claude/commands/ 에 복사해 쓴다
tools/           — 보조 도구 (financial_rigor.py 정밀 계산, twstock_data.py 대만 주식 FinMind 조회)
reports/         — 투자 연구 보고서 출력
assets/          — 이미지 등 정적 자원
```

`skills/*.md`를 고친 뒤에는 `python3 scripts/sync-codex-skills.py`로 `codex-skills/`를 다시 만든다(AGENTS.md 참고).

## 보고서 폴더 구조

모든 보고서는 **회사명**으로 폴더를 만들고, 그 회사의 보고서는 전부 해당 폴더에 넣는다.

```
reports/
├── AI산업연구/               — AI 산업 체인 전체 연구
│   ├── AI5층케이크-산업전체연구-20260605.md
│   └── AI5층케이크-게시글-20260605.md
├── 엔비디아/                 — 엔비디아의 모든 연구 보고서
│   ├── 엔비디아-research-20260408.md
│   ├── 엔비디아-earnings-2025Q4.md
│   ├── 엔비디아-management-20260409.md
│   └── 엔비디아-thesis.md
├── SK하이닉스/               — SK하이닉스의 모든 연구 보고서
├── 애플/                     — 애플의 모든 연구 보고서
├── 원전-industry-20260409.md  — 산업 보고서는 루트에 둔다
├── AI컴퓨팅-funnel-20260509.md — 퍼널 스크리닝 보고서는 루트에 둔다
├── AI-로테이션판단-20260509.md — 테마 단위 종합 판단 보고서는 루트에 둔다
├── portfolio-latest.md        — 포트폴리오 보고서는 루트에 둔다
└── 다수기업비교-checklist-20260408.md — 여러 기업을 다루는 보고서는 루트에 둔다
```

### 이름 규칙

- 회사명·산업명은 한국에서 통용되는 한국어 표기를 쓴다(엔비디아, 애플, 마이크로소프트, SK하이닉스). 통용 표기가 없으면 영문 사명을 쓴다.
- 파일명·폴더명에는 공백을 쓰지 않고 `-`로 잇는다.
- 기존 폴더 가운데 영문 이름(`Google`, `Meta`, `Tesla` 등)은 그대로 쓴다. 같은 회사의 폴더가 이미 있으면 새 폴더를 만들지 않고 그 폴더에 쓴다.

## 보고서 파일명 규칙

| Skill | 파일명 형식 | 예시 |
|------|---------|------|
| /investment-team | `{회사명}/` 폴더에 4개 관점 + 최종보고서 | `reports/엔비디아/최종보고서.md` |
| /investment-research | `{회사명}-research-{YYYYMMDD}.md` | `reports/엔비디아/엔비디아-research-20260408.md` |
| /investment-checklist | `{회사명}-checklist-{YYYYMMDD}.md` | `reports/엔비디아/엔비디아-checklist-20260408.md` |
| /industry-research | `{산업명}-industry-{YYYYMMDD}.md` (루트) | `reports/원전-industry-20260409.md` |
| /industry-funnel | `{산업명}-funnel-{YYYYMMDD}.md` (루트) | `reports/AI컴퓨팅-funnel-20260509.md` |
| /private-company-research | `{회사명}-private-{YYYYMMDD}.md` | `reports/SpaceX/SpaceX-private-20260408.md` |
| /earnings-review | `{회사명}-earnings-{기간}.md` | `reports/엔비디아/엔비디아-earnings-2025Q4.md` |
| /earnings-team | `{회사명}/` 폴더에 4대 거장 관점 + 연구초안 + 게시글 + 독자리뷰 | `reports/엔비디아/엔비디아-earnings-2025Q4.md` (게시글 최종본) |
| /thesis-tracker | `{회사명}-thesis.md` (장기 관리) | `reports/엔비디아/엔비디아-thesis.md` |
| /portfolio-review | `portfolio-latest.md` (루트, 계속 갱신) | `reports/portfolio-latest.md` |
| /management-deep-dive | `{회사명}-management-{YYYYMMDD}.md` | `reports/엔비디아/엔비디아-management-20260409.md` |

skill 정의에 적힌 저장 경로가 이 표와 다르면 이 표를 따른다.

## /investment-team 파일 구조

```
reports/{회사명}/
├── README.md                              — 연구 프레임 개요 + 핵심 결론
├── 01-비즈니스모델분석-돤융핑관점.md
├── 02-재무밸류에이션분석-버핏관점.md
├── 03-산업경쟁분석-멍거관점.md
├── 04-리스크경영진평가-리루관점.md
└── 최종보고서.md                          — Team Lead 종합 보고서
```

## 투자 분석 핵심 원칙 (최우선)

- **객관, 객관, 객관** — 모든 분석은 사실과 데이터에 근거한다. 주관적 억측은 엄격히 금지한다
- "사실"과 "의견"을 엄격히 구분한다. 사실은 데이터로 뒷받침하고, 의견은 반드시 "의견" 또는 "추정"이라고 표시한다
- **입장을 미리 정하지 않는다**: 매수 관점도 매도 관점도 미리 정하지 않는다. 데이터를 먼저 놓고, 논리를 전개한 뒤, 결론을 낸다. 결론은 데이터에서 자연스럽게 나와야 한다
- "~라고 생각한다", "~인 것 같다", "분명히" 같은 주관적 표현을 쓰지 않는다. "데이터에 따르면", "증거가 보여 주는 바로는", "XX 출처에 따르면"으로 쓴다
- **양면을 모두 제시한다**: 핵심 판단마다 반대 논거("다만 한편으로는...")를 붙여 독자가 직접 저울질하게 한다
- 불확실한 것은 "불확실하다", "데이터가 부족하다"고 정직하게 쓴다. 추측으로 확실성을 채우지 않는다
- 모든 skill(investment-team, investment-research, earnings-review 등)은 실행할 때 위 원칙을 지킨다

## 보고서 언어와 문체

- 모든 보고서는 **한국어**로 쓴다
- 문체: 직설적이고 날카롭게, 군더더기 없이
- 데이터에는 출처를 표시하고, 핵심 데이터는 최소 2개 출처로 교차검증한다
- 추정치에는 반드시 "추정"이라고 표시한다
- 평점은 ★ 기호(★1~5)를 쓰고 반 개는 쓰지 않는다
- 버핏/멍거/돤융핑/리루의 어록 논평을 사이사이 넣는다(한국어로 옮겨 싣는다)

## GitHub 작업

- 로컬 클론 경로: `~/ai-berkshire/`
- `origin`: 내 포크 `https://github.com/tkimter/ai-berkshire.git` — 푸시는 여기로만 한다
- `upstream`: 원본 `https://github.com/xbtlin/ai-berkshire.git` — 읽기 전용. 푸시하지 않는다
- 푸시 전에 `git pull --rebase origin main`
- 원본의 변경은 통째로 병합하지 않는다(파일명·언어가 달라 충돌한다). `git fetch upstream` 뒤 필요한 변경만 골라 한국어로 옮겨 반영한다
- 커밋 메시지는 한국어로, 무엇을 바꿨는지 분명히 쓴다
- 중간 과정 파일(예: data_collection.md)은 푸시하지 않고 최종 보고서만 푸시한다

## 자주 쓰는 명령

```bash
# 보고서를 GitHub에 푸시
cd ~/ai-berkshire
git add reports/xxx.md                  # 새 보고서를 먼저 스테이징 (색인은 스테이징된 파일만 싣는다)
python3 tools/reports_index.py          # 연구 색인 갱신 (필수)
git add reports/README.md reports/index.json README.md
git commit -m "xxx 보고서 추가"
git pull --rebase origin main
git push origin main
```

```bash
# 색인이 오래됐는지만 확인하고 파일은 쓰지 않는다
python3 tools/reports_index.py --check
```

## 주의 사항

- 시가총액은 반드시 손으로 검산한다: 주가 × 총주식수를 보고서의 시가총액과 대조한다
- 통화 단위를 분명히 쓴다(홍콩달러/위안화/달러/대만달러/원). 혼동을 막는다
- PE/ROE 등 지표는 tools/financial_rigor.py로 정밀 계산한다
- 대만 주식 데이터는 tools/twstock_data.py(FinMind)로 가져오고, skills/financial-data.md의 대만 주식 장에 따라 교차검증한다
- 보고서를 다 쓰면 GitHub에 푸시할지 먼저 묻는다
- **푸시 전에 반드시 `python3 tools/reports_index.py`로 색인을 갱신한다.** 하지 않으면 색인 검사(`--check`)가 실패한다
- 새 보고서는 파일명에 `-YYYYMMDD` 접미를 붙이고 본문 첫 줄을 `# 제목`으로 쓰면 색인이 자동으로 인식한다.
  덮어써야 하면 파일 맨 앞에 YAML front-matter(`title` / `date` / `type`)를 넣는다.
  규칙은 `reports/_index/README.md`에 있다
- 새로 만든 **테마 폴더나 스크리닝 풀 폴더**는 `reports/_index/config.json`에 등록한다. 빠뜨리면 기업으로 처리된다

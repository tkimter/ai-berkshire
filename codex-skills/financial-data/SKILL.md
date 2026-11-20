---
name: financial-data
description: "AI Berkshire skill: 재무 데이터 취득 및 교차검증 규범. Source: skills/financial-data.md."
---

## Codex adapter note

This skill is generated from `skills/financial-data.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 재무 데이터 취득 및 교차검증 규범

본 규범은 기업 재무 데이터가 관련된 모든 연구에 적용한다. **핵심 데이터는 모두 두 개의 독립된 출처에서 가져와야 하며, 오차>1%이면 반드시 표시한다.**

---

## 데이터 출처 우선순위

### 미국 주식(PDD, 텐센트 ADR, 넷이즈 ADR 등)

| 우선순위 | 출처 | URL | 취득 방식 |
|--------|------|-----|---------|
| 1(주) | **macrotrends** | macrotrends.net/stocks/charts/{ticker} | 직접 접속, 가입 불필요 |
| 2(부) | **stockanalysis** | stockanalysis.com/stocks/{ticker}/financials | 직접 접속, 가입 불필요 |
| 원본 1차 자료 | SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 10-K / 10-Q 원문 |

### 홍콩 주식(텐센트 0700, 넷이즈 9999, 메이퇀 3690 등)

| 우선순위 | 출처 | URL | 취득 방식 |
|--------|------|-----|---------|
| 1(주) | **aastocks** | aastocks.com/tc/stocks/analysis/company-fundamental | 직접 접속 |
| 2(부) | **macrotrends**(ADR 코드) | 텐센트는 TCEHY, 넷이즈는 NTES | 직접 접속 |
| 원본 1차 자료 | HKEX披露易(HKEXnews 공시 사이트) | hkexnews.hk | 연간 보고서 PDF |

### A주(싼치후위(三七互娱), 지비터(吉比特) 등)

| 우선순위 | 출처 | URL | 취득 방식 |
|--------|------|-----|---------|
| 1(주) | **东方财富**(둥팡차이푸) | eastmoney.com → 종목 코드 검색 → 财务报表(재무제표) | 직접 접속 |
| 2(부) | **巨潮资讯**(쥐차오쯔쉰) | cninfo.com.cn | 연간/분기 보고서 원본 PDF |

### 대만 주식(TSMC(台積電) 2330, 미디어텍(聯發科) 2454, 라간정밀(大立光) 3008 등)

| 우선순위 | 출처 | URL | 취득 방식 |
|--------|------|-----|---------|
| 1(주) | **FinMind API** | api.finmindtrade.com | `tools/twstock_data.py`(의존성 없는 스크립트, 아래 참조) |
| 2(부) | **Goodinfo台湾股市资讯网**(Goodinfo 대만 주식시장 정보망) | goodinfo.tw/tw/StockDetail.asp?STOCK_ID={코드} | 직접 접속 |
| 원본 1차 자료 | 公开资讯观测站(공개정보관측소, MOPS) | mops.twse.com.tw | 재무보고서 원문/월 매출 공시 |

**FinMind 데이터 취득 도구**(대만 주식을 분석할 때 우선 호출한다. 출력에 시가총액 검산이 포함된다):

```bash
python3 tools/twstock_data.py quote 2330        # 최신 시세 + PER/PBR/배당수익률 + 시가총액 검산
python3 tools/twstock_data.py valuation 2330    # 밸류에이션 지표 + PER 1년 구간 + 52주 고저
python3 tools/twstock_data.py financials 2330   # 최근 5년 연간 핵심 재무(매출/매출총이익률/지배주주 순이익/EPS/ROE)
python3 tools/twstock_data.py revenue 2330      # 최근 13개월 월 매출 및 전년 동기 대비
python3 tools/twstock_data.py dividend 2330     # 최근 수년 배당 정책(현금/주식 배당, 배당락일)
python3 tools/twstock_data.py search 台積        # 종목 코드 검색(대만 주식 종목명은 번체자임에 유의)
```

대만 주식 특별 유의사항:

1. **통화 단위는 대만달러(TWD)다**. 홍콩달러/위안화/미국달러와 섞어 쓸 때는 반드시 명시적으로 표기하고, 시장 간 비교는 먼저 통일 환산한다
2. **월 매출은 대만 주식만의 강점이다**: 상장·장외(上市柜) 회사는 매월 10일 이전에 전월 매출을 의무 공시하며, 이는 펀더멘털 변곡점을 추적하는 가장 빠른 공개 신호다. earnings-review/thesis-tracker 류의 분석은 이를 우선 활용한다(`revenue` 하위 명령)
3. FinMind 손익계산서는 **단일 분기 값**이며, 도구가 자동으로 연간 값으로 합산한다. 4개 분기가 안 되는 연도는 "(앞 N개 분기 누계만, 연간 아님)"으로 표기된다
4. FinMind는 가입하지 않아도 바로 쓸 수 있다(시간 단위 한도가 있다). 가입 후의 API token은 **로컬 기기에만 저장하고, git에 제출하는 것을 엄금한다**. 도구는 다음 우선순위로 자동으로 읽는다: ①환경 변수 `FINMIND_TOKEN`; ②로컬 파일 `local/finmind_token.txt`(`local/` 은 `.gitignore` 로 영구 제외되어 있으므로, token을 한 줄로 이 파일에 써 넣으면 된다). token은 보고서, skill, commit에 나타나서는 안 된다
5. 교차검증: FinMind 수치를 Goodinfo(또는 macrotrends의 ADR, 예: TSM)와 대조하며, 오차 규칙은 아래와 같다. TSMC처럼 ADR이 있는 회사는 ADR과 대만 원주의 환율/예탁 비율 차이에 유의한다(1 TSM ADR = 2330 5주)

---

## 실행 규범

### 1단계: 데이터 취득

재무 지표(매출, 순이익, 매출총이익률, 영업현금흐름, 부채비율 등)마다 **출처 1**과 **출처 2**에서 각각 수치를 가져온다.

### 2단계: 오차 계산과 표시

```
오차율 = |출처 1 수치 - 출처 2 수치| / 출처 1 수치 × 100%
```

| 오차 | 처리 방식 |
|------|---------|
| ≤ 1% | ✅ 일치. 출처 1 수치를 쓰고 두 출처를 표기한다 |
| 1% ~ 5% | ⚠️ "데이터에 차이 있음"으로 표시하고, 두 수치를 적고, 가능한 원인(환율/회계 기준)을 설명한다 |
| > 5% | ❌ "데이터에 중대한 차이 있음"으로 표시하고, 반드시 원본 재무보고서를 확인한다. 그대로 사용해서는 안 된다 |

### 3단계: 데이터 제시 형식

핵심 데이터는 모두 다음 형식으로 표기한다:

```
매출: 1,239억 위안 ✅
  - macrotrends: 1,241억 위안
  - stockanalysis: 1,237억 위안
  - 오차: 0.3%
```

차이 예시:
```
순이익: 245억 위안 ⚠️ 데이터에 차이 있음
  - macrotrends: 245억 위안(GAAP)
  - stockanalysis: 278억 위안(Non-GAAP)
  - 오차: 13.5% — 원인: 회계 기준이 다름(GAAP vs Non-GAAP)
```

---

## 흔한 차이 원인(반드시 데이터 오류인 것은 아니다)

| 원인 | 설명 |
|------|------|
| GAAP vs Non-GAAP | 가장 흔하며, 특히 이익류 데이터에서 그렇다 |
| 환율 환산 | 홍콩달러/위안화/미국달러 환산 시점이 다름 |
| 회계연도 정의 | 역년 vs 회계연도(예: 애플의 회계연도는 10월에 끝난다) |
| 연결 기준 | 비지배지분 포함 여부 |
| 데이터 갱신 지연 | 어떤 플랫폼이 최신 분기 재무보고서를 아직 반영하지 않음 |

---

## 특별 규칙

1. **비상장 회사**(미호요, 릴리스게임즈 등): 1차 데이터 출처가 하나뿐일 때는 데이터 앞에 `[추정]` 을 표시하고, 교차검증을 수행하지 않는다
2. **분기 데이터 vs 연간 데이터**: 교차검증에는 연간 데이터를 우선 사용한다. 분기 데이터는 일부 출처에서 지연될 수 있다
3. **원본 재무보고서 우선**: 두 출처가 모두 원본 재무보고서(10-K/연간 보고서 PDF)와 맞지 않으면 원본 재무보고서를 기준으로 하고, 출처 오류로 표시한다

---

## 주가와 수정주가(과거 시계열 필독)

가격에는 세 가지 기준이 있으며, 섞어 쓰면 과거 주가 위치, 장기 상승률, 과거 밸류에이션 분위수가 모두 왜곡된다:

| 기준 | 의미 | 용도 |
|------|------|------|
| 무수정(不复权) | 실제 체결가. 권리락·배당락일에 갭 발생 | "현재 시점" 스냅샷에만 사용 |
| 전방 수정(前复权) | 최신 가격을 기준으로 과거 가격을 조정 | 과거 주가 비교, N년 상승률, 과거 PE band에는 일률적으로 이것을 쓴다 |
| 후방 수정(后复权) | 상장 첫날을 기준으로 이후 가격을 조정 | 과거 총수익/연환산 수익률 계산 |

규칙:

1. 과거 가격이 관련된 분석은 **전방 수정(前复权)**으로 통일하며, 한 분석 안에서 수정주가 출처와 무수정 출처를 **섞어 쓰지 않는다**.
2. 현재 시가총액/현재 PE는 **현재 실제 주가 × 현재 총주식수**를 쓰면 되며, 수정주가와 무관하다——수정주가는 과거 시계열에만 영향을 준다.
3. 주식분할/대규모 무상증자를 사이에 둔 주당 지표(과거 EPS, 과거 주가)는 반드시 수정주가로 환원한 뒤 전년 동기 대비를 계산한다.
4. 총수익/연환산 수익률에는 배당을 포함해야 한다(후방 수정에는 이미 포함되어 있다). 가격 상승률만 보면 과소평가된다.
5. 증자/자사주 매입 후의 시가총액 검산은 최신 총주식수를 기준으로 한다(`financial_rigor.py verify-market-cap` 은 편차>5%이면 확인하라고 알린다).

---

## 빠른 색인

| 상황 | 주요 출처 | 예비 출처 |
|------|---------|---------|
| PDD / 핀둬둬 | macrotrends.net/stocks/charts/PDD | stockanalysis.com/stocks/pdd |
| 텐센트 | macrotrends.net/stocks/charts/TCEHY | aastocks(0700.HK) |
| 넷이즈 | macrotrends.net/stocks/charts/NTES | aastocks(9999.HK) |
| 싼치후위(三七互娱) | eastmoney.com(002555) | cninfo.com.cn |
| 지비터(吉比特) | eastmoney.com(603444) | cninfo.com.cn |
| Nintendo | macrotrends.net/stocks/charts/NTDOY | stockanalysis.com/stocks/ntdoy |
| Capcom | macrotrends(CCOEY) | stockanalysis(CCOEY) |
| TSMC(台積電) | tools/twstock_data.py(2330) | goodinfo.tw / macrotrends(TSM, 1 ADR=5주에 유의) |
| 미디어텍(聯發科) | tools/twstock_data.py(2454) | goodinfo.tw |

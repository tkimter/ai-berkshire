# OpenRouter 모델 사용량 다차원 분해: 가격 정규화 전후의 실제 순위

> 데이터 스냅샷: 2026년 6월 23일 | 분석 일자: 2026년 7월 2일

## 핵심 질문

OpenRouter의 모델 사용량 순위는 모델이 실제로 얼마나 쓸 만한지를 반영하는가? 답은 **그대로 쓸 수 없다**는 것이다. 원시 token 사용량은 사실상 가격의 역수다. 싼 모델은 태생적으로 불균형하게 많은 트래픽을 얻는다. 본문은 다차원 분석과 가격 정규화를 통해 "실제 사용 만족도"에 더 가까운 순위를 복원하려 한다.

## 데이터 출처

- **CodeSOTA Agent Leaderboard**(주 데이터 출처): 46개 Agent 애플리케이션의 30일 사용 데이터를 포괄하며, token 양, 지출, 채택 app 수, #1 slot 수를 함께 제공한다
- **DigitalApplied** April/June 2026 보고서: 주간 token 양, 시장 점유율
- **OpenRouter 공식 블로그**: 오픈소스 모델 벤치마크, 가격, 처리량
- **AICost**: 월간 token 순위, 중국 모델 분석

## 방법론

### 다섯 가지 차원

| 차원 | 가중치 | 의미 | 노이즈 특징 |
|------|:----:|------|----------|
| 매출(Revenue) | 30% | 돈으로 투표 — 개발자가 이 모델에 얼마를 쓸 의향이 있는가 | 자금력 있는 기업 사용자 쪽으로 치우친다 |
| 채택 폭(Apps) | 25% | 얼마나 많은 서로 다른 애플리케이션이 이 모델을 통합했는가 | 가격의 영향을 가장 덜 받는다 |
| 사용량(Tokens) | 20% | 원시 token 처리량 | 가격 노이즈가 가장 크다 |
| 품질 선두(#1 Slots) | 15% | 몇 개의 애플리케이션에서 1순위 모델로 선택되었는가 | 표본은 작지만 신호가 강하다 |
| 개발자당 지불액 | 10% | Revenue/Apps — 개발자 한 명이 얼마를 쓸 의향이 있는가 | "싸니까 쓴다"는 노이즈를 걸러낸다 |

### 왜 "token/가격"으로 정규화하지 않는가

"1달러당 처리하는 token 수"는 본질적으로 가격의 역수이므로 추가 정보를 주지 못한다. 진정으로 의미 있는 가격 정규화 방법은 **가격 요인을 통제한 뒤에도 개발자의 행동이 여전히 이 모델을 가리키는가**를 보는 것이다. 즉 매출, 채택 폭, #1 slots 같은 차원이다.

---

## 종합 순위 Top 20

| 순위 | 모델 | 공급사 | 종합 점수 | 매출 | 사용량 | 채택 | #1 | 유효 가격 |
|:----:|------|--------|:-----:|:----:|:-----:|:----:|:---:|:--------:|
| 1 | Claude Sonnet 4.6 | Anthropic | 96.4 | #1 | #3 | #3 | #2 | $6.35/M |
| 2 | MiniMax M3 | MiniMax | 86.2 | #6 | #2 | #4 | #6 | $0.55/M |
| 3 | DeepSeek V4 Pro | DeepSeek | 85.3 | #8 | #4 | #2 | #3 | $0.56/M |
| 4 | Claude Opus 4.8 | Anthropic | 84.8 | #2 | #7 | #8 | #8 | $10.60/M |
| 5 | DeepSeek V4 Flash | DeepSeek | 78.6 | #13 | #1 | #1 | #1 | $0.12/M |
| 6 | Gemini 3.5 Flash | Google | 73.1 | #7 | #14 | #5 | #11 | $3.59/M |
| 7 | GPT-5.5 | OpenAI | 72.8 | #3 | #13 | #15 | #9 | $12.01/M |
| 8 | Claude Opus 4.6 | Anthropic | 71.9 | #5 | #17 | #9 | #10 | $10.60/M |
| 9 | Claude Opus 4.7 | Anthropic | 68.3 | #4 | #16 | #12 | #16 | $10.59/M |
| 10 | Gemini 3 Flash Preview | Google | 67.2 | #12 | #12 | #10 | #4 | $1.20/M |
| 11 | MiMo-V2.5-Pro | Xiaomi | 62.9 | #14 | #9 | #6 | #13 | $0.56/M |
| 12 | Step 3.7 Flash | StepFun | 61.4 | #9 | #5 | #27 | #7 | $0.47/M |
| 13 | Laguna M.1 | Poolside | 54.0 | #17 | #6 | #19 | #14 | $0.26/M |
| 14 | Kimi K2.6 | MoonshotAI | 48.8 | #15 | #18 | #13 | #18 | $1.43/M |
| 15 | GPT-5.3-Codex | OpenAI | 44.7 | #10 | #22 | #29 | #12 | $5.19/M |
| 16 | GLM 5.2 | Z.ai | 44.1 | #16 | #20 | #17 | #19 | $1.52/M |
| 17 | Gemini 3.1 Flash Lite | Google | 41.4 | #26 | #19 | #11 | #5 | $0.60/M |
| 18 | Nex-N2-Pro | Nex AGI | 39.0 | #20 | #11 | #22 | #22 | $0.46/M |
| 19 | Claude Fable 5 | Anthropic | 36.4 | #11 | #29 | #28 | #17 | $21.21/M |
| 20 | Claude Sonnet 4.5 | Anthropic | 35.9 | #18 | #26 | #18 | #20 | $6.36/M |

---

## 차원별 순위 비교

### 차원 1: 원시 사용량(Token Volume)

가격 노이즈가 가장 큰 차원이다. 상위 10개는 모두 $1/M 이하의 저가 모델이다(Claude Sonnet 4.6 제외).

| 순위 | 모델 | Token 양 | 유효 가격 |
|:----:|------|:--------:|:--------:|
| 1 | DeepSeek V4 Flash | 6,420B | $0.12/M |
| 2 | MiniMax M3 | 4,530B | $0.55/M |
| 3 | Claude Sonnet 4.6 | 3,290B | $6.35/M |
| 4 | DeepSeek V4 Pro | 2,880B | $0.56/M |
| 5 | Step 3.7 Flash | 2,880B | $0.47/M |
| 6 | Laguna M.1 | 2,130B | $0.26/M |
| 7 | Claude Opus 4.8 | 1,540B | $10.60/M |
| 8 | Nemotron 3 Super | 1,470B | $0.19/M |
| 9 | MiMo-V2.5-Pro | 1,270B | $0.56/M |
| 10 | MiMo-V2.5 | 857B | $0.18/M |

**Claude Sonnet 4.6은 높은 가격($6.35/M)으로 token 양 Top 3에 들어간 유일한 모델이다.** 이것 자체가 매우 강한 품질 신호다.

### 차원 2: 매출(Revenue = 돈으로 투표)

매출은 가장 강한 품질 신호다. 실제 돈을 쓸 의향이 있다는 것은 모델이 프로덕션 환경에서 대체 불가능하다는 뜻이다.

| 순위 | 모델 | 월 매출 | Token 양 |
|:----:|------|:------:|:--------:|
| 1 | Claude Sonnet 4.6 | $20.9M | 3,290B |
| 2 | Claude Opus 4.8 | $16.3M | 1,540B |
| 3 | GPT-5.5 | $7.9M | 661B |
| 4 | Claude Opus 4.7 | $5.9M | 554B |
| 5 | Claude Opus 4.6 | $5.7M | 536B |
| 6 | MiniMax M3 | $2.5M | 4,530B |
| 7 | Gemini 3.5 Flash | $2.2M | 599B |
| 8 | DeepSeek V4 Pro | $1.6M | 2,880B |
| 9 | Step 3.7 Flash | $1.3M | 2,880B |
| 10 | GPT-5.3-Codex | $1.3M | 247B |

**Anthropic이 상위 5개 중 4개를 차지하며, 월 매출 합계는 $50.1M으로 전체 시장의 66%다.** token 양은 약 15%에 불과한데도 그렇다.

### 차원 3: 개발자 채택 폭(Apps Count)

가격의 영향을 가장 덜 받는 차원이다. 개발자가 시간을 들여 모델을 통합하는 것은 단지 싸서만은 아니다.

| 순위 | 모델 | Apps 수 | 유효 가격 |
|:----:|------|:-------:|:--------:|
| 1 | DeepSeek V4 Flash | 36 | $0.12/M |
| 2 | DeepSeek V4 Pro | 34 | $0.56/M |
| 3 | Claude Sonnet 4.6 | 29 | $6.35/M |
| 4 | MiniMax M3 | 28 | $0.55/M |
| 5 | Gemini 3.5 Flash | 26 | $3.59/M |
| 6 | MiMo-V2.5-Pro | 26 | $0.56/M |
| 7 | MiMo-V2.5 | 25 | $0.18/M |
| 8 | Claude Opus 4.8 | 24 | $10.60/M |
| 9 | Claude Opus 4.6 | 21 | $10.60/M |
| 10 | Gemini 3 Flash Preview | 21 | $1.20/M |

**DeepSeek V4 Flash가 채택 폭에서 1위라는 것은 그 인기가 가격만으로 생긴 것이 아님을 보여준다.** 36개의 서로 다른 app이 통합을 선택했다. 개발자들이 발로 투표한 것이다.

### 차원 4: 품질 선두(#1 Slots)

몇 개의 애플리케이션에서 1순위 모델로 선택되었는가. 가장 순수한 품질 신호다.

| 순위 | 모델 | #1 수 | 총 채택 |
|:----:|------|:-----:|:------:|
| 1 | DeepSeek V4 Flash | 6 | 36 apps |
| 2 | Claude Sonnet 4.6 | 5 | 29 apps |
| 3 | DeepSeek V4 Pro | 3 | 34 apps |
| 4 | Gemini 3 Flash Preview | 3 | 21 apps |
| 5 | Gemini 3.1 Flash Lite | 3 | 21 apps |
| 6 | MiniMax M3 | 2 | 28 apps |
| 7 | Step 3.7 Flash | 2 | 7 apps |

**#1 slot을 하나라도 얻은 모델은 15개뿐이다.** 최소 한 가지 시나리오에서 최적의 선택이 된다는 것 자체가 높은 문턱이다.

### 차원 5: 개발자당 지불액(Revenue / App)

해당 모델을 통합한 개발자 한 명이 평균 얼마를 쓰는가. "무료라서 쓴다"는 노이즈를 걸러낸다.

| 순위 | 모델 | App당 매출 | Apps 수 |
|:----:|------|:----------:|:-------:|
| 1 | Claude Sonnet 4.6 | $721K | 29 |
| 2 | Claude Opus 4.8 | $680K | 24 |
| 3 | GPT-5.5 | $496K | 16 |
| 4 | Claude Opus 4.7 | $294K | 20 |
| 5 | Claude Opus 4.6 | $270K | 21 |
| 6 | GPT-5.3-Codex | $256K | 5 |
| 7 | Step 3.7 Flash | $191K | 7 |
| 8 | Claude Fable 5 | $149K | 6 |
| 9 | MiniMax M3 | $89K | 28 |
| 10 | Gemini 3.5 Flash | $83K | 26 |

**Claude Sonnet 4.6은 채택이 넓을 뿐 아니라(29 apps) app 하나당 평균 월 $721K를 쓴다.** 넓고도 깊다.

---

## 가격 정규화의 핵심 발견

"원시 token 순위"와 "종합 순위"의 격차를 비교하면 가격이 사용량 데이터를 얼마나 왜곡했는지 알 수 있다.

### 가격 때문에 부풀려진 모델

이 모델들은 token 사용량 순위가 종합 순위보다 훨씬 높다. 사용량이 품질이 아니라 주로 낮은 가격에 의해 만들어졌다는 뜻이다.

| 모델 | Token 순위 | 종합 순위 | 하락 | 유효 가격 | 진단 |
|------|:---------:|:-------:|:----:|:--------:|------|
| Nemotron 3 Super | #8 | #25 | ↓17 | $0.19/M | app 10개, #1은 0개. 순전히 싸서 대량 배치 작업에 쓰인다 |
| MiMo-V2.5 | #10 | #21 | ↓11 | $0.18/M | app 25개지만 #1은 0개. 아무도 가장 좋다고 보지 않는다 |
| MiniMax M2.7 | #15 | #24 | ↓9 | $0.44/M | M3로 대체된 뒤에도 기존 사용자의 관성에 기대고 있다 |
| Nemotron 3 Ultra | #21 | #29 | ↓8 | $0.98/M | benchmark는 괜찮지만(AA 48) 실제 채택은 매우 낮다 |
| Step 3.7 Flash | #5 | #12 | ↓7 | $0.47/M | app이 7개뿐, 사용이 극도로 집중되어 있다 |
| Laguna M.1 | #6 | #13 | ↓7 | $0.26/M | 2.13T token이지만 app은 12개뿐 |

### 가격 때문에 눌린 모델

이 모델들은 token 사용량 순위가 종합 순위보다 훨씬 낮다. 비싸서 사용량이 억제되었지만, 매출과 채택도는 품질이 실제로 좋다는 것을 보여준다.

| 모델 | Token 순위 | 종합 순위 | 상승 | 유효 가격 | 진단 |
|------|:---------:|:-------:|:----:|:--------:|------|
| Claude Fable 5 | #29 | #19 | ↑10 | $21.21/M | 전체에서 가장 비싸고 42B token이지만 월 매출 $891K |
| Claude Opus 4.6 | #17 | #8 | ↑9 | $10.60/M | app 21개가 $10.60/M에 계속 사용할 의향이 있다 |
| Gemini 3.5 Flash | #14 | #6 | ↑8 | $3.59/M | app 26개, 가격은 중간이지만 채택이 매우 넓다 |
| Claude Opus 4.7 | #16 | #9 | ↑7 | $10.59/M | app 20개, 월 매출 $5.87M |
| GPT-5.3-Codex | #22 | #15 | ↑7 | $5.19/M | app이 5개뿐이지만 월 매출 $1.28M, 극도로 버티컬하다 |
| GPT-5.5 | #13 | #7 | ↑6 | $12.01/M | 월 매출 $7.94M, 매출 3위 |

---

## 핵심 통찰

### 1. Token 사용량 ≈ 가격의 역수

DeepSeek V4 Flash는 6.42T token을 처리했지만(1위) 매출은 $739K에 불과하다(13위). Claude Sonnet 4.6의 token 양은 그 절반이지만 매출은 **28배**다. token 순위표만 보면 DeepSeek V4 Flash가 시장에서 가장 좋은 모델이라고 생각하게 된다. 그러나 이 모델은 그보다는 "쓸 만한 수준에서 가장 싼 모델"에 가깝다.

### 2. 매출은 가장 강하지만 편향이 있는 품질 신호다

Anthropic의 모델 6개가 월 매출 $50.1M(전체 시장의 66%)을 가져갔지만 token은 15%만 차지한다. 이는 기업 사용자가 실제로 Anthropic의 모델을 더 좋다고 보고, 그 대가로 10-20배의 가격 프리미엄을 지불할 의향이 있음을 보여준다. 그러나 이는 매출 순위가 "예산이 있는 기업이 무엇을 고르는가" 쪽으로 치우쳐 있다는 뜻이기도 하며, "최고의 가성비"를 대표하지는 않는다.

### 3. 채택 폭이 가장 깨끗한 신호다

개발자가 시간을 들여 모델 하나를 통합하는 비용은 가격을 갈아타는 비용보다 훨씬 크다. 이는 apps 수가 가격의 영향을 상대적으로 덜 받는다는 뜻이다. 이 차원에서 DeepSeek V4 Flash(36 apps)와 DeepSeek V4 Pro(34 apps)가 1, 2위이며, 이들의 인기가 가격 효과만은 아님을 보여준다.

### 4. 네 차원 모두에서 앞서야 "진짜 쓸 만한" 모델이다

- **Claude Sonnet 4.6**: 네 차원 모두 Top 3이며, 유일하다. 절대적 지배력.
- **MiniMax M3**, **DeepSeek V4 Pro**: 싸지만 채택과 선두 지표가 모두 강하다. 가격에만 기대는 것이 아니다.
- **GPT-5.5**: 매출 3위지만 채택은 app 16개뿐이며, 주로 소수의 고액 지불 사용자에 기댄다.

### 5. 중국 모델: token의 51%, 매출의 7%

중국 모델(MiniMax, DeepSeek, Xiaomi, Moonshot, Z.ai, Qwen)은 token 양에서 이미 절반을 넘었지만 매출 기여는 10분의 1에 못 미친다. 이 격차의 핵심 설명은 가격 전략이다. 중국 모델은 대체로 1/10에서 1/100의 가격으로 경쟁한다. 예외는 MiniMax M3로, 채택과 품질 선두 차원 모두에서 두드러지며 싸기만 한 것이 아니다.

### 6. 투자자에 대한 시사점

AI 모델/회사의 경쟁력을 평가하고 있다면:
- **token 사용량 순위표를 보지 마라** — 사실상 가격의 역수다
- **매출 + 채택 폭의 교차를 보라** — Claude Sonnet 4.6은 두 차원 모두 Top 3이며, 이것이 진짜 해자다
- **"가격 부풀림형" 모델에 주의하라** — Nemotron 3 Super의 token 양은 커 보이지만, 17계단 내려간 자리가 실제 위치다
- **가격 탄력성에 주목하라** — 모델이 가격을 올린 뒤 사용량이 급감하면 사용자 충성도가 낮다는 뜻이다. 유지된다면(Claude Opus 시리즈처럼) 전환 비용이 높다는 뜻이다

---

## 공급사 분포(Top 20)

| 공급사 | 모델 수 | 총 매출 | 총 Token | 평균 가격 |
|--------|:------:|:------:|:--------:|:--------:|
| Anthropic | 6 | $50.1M | 6.0T | $8.35/M |
| OpenAI | 2 | $9.2M | 0.9T | $10.22/M |
| Google | 3 | $3.2M | 1.7T | $1.88/M |
| MiniMax | 1 | $2.5M | 4.5T | $0.55/M |
| DeepSeek | 2 | $2.3M | 9.3T | $0.25/M |
| StepFun | 1 | $1.3M | 2.9T | $0.47/M |
| Xiaomi | 1 | $0.7M | 1.3T | $0.56/M |
| MoonshotAI | 1 | $0.6M | 0.5T | $1.43/M |
| Z.ai | 1 | $0.6M | 0.4T | $1.52/M |
| Poolside | 1 | $0.5M | 2.1T | $0.26/M |
| Nex AGI | 1 | $0.4M | 0.8T | $0.46/M |

---

## 데이터 출처

- [CodeSOTA Agent Leaderboard](https://www.codesota.com/agentic/openrouter-models)(주 데이터 출처, 46개 Agent 애플리케이션의 30일 스냅샷)
- [OpenRouter Rankings April 2026 - DigitalApplied](https://www.digitalapplied.com/blog/openrouter-rankings-april-2026-top-ai-models-data)
- [OpenRouter June 2026 Roundup - DigitalApplied](https://www.digitalapplied.com/blog/openrouter-new-models-june-2026-roundup-pricing-rankings)
- [OpenRouter: The Open Weight Models That Matter June 2026](https://openrouter.ai/blog/insights/the-open-weight-models-that-matter-june-2026/)
- [AICost: Chinese Models Dominate](https://aicost.org/blog/openrouter-monthly-token-usage-ranking-2026-chinese-models-dominate)
- [OpenRouter Data Page](https://openrouter.ai/data)

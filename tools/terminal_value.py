#!/usr/bin/env python3
"""종말가치 배수와 10년 IRR 추정 도구 (Terminal Value Toolkit for AI Berkshire).

「7개사 10년 투자가치 횡단 비교」 3절의 밸류에이션 프레임워크를 재사용 가능한 도구로 만든 것이다.
핵심은 영구성장 모형이다:

    PE(종말가치) = (1 - g/ROIC) / (r - g)

    분자 1 - g/ROIC  = 배당성향. g/ROIC 는 유보율이다. 매년 g 만큼 성장하려면, 유보한 1원이
                       ROIC 를 벌어들이므로 이익의 g/ROIC 를 남겨 재투자해야 하고, 나머지만
                       주주에게 돌려줄 수 있다.
    분모 r - g       = 영구연금의 분모. 요구수익률이 r 이고 대상이 스스로 g 만큼 자라므로
                       순차이는 r-g 다.

반드시 기억해야 할 세 가지 규율(모두 그 보고서가 실제로 빠졌던 함정에서 나왔다):

  1. r 과 g 는 같은 통화여야 한다. 명목 성장 3% 는 인플레이션 2.5% 인 미국에서는 실질 0.5%
     (보수적)이고, 인플레이션 1% 인 중국에서는 실질 2%(공격적)다. 같은 숫자라도 통화가
     바뀌면 의미가 바뀐다. 이 도구는 --g-shift 로 통화 환산을 명시적으로 표현하며,
     암묵적인 혼용을 허용하지 않는다.
  2. 분모 r-g 가 최소 5%포인트는 되어야 고든 모형이 의미를 갖는다. 5pct 미만에서는 g 가
     조금만 움직여도 밸류에이션이 뒤집힌다. 그것은 밸류에이션이 아니라 편향의 증폭이다.
     이 도구는 칸마다 점검해 명시적으로 경고한다.
  3. 이산 리스크(상장폐지/VIE 무효화/지정학적 공급 차단/규제 강타)는 r 이나 beta 에 넣을 수
     없다. r 을 3%포인트 올리면 10년차 현금흐름에 대한 벌점이 1년차의 2.6배가 되는데,
     상장폐지는 대체로 균등하거나 오히려 앞쪽에 몰린 연간 위험률이다. 할인율로 처리하면
     리스크의 시간 분포를 거꾸로 만든다. 올바른 방법은 테일 시나리오 구간을 따로 두는 것이다.

외부 의존성 없음. Python 표준 라이브러리만 사용한다. Python >= 3.7 필요.

사용법:

    # 단일 시점 엑시트 PE, 전체 산식 출력
    python3 tools/terminal_value.py pe --roic 0.20 --g 0.02 --r 0.06

    # 단일 회사 3개 구간 추정(내장 프리셋 사용)
    python3 tools/terminal_value.py company --name 텐센트 --r 0.06 --g-shift -0.01

    # 7개사 횡단 비교표 + 순위
    python3 tools/terminal_value.py table --r 0.06 --g-shift -0.01 --rf 0.017

    # 여러 r 구간 민감도 + 순위 안정성 검증
    python3 tools/terminal_value.py sweep --r 0.06,0.08,0.10,0.12 --g-shift -0.01 --rf 0.017

    # 단일 회사 r±2pp: 기대 IRR 이 자본비용을 감당하는가, 결론이 반전되는가
    # (비중 스트레스 테스트이지 매수 거부권이 아니다)
    # --currency 로 통화별 합리 구간을 지정한다. 구간 밖 구간은 참고용이며 반전 판정에 참여하지 않는다
    python3 tools/terminal_value.py flip --name 텐센트 --r 0.10 --delta 0.02 --currency HKD --g-shift -0.01

    # 프리셋에 없는 신규 회사: 인라인 파라미터(또는 같은 필드를 JSON 에 써서 --config 로 전달)
    python3 tools/terminal_value.py flip --name 어떤회사 --roic 0.18 --g 0.015,0.03,0.04 \
        --p 0.35,0.50,0.15 --irr10=-2.0,8.0,14.0 --k 0.01 --r 0.10 --currency USD

    # 분모 폭 점검(어느 칸이 5pct 유효성 하한 아래로 떨어지는가)
    python3 tools/terminal_value.py check --r 0.06 --g-shift -0.01

    # IRR 을 처음부터 계산(프리셋에 의존하지 않고 이익과 시가총액만 주면 된다)
    python3 tools/terminal_value.py irr --profit 5390 --mcap 34420 --pe 22.5 --years 10 --payout 0.015

    # 자체 회사 설정 사용
    python3 tools/terminal_value.py table --r 0.08 --config my_companies.json

    # --config 파일 형식(내장 PRESET 필드와 동일하며, k 는 생략 가능, 기본값 0):
    #   {"어떤회사": {"roic": 0.18, "g": [0.015, 0.03, 0.04], "p": [0.35, 0.50, 0.15],
    #                "irr10": [-2.0, 8.0, 14.0], "k": 0.01}}
    #   irr10 = r=10%, 원래 g 하에서 3개 구간의 10년 IRR(백분율). irr 하위 명령으로 처음부터 계산할 수 있다.
"""

import argparse
import json
import sys

# ---------------------------------------------------------------------------
# 출력 인코딩: Windows 콘솔 기본값은 cp949 등 레거시 코드페이지라서,
# 이 도구의 ⚠ / ✓ 가 UnicodeEncodeError 를 일으킨다
# ---------------------------------------------------------------------------


def _force_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


_force_utf8_stdio()

# 고든 모형의 유효성 하한: 분모 r-g 가 최소 5%포인트
MIN_SPREAD = 0.05

# ---------------------------------------------------------------------------
# 내장 프리셋: 7개사 10년 투자가치 횡단 비교(기준일 2026-08-14, 기준 수정 2026-08-17)
#
# roic  — 2036년 정상상태 증분 ROIC. 보고서 3.2절의 판단값으로, 기존 자본 ROIC(77%-180%)와
#         배당에서 역산한 내재 증분 ROIC(2%-14.3%) 사이에 있다. 계산이 아니라 판단이다.
# g     — 영구성장률 3개 구간(비관/기준/낙관). 위안화 기준으로 환산하기 「전」의 원래 값.
#         규칙: 비관 = 기준 - 1.5pct, 낙관 = 기준 + 1.0pct(일부러 비대칭이다.
#         하방에는 이미 장부에 잡힌 확실한 증거가 있고, 상방은 대부분 미검증 사항이기 때문이다).
#         이 g 값들은 보고서 3.6절의 표 세 개에서 역산한 것으로, 다시 계산하면 원래 표를 그대로 재현한다.
# p     — 3개 구간의 확률 가중치(비관/기준/낙관). 4절의 대립 검증을 거친 조정값이다.
# irr10 — 보고서 3.6절 r=10% 기준 하의 3개 구간 IRR. rescale 모드의 기준점이다.
# k     — 배당수익률 - 지분 희석률, 연율. IRR 중 엑시트 배수에 따라 변하지 않는 부분이다.
#         결과는 k 에 극히 둔감하므로(k 가 3pct 움직여도 IRR 은 약 0.07pct 만 변한다) 추정값을 쓴다.
# ---------------------------------------------------------------------------

PRESET = {
    "텐센트": dict(roic=0.20, g=(0.015, 0.030, 0.040), p=(0.35, 0.50, 0.15),
                irr10=(0.3, 9.3, 15.4), k=0.020),
    "알리바바": dict(roic=0.15, g=(0.015, 0.030, 0.040), p=(0.35, 0.45, 0.20),
                 irr10=(-1.3, 7.8, 16.3), k=0.000),
    "핀둬둬": dict(roic=0.40, g=(0.005, 0.020, 0.030), p=(0.30, 0.55, 0.15),
                irr10=(-9.7, 8.2, 15.0), k=0.000),
    "구이저우마오타이": dict(roic=0.25, g=(0.010, 0.025, 0.035), p=(0.35, 0.45, 0.20),
                     irr10=(-5.3, 3.4, 7.2), k=0.045),
    "팝마트": dict(roic=0.25, g=(0.015, 0.030, 0.040), p=(0.38, 0.44, 0.18),
                irr10=(-8.2, 4.9, 10.9), k=0.018),
    "메이퇀": dict(roic=0.18, g=(0.015, 0.030, 0.040), p=(0.40, 0.45, 0.15),
                irr10=(-12.1, 1.8, 8.7), k=0.000),
    "MiniMax": dict(roic=0.20, g=(0.025, 0.040, 0.050), p=(0.55, 0.30, 0.15),
                    irr10=(-30.8, -4.7, 9.6), k=-0.030),
}

BASE_R = 0.10  # 프리셋 irr10 에 대응하는 할인율

# 무위험이자율 실측값(2026-08). 위험조정수익의 분자에 쓴다
RF = {
    "CNY": 0.0170,  # 중국 10년물 국채, 2026-08-07
    "USD": 0.0470,  # 미국 10년물 국채, 2026-08-14
}

LABELS = ("비관", "기준", "낙관")

# ---------------------------------------------------------------------------
# 통화 기준 가드레일(audit 하위 명령용)
#
# r 구간 하단 = 관측 무위험이자율 + 약 4.3pct 프리미엄, 상단 = 합성 무위험이자율 + 약 6pct 프리미엄.
# 두 통화의 구간 차이 3%포인트는 전부 국채 금리차이며, 리스크 판단의 차이는 전혀 들어 있지 않다.
# g 상한 = 해당 통화의 장기 인플레이션 + 약 1pct 실질 성장. 이를 넘으면 회사가 경제 전체만큼
# 커진다고 가정하는 것과 같다.
# 데이터 출처는 「7개사 10년 투자가치 횡단 비교 - 확실성 조정 수익」 보고서(20260814) 3.4절 참조.
# ---------------------------------------------------------------------------

CURRENCY_BANDS = {
    "CNY": dict(r=(0.06, 0.09), g_max=0.02, rf=0.0170,
                note="중국 10년물 국채 1.70%(관측) / 2.5-3.0%(합성) + ERP 5.18%"),
    "USD": dict(r=(0.09, 0.115), g_max=0.040, rf=0.0470,
                note="미국 10년물 국채 4.70% + 중국 총 ERP 5.18%(국가 프리미엄 1.01% 포함)"),
    "HKD": dict(r=(0.09, 0.115), g_max=0.040, rf=0.0470,
                note="홍콩달러는 미국달러에 페그되어 있어 USD 와 같은 기준"),
}

# 이산 리스크의 합법적인 귀속. 할인율이나 beta 에 넣으면 일률적으로 반려한다. r 을 3%포인트
# 올리면 10년차 현금흐름에 대한 벌점이 1년차의 2.6배가 되는데, 상장폐지/공급 차단은 대체로
# 균등하거나 오히려 앞쪽에 몰린 연간 위험률이라서 시간 분포를 거꾸로 만든다.
# 비교할 때는 공백을 제거하므로 "테일 구간" 도 "테일구간" 으로 인식한다.
RISK_PLACEMENT_OK = {"시나리오", "테일구간", "확률"}
RISK_PLACEMENT_BAD = {"할인율", "r", "beta", "β"}
RISK_PLACEMENT_WARN = {"미모델링"}

# ---------------------------------------------------------------------------
# 핵심 계산
# ---------------------------------------------------------------------------


def exit_pe(roic, g, r):
    """영구성장 모형의 종말가치 PE.

    (pe, 유보율, 분자, 분모) 를 반환한다. 분모 <= 0 이면 pe=None(모델 무효)을 반환한다.
    """
    spread = r - g
    retention = g / roic
    numerator = 1.0 - retention
    if spread <= 0:
        return None, retention, numerator, spread
    return numerator / spread, retention, numerator, spread


def irr_from_terminal(profit_2036, mcap_today, pe, years=10, payout=0.0):
    """IRR 을 처음부터 계산한다: 종말가치 시가총액 = 2036 이익 x 엑시트 PE.

    payout = 배당수익률 - 희석률, 연율. 기하 수익률에 그대로 더한다(보고서 기준, 재투자 복리는 반영하지 않음).
    """
    return (profit_2036 * pe / mcap_today) ** (1.0 / years) - 1.0 + payout


def rescale_irr(irr_base, pe_base, pe_new, k, years=10):
    """기준 r 하의 IRR 을 새 엑시트 배수로 환산한다.

    IRR 중 자본이득 부분만 엑시트 배수에 따라 변하고, k(배당-희석)는 변하지 않는다:
        (1 + IRR_new - k) = (1 + IRR_base - k) x (PE_new / PE_base)^(1/years)
    """
    return (1.0 + irr_base - k) * (pe_new / pe_base) ** (1.0 / years) - 1.0 + k


def weighted_stats(values, probs):
    """확률 가중 기대값과 표준편차."""
    mean = sum(v * p for v, p in zip(values, probs))
    var = sum(p * (v - mean) ** 2 for v, p in zip(values, probs))
    return mean, var ** 0.5


def evaluate(spec, r, g_shift=0.0, years=10):
    """주어진 r 하에서 한 회사의 3개 구간 엑시트 PE 와 IRR 을 계산한다.

    g_shift 는 통화 환산이다: 원래 g 를 목표 통화의 인플레이션 기준으로 평행이동한다.
    위안화 기준은 보고서 원래 값 대비 -0.01 을 쓴다(중국 장기 인플레이션 약 1% vs 미국 약 2.5%).
    """
    roic = spec["roic"]
    rows = []
    for label, g0, irr_b in zip(LABELS, spec["g"], spec["irr10"]):
        g = g0 + g_shift
        pe_new, retention, numerator, spread = exit_pe(roic, g, r)
        # 기준 PE 는 반드시 「평행이동 전」의 g 를 써야 한다: irr10 이라는 기준점은 (BASE_R, 원래 g) 에 대응한다.
        # 평행이동 후의 g 로 기준을 계산하면 통화 환산의 영향이 절반 누락되어 IRR 이 체계적으로 과대평가된다.
        pe_base, _, _, _ = exit_pe(roic, g0, BASE_R)
        if pe_new is None or pe_base is None:
            irr = None
        else:
            irr = rescale_irr(irr_b / 100.0, pe_base, pe_new, spec["k"], years) * 100.0
        rows.append(dict(label=label, g=g, pe=pe_new, irr=irr,
                         retention=retention, numerator=numerator, spread=spread))
    return rows


def summarize(rows, probs, rf):
    """기대 IRR, 표준편차, 위험조정수익. 한 구간이라도 무효이면 전체를 쓸 수 없다."""
    irrs = [row["irr"] for row in rows]
    if any(x is None for x in irrs):
        return None, None, None
    mean, sd = weighted_stats(irrs, probs)
    ratio = (mean - rf * 100.0) / sd if sd > 0 else None
    return mean, sd, ratio


def load_companies(path):
    if not path:
        return dict(PRESET)
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for name, spec in raw.items():
        out[name] = dict(roic=spec["roic"], g=tuple(spec["g"]), p=tuple(spec["p"]),
                         irr10=tuple(spec["irr10"]), k=spec.get("k", 0.0))
    return out


def warn_spread(spread):
    """분모 폭 점검 표시."""
    if spread <= 0:
        return "✗무효"
    if spread < MIN_SPREAD:
        return "⚠좁음"
    return ""

# ---------------------------------------------------------------------------
# 하위 명령
# ---------------------------------------------------------------------------


def cmd_pe(args):
    pe, retention, numerator, spread = exit_pe(args.roic, args.g, args.r)
    print(f"\nPE(종말가치) = (1 - g/ROIC) / (r - g)\n")
    print(f"  ROIC = {args.roic:.1%}   g = {args.g:.2%}   r = {args.r:.2%}\n")
    print(f"  유보율 g/ROIC   = {args.g:.4f} / {args.roic:.2f} = {retention:.4f}  ({retention:.1%})")
    print(f"  분자 1 - 유보율 = {numerator:.4f}                    (즉 배당성향 {numerator:.1%})")
    print(f"  분모 r - g      = {args.r:.4f} - {args.g:.4f} = {spread:.4f}  ({spread*100:.1f}pct)")
    if pe is None:
        print(f"\n  ✗ 분모 <= 0, 모델 무효. g 는 r 보다 작아야 한다.\n")
        return 1
    print(f"\n  엑시트 PE = {numerator:.4f} / {spread:.4f} = {pe:.1f}x\n")
    if spread < MIN_SPREAD:
        print(f"  ⚠ 분모가 {spread*100:.1f}pct 에 불과해 {MIN_SPREAD*100:.0f}pct 유효성 하한에 못 미친다.")
        bumped, _, _, _ = exit_pe(args.roic, args.g + 0.005, args.r)
        if bumped:
            print(f"    g 를 0.5pct 만 더해도 PE 가 {bumped:.1f}x 가 된다({bumped/pe-1:+.0%}).")
        print(f"    이 칸은 방향성 참고로만 써야 하며, 밸류에이션으로 쓸 수 없다.\n")
    return 0


def cmd_company(args):
    companies = load_companies(args.config)
    if args.name not in companies:
        print(f"알 수 없는 회사: {args.name}. 선택 가능: {', '.join(companies)}", file=sys.stderr)
        return 1
    spec = companies[args.name]
    rows = evaluate(spec, args.r, args.g_shift, args.years)
    rf = args.rf if args.rf is not None else RF["CNY"]

    print(f"\n{args.name}  |  r = {args.r:.1%}   ROIC = {spec['roic']:.0%}   "
          f"g 평행이동 {args.g_shift:+.1%}   Rf = {rf:.2%}\n")
    print(f"{'구간':<6}{'확률':>6}{'g':>8}{'유보율':>8}{'분자':>8}{'분모':>9}{'엑시트PE':>9}{'IRR':>9}  점검")
    print("-" * 74)
    for row, p in zip(rows, spec["p"]):
        pe = f"{row['pe']:.1f}x" if row["pe"] else "—"
        irr = f"{row['irr']:+.1f}%" if row["irr"] is not None else "—"
        print(f"{row['label']:<6}{p:>6.0%}{row['g']:>8.1%}{row['retention']:>8.1%}"
              f"{row['numerator']:>8.3f}{row['spread']*100:>7.1f}pct{pe:>9}{irr:>9}  {warn_spread(row['spread'])}")

    mean, sd, ratio = summarize(rows, spec["p"], rf)
    print("-" * 74)
    if mean is None:
        print("\n기대값을 쓸 수 없다: 최소 한 구간의 분모 <= 0.\n")
        return 1
    print(f"{'기대IRR':<12}{mean:+.2f}%      표준편차 {sd:.1f}%      위험조정 {ratio:+.2f}\n")
    narrow = [r_["label"] for r_ in rows if 0 < r_["spread"] < MIN_SPREAD]
    if narrow:
        print(f"⚠ {'/'.join(narrow)} 구간의 분모가 {MIN_SPREAD*100:.0f}pct 미만이라 엑시트 배수가 g 에 극도로 민감하다.\n")
    return 0


def cmd_table(args):
    companies = load_companies(args.config)
    rf = args.rf if args.rf is not None else RF["CNY"]
    results = []
    for name, spec in companies.items():
        rows = evaluate(spec, args.r, args.g_shift, args.years)
        mean, sd, ratio = summarize(rows, spec["p"], rf)
        results.append((name, spec, rows, mean, sd, ratio))
    ok = [x for x in results if x[5] is not None]
    bad = [x for x in results if x[5] is None]
    ok.sort(key=lambda x: -x[5])

    print(f"\nr = {args.r:.1%}   g 평행이동 {args.g_shift:+.1%}   Rf = {rf:.2%}   보유기간 {args.years}년\n")
    print(f"{'순위':<5}{'회사':<10}{'엑시트PE(비관/기준/낙관)':<24}{'IRR(비관/기준/낙관)':<30}"
          f"{'기대IRR':>9}{'σ':>8}{'위험조정':>11}")
    print("-" * 98)
    for i, (name, spec, rows, mean, sd, ratio) in enumerate(ok, 1):
        pes = "/".join(f"{r_['pe']:.1f}" for r_ in rows)
        irrs = "/".join(f"{r_['irr']:+.1f}%" for r_ in rows)
        print(f"{i:<5}{name:<10}{pes:<26}{irrs:<32}{mean:>8.2f}%{sd:>7.1f}%{ratio:>11.2f}")
    for name, spec, rows, mean, sd, ratio in bad:
        print(f"{'—':<5}{name:<10}{'모델 무효(분모 <= 0)':<26}")

    narrow = sum(1 for _, _, rows, _, _, _ in results
                 for r_ in rows if 0 < r_["spread"] < MIN_SPREAD)
    total = sum(len(rows) for _, _, rows, _, _, _ in results)
    print("-" * 98)
    if narrow:
        print(f"\n⚠ {total}칸 중 {narrow}칸의 분모가 {MIN_SPREAD*100:.0f}pct 유효성 하한에 못 미친다. "
              f"`check --r {args.r}` 를 실행해 상세를 확인한다.")
        if narrow > total / 2:
            print(f"  절반 넘는 칸이 무효다. 이 구간은 「상방/하방 시나리오」로 봐야 하며, 동등하게 신뢰할 수 있는 또 하나의 밸류에이션으로 쓸 수 없다.")
    print()
    return 0


def cmd_sweep(args):
    companies = load_companies(args.config)
    rf = args.rf if args.rf is not None else RF["CNY"]
    rates = [float(x) for x in args.r.split(",")]
    order = {}

    print(f"\ng 평행이동 {args.g_shift:+.1%}   Rf = {rf:.2%}   보유기간 {args.years}년")
    print(f"\n기대IRR:\n")
    header = f"{'회사':<10}" + "".join(f"{'r=' + format(x, '.0%'):>11}" for x in rates)
    print(header)
    print("-" * len(header))
    for name, spec in companies.items():
        cells = []
        for r in rates:
            rows = evaluate(spec, r, args.g_shift, args.years)
            mean, sd, ratio = summarize(rows, spec["p"], rf)
            cells.append((mean, ratio))
            order.setdefault(r, []).append((name, ratio))
        line = f"{name:<10}" + "".join(
            f"{m:>10.1f}%" if m is not None else f"{'—':>11}" for m, _ in cells)
        print(line)

    print(f"\n위험조정수익 순위:\n")
    ranks = {}
    for r in rates:
        entries = [(n, x) for n, x in order[r] if x is not None]
        entries.sort(key=lambda t: -t[1])
        for pos, (n, _) in enumerate(entries, 1):
            ranks.setdefault(n, {})[r] = pos
    header = f"{'회사':<10}" + "".join(f"{'r=' + format(x, '.0%'):>11}" for x in rates)
    print(header)
    print("-" * len(header))
    for name in companies:
        cells = "".join(f"{ranks.get(name, {}).get(r, '—'):>11}" for r in rates)
        print(f"{name:<10}{cells}")

    moved = [n for n in companies
             if len({ranks.get(n, {}).get(r) for r in rates}) > 1]
    print()
    if moved:
        print(f"r 에 따라 순위가 바뀌는 회사: {', '.join(moved)}")
        print(f"나머지 {len(companies) - len(moved)}개사는 순위가 일정하다. 절대 수치보다 훨씬 견고한 결론이다.\n")
    else:
        print(f"전체 {len(companies)}개사의 순위가 일정하다. 순위는 r 의 영향을 전혀 받지 않는다.\n")
    return 0


def stress_pass(mean_irr_pct, r):
    """비중 스트레스 테스트: 기대 IRR(%포인트)이 자본비용 r 을 감당하는가.

    True/False 를 반환한다. mean_irr_pct 가 None 이면 None(모델 무효)을 반환한다.
    포트폴리오 비중 스트레스 테스트이지, 매수/회피에 대한 단독 거부권이 아니다.
    """
    if mean_irr_pct is None:
        return None
    return mean_irr_pct >= r * 100.0


def in_band(rate, band):
    """r 이 통화별 합리 구간 안에 있는가(폐구간, 부동소수점 오차 허용). band=None 이면 구간 필터를 하지 않는다."""
    if band is None:
        return None
    lo, hi = band["r"]
    return lo - 1e-9 <= rate <= hi + 1e-9


def flip_analysis(spec, r, delta=0.02, g_shift=0.0, years=10, rf=None, band=None):
    """r-delta / r / r+delta 3개 구간에서 기대 IRR 과 스트레스 테스트 통과 여부를 계산한다.

    band 가 CURRENCY_BANDS 의 한 항목이면, 구간 밖 구간은 참고용이며 반전 판정에 참여하지 않는다
    (audit C1 은 구간 밖 r 을 거부한다. 그런 r 로 "반전" 을 끌어내는 것은 결론에 맞춰 r 을 조정하는 것이다).

    반환 dict:
      rates, means, passes, in_band, flipped, labels
    in_band 는 구간마다 True/False 다. band=None 이면 None(구간 필터 미적용)이다.
    flipped=True 는 판정에 참여한 구간들의 통과/미통과가 서로 다르다는 뜻이다(결론이 Δr 에 따라 반전).
    """
    if rf is None:
        rf = band["rf"] if band else RF["CNY"]
    if delta <= 0:
        raise ValueError("delta 는 양수여야 한다. 예: 0.02 는 ±2pp 를 뜻한다")
    rates = (r - delta, r, r + delta)
    labels = (f"r−{delta*100:g}pp", "기준 r", f"r+{delta*100:g}pp")
    means, passes, flags = [], [], []
    for rate in rates:
        flags.append(in_band(rate, band))
        if rate <= 0:
            means.append(None)
            passes.append(None)
            continue
        rows = evaluate(spec, rate, g_shift, years)
        mean, _sd, _ratio = summarize(rows, spec["p"], rf)
        means.append(mean)
        passes.append(stress_pass(mean, rate))
    known = [p for p, ok in zip(passes, flags) if p is not None and ok is not False]
    flipped = len(set(known)) > 1 if known else False
    return dict(rates=rates, means=means, passes=passes, in_band=tuple(flags),
                flipped=flipped, labels=labels)


def _floats(text, n, what):
    vals = [float(x) for x in text.split(",")]
    if len(vals) != n:
        raise ValueError(f"{what} 에는 쉼표로 구분한 숫자 {n}개(비관,기준,낙관)가 필요하다. 받은 개수: {len(vals)}")
    return tuple(vals)


def inline_spec(args):
    """--roic/--g/--p/--irr10/--k 로 한 회사의 파라미터를 조립한다(필드는 PRESET / --config 와 동일)."""
    missing = [f"--{k}" for k in ("roic", "g", "p", "irr10") if getattr(args, k) is None]
    if missing:
        raise ValueError(f"인라인 파라미터가 불완전하다. 누락: {' '.join(missing)}"
                         f"(--roic/--g/--p/--irr10 은 함께 주어야 한다)")
    spec = dict(roic=args.roic, g=_floats(args.g, 3, "--g"), p=_floats(args.p, 3, "--p"),
                irr10=_floats(args.irr10, 3, "--irr10"), k=args.k)
    if abs(sum(spec["p"]) - 1.0) > 1e-6:
        raise ValueError(f"--p 3개 구간 확률의 합은 1 이어야 한다. 현재 {sum(spec['p']):.4f}")
    return spec


def cmd_flip(args):
    """r±delta 민감도: 결론이 할인율에 따라 반전되는가.

    용도: 매수/보유/회피를 제시하기 전에 "결론이 산 것이 회사인가 할인율인가" 를 드러낸다.
    스트레스 테스트 미통과 → 비중 제안을 조인다. 이것만으로 결정을 회피로 바꿔서는 안 된다.
    """
    band = CURRENCY_BANDS.get(args.currency.upper())
    if band is None:
        print(f"알 수 없는 통화 {args.currency}. 선택 가능: {', '.join(CURRENCY_BANDS)}", file=sys.stderr)
        return 1
    inline = any(getattr(args, k) is not None for k in ("roic", "g", "p", "irr10"))
    try:
        if inline:
            if args.config:
                raise ValueError("인라인 파라미터와 --config 는 둘 중 하나만 쓴다")
            spec = inline_spec(args)
        else:
            companies = load_companies(args.config)
            if args.name not in companies:
                print(f"알 수 없는 회사: {args.name}. 선택 가능: {', '.join(companies)}. "
                      f"신규 회사는 --roic/--g/--p/--irr10 인라인 파라미터를 쓰거나, JSON 으로 작성해 --config 로 전달한다",
                      file=sys.stderr)
                return 1
            spec = companies[args.name]
        rf = args.rf if args.rf is not None else band["rf"]
        result = flip_analysis(spec, args.r, args.delta, args.g_shift, args.years, rf, band)
    except ValueError as exc:
        print(f"파라미터 오류: {exc}", file=sys.stderr)
        return 1

    cur = args.currency.upper()
    print(f"\n{args.name}  |  기준 r = {args.r:.2%}   Δr = ±{args.delta*100:g}pp   통화 {cur}   "
          f"g 평행이동 {args.g_shift:+.1%}   Rf = {rf:.2%}   보유기간 {args.years}년")
    lo, hi = band["r"]
    print(f"통화별 합리 구간: r ∈ [{lo:.1%}, {hi:.1%}](audit C1 과 동일). 구간 밖 구간은 참고용이며 반전 판정에 참여하지 않는다.")
    if not result["in_band"][1]:
        print(f"\n【반려】기준 r={args.r:.2%} 는 {cur} 의 [{lo:.1%}, {hi:.1%}] 구간 안에 있지 않다. "
              f"audit C1 도 똑같이 거부한다. r 을 먼저 고친 뒤 flip 을 실행한다.\n")
        return 1
    print(f"판정 규칙: 기대 IRR ≥ r → 비중 스트레스 테스트 통과, 아니면 미통과.")
    print(f"역할: 10년 모델 = 비중 스트레스 테스트이며, 매수/보유/회피에 대한 유일한 거부권이 아니다.\n")
    print(f"{'구간':<10}{'r':>8}{'기대IRR':>12}{'r 대비':>12}{'스트레스':>10}")
    print("-" * 54)
    for label, rate, mean, passed, ok in zip(
            result["labels"], result["rates"], result["means"], result["passes"],
            result["in_band"]):
        if rate <= 0:
            print(f"{label:<10}{'≤0':>8}{'—':>12}{'—':>12}{'무효':>10}")
            continue
        mean_s = f"{mean:+.2f}%" if mean is not None else "—"
        if mean is None:
            rel = "—"
            tag = "무효"
        else:
            gap = mean - rate * 100.0
            rel = f"{gap:+.2f}pp"
            tag = "통과" if passed else "미통과"
        if ok is False:
            tag += "(구간 밖, 참고용)"
        print(f"{label:<10}{rate:>8.2%}{mean_s:>12}{rel:>12}  {tag}")
    print("-" * 54)

    base_pass = result["passes"][1]
    if base_pass is None:
        print("\n【무효】기준 r 하에서 모델을 쓸 수 없다(분모 무효 등). 먼저 audit / check 를 실행한다.\n")
        return 1

    judged = sum(1 for p, ok in zip(result["passes"], result["in_band"])
                 if p is not None and ok is not False)
    if result["flipped"]:
        print(f"\n【반전】결론이 통화별 합리 구간 안에서 Δr±{args.delta*100:g}pp 에 따라 반전된다. "
              f"보고서에 반드시 밝힌다: 본 결론은 할인율에 민감하다. 단일 기준 r 하의 미통과를 매수 거부권으로 삼아서는 안 된다.")
        print(f"        올바른 사용법: 비중 상한을 조이고, 3년 3개 시나리오/thesis 와의 「밸류에이션 이견 대조」를 마친다.")
    else:
        status = "항상 통과" if base_pass else "항상 미통과"
        print(f"\n【안정】Δr±{args.delta*100:g}pp 구간 안에서 스트레스 테스트 {status}. 할인율 교란에 대해 더 견고하다.")
        if judged < 2:
            print(f"        주의: 양쪽 구간이 모두 구간 밖이라, 구간 안에서는 기준 구간 하나만 판정에 참여한다. "
                  f"더 작은 --delta 로 구간 안에서 다시 점검할 수 있다.")
        if not base_pass:
            print(f"        미통과는 여전히 비중만 제약하며, 자동으로 회피를 뜻하지 않는다. 나머지 다섯 차원과 나란히 놓고 결정해야 한다.")

    print("\n알림: 매수 결론에 맞추려고 r 을 통화별 합리 구간에서 벗어나게 조정하는 것은 금지한다. "
          "민감도는 일관성 감사를 위한 것이지, 「r 을 낮춰서 사기」 위한 것이 아니다.\n")
    # 종료 코드 0: 도구가 정상 실행됨. 반전 여부는 출력에 적히며, skill 이 보고서에 반드시 옮겨 적게 한다.
    return 0


def cmd_check(args):
    companies = load_companies(args.config)
    print(f"\n분모 폭 점검   r = {args.r:.1%}   g 평행이동 {args.g_shift:+.1%}   "
          f"하한 {MIN_SPREAD*100:.0f}pct\n")
    print(f"{'회사':<10}{'구간':<6}{'g':>8}{'r-g':>9}{'엑시트PE':>9}"
          f"{'g+0.5pct 후':>12}{'PE 변화':>9}  점검")
    print("-" * 76)
    flagged = 0
    for name, spec in companies.items():
        for label, g0 in zip(LABELS, spec["g"]):
            g = g0 + args.g_shift
            pe, _, _, spread = exit_pe(spec["roic"], g, args.r)
            bumped, _, _, _ = exit_pe(spec["roic"], g + 0.005, args.r)
            mark = warn_spread(spread)
            if mark:
                flagged += 1
            pe_s = f"{pe:.1f}x" if pe else "—"
            bumped_s = f"{bumped:.1f}x" if bumped else "—"
            delta = f"{bumped/pe-1:+.0%}" if (pe and bumped) else "—"
            print(f"{name if label == LABELS[0] else '':<10}{label:<6}{g:>8.1%}"
                  f"{spread*100:>7.1f}pct{pe_s:>9}{bumped_s:>12}{delta:>9}  {mark}")
    print("-" * 76)
    total = len(companies) * 3
    print(f"\n{total}칸 중 {flagged}칸에서 경고가 발생했다.")
    print(f"「g+0.5pct 후」 열이 이 규칙의 핵심이다: 분모가 좁을수록 영구성장률이 조금만 움직여도 밸류에이션이 뒤집힌다.\n")
    return 0


def cmd_audit(args):
    """세 가지 강제 제약의 통과 검사. 하나라도 통과하지 못하면 → 【반려】, 종료 코드 1."""
    band = CURRENCY_BANDS.get(args.currency.upper())
    if band is None:
        print(f"알 수 없는 통화 {args.currency}. 선택 가능: {', '.join(CURRENCY_BANDS)}", file=sys.stderr)
        return 1
    gs = [float(x) for x in args.g.split(",")]
    fails, warns = [], []

    print(f"\n{'='*72}\n밸류에이션 기준 통과 검사   통화={args.currency.upper()}   r={args.r:.2%}   "
          f"ROIC={args.roic:.0%}   g={'/'.join(f'{x:.1%}' for x in gs)}\n{'='*72}")

    # --- C1 통화 일관성: r 과 g 는 같은 통화여야 한다 ------------------------
    lo, hi = band["r"]
    print(f"\n【C1】통화 일관성 — r 과 g 는 같은 통화를 써야 한다")
    print(f"     {args.currency.upper()} 기준: {band['note']}")
    print(f"     r 합리 구간 [{lo:.1%}, {hi:.1%}]   g 상한 {band['g_max']:.1%}   Rf {band['rf']:.2%}")
    if not (lo <= args.r <= hi):
        other = [c for c, b in CURRENCY_BANDS.items()
                 if c != args.currency.upper() and b["r"][0] <= args.r <= b["r"][1]]
        hint = f"(이 r 은 {'/'.join(other)} 의 구간에 들어간다. 통화를 잘못 고른 것은 아닌가?)" if other else ""
        fails.append(f"C1: r={args.r:.2%} 는 {args.currency.upper()} 의 [{lo:.1%},{hi:.1%}] 구간 안에 있지 않다 {hint}")
    # g 상한은 기준 구간에 건다. 낙관 구간은 설계상 기준 +1pct 이므로 1pct 를 추가로 허용한다.
    g_base = gs[1] if len(gs) >= 2 else gs[0]
    if g_base > band["g_max"] or max(gs) > band["g_max"] + 0.01:
        other = [c for c, b in CURRENCY_BANDS.items()
                 if c != args.currency.upper() and g_base <= b["g_max"]]
        hint = (f"(이것은 {'/'.join(other)} 의 수준이다. r 은 자국 통화를 쓰고 g 는 외화를 썼다. "
                f"가장 흔한 기준 혼용이다)") if other else ""
        fails.append(f"C1: 기준 구간 g={g_base:.1%} 가 {args.currency.upper()} 상한 "
                     f"{band['g_max']:.1%} 를 넘는다(낙관 구간은 1pct 를 더 허용해 {band['g_max']+0.01:.1%} 까지){hint}")
    if args.rf is not None and abs(args.rf - band["rf"]) > 0.005:
        fails.append(f"C1: 무위험이자율 {args.rf:.2%} 가 {args.currency.upper()} 의 {band['rf']:.2%} 와 맞지 않는다")
    print(f"     → {'✗ 불통과' if any(f.startswith('C1') for f in fails) else '✓ 통과'}")

    # --- C2 분모 폭 ----------------------------------------------------------
    print(f"\n【C2】분모 폭 — r-g 가 최소 {MIN_SPREAD*100:.0f}%포인트")
    narrow = []
    for label, g in zip(LABELS, gs):
        pe, _, _, spread = exit_pe(args.roic, g, args.r)
        bumped, _, _, _ = exit_pe(args.roic, g + 0.005, args.r)
        tag = warn_spread(spread)
        delta = f"  g+0.5pct → {bumped:.1f}x ({bumped/pe-1:+.0%})" if (pe and bumped) else ""
        pe_s = f"{pe:.1f}x" if pe else "모델 무효"
        print(f"     {label}  g={g:>5.1%}  r-g={spread*100:>4.1f}pct  PE={pe_s:>10}{delta}  {tag}")
        if spread <= 0:
            fails.append(f"C2: {label} 구간 r-g={spread*100:.1f}pct <= 0, 모델 무효")
        elif spread < MIN_SPREAD:
            narrow.append(label)
    if narrow:
        if args.upside_only:
            warns.append(f"C2: {'/'.join(narrow)} 구간의 분모가 {MIN_SPREAD*100:.0f}pct 에 못 미친다. "
                         f"--upside-only 를 선언했으므로 시나리오 참고용으로만 쓸 수 있다")
        else:
            fails.append(f"C2: {'/'.join(narrow)} 구간의 분모가 {MIN_SPREAD*100:.0f}pct 에 못 미친다. "
                         f"g 를 좁히거나, --upside-only 를 붙여 이것이 밸류에이션이 아니라 시나리오임을 선언한다")
    print(f"     → {'✗ 불통과' if any(f.startswith('C2') for f in fails) else '✓ 통과'}")

    # --- C3 이산 리스크 귀속 -------------------------------------------------
    print(f"\n【C3】이산 리스크 귀속 — 상장폐지/VIE/지정학/규제는 시나리오에 귀속해야 하며, r 이나 β 에 넣을 수 없다")
    if args.beta != 1.0 and not args.beta_justification:
        fails.append(f"C3: β={args.beta} 가 1.0 에서 벗어났는데 --beta-justification 이 없다. "
                     f"회귀 β 의 표준오차만 ±0.2-0.3 이다. 조정하려면 상향식 펀더멘털 β 를 썼음을 설명해야 한다")
    for item in [x for x in args.discrete_risks.split(",") if x.strip()]:
        if ":" not in item:
            fails.append(f"C3: '{item}' 의 형식은 리스크명:귀속 이어야 한다")
            continue
        name, place = (p.strip() for p in item.split(":", 1))
        key = "".join(place.split())
        if key in RISK_PLACEMENT_BAD:
            fails.append(f"C3: 「{name}」이(가) '{place}' 에 들어갔다. r 을 올리면 10년차 현금흐름에 대한 벌점이 1년차의 2.6배가 되는데, "
                         f"이런 리스크는 균등하거나 오히려 앞쪽에 몰린 연간 위험률이다. 리스크의 시간 분포를 거꾸로 만든다")
            mark = "✗"
        elif key in RISK_PLACEMENT_WARN:
            warns.append(f"C3: 「{name}」 미모델링. 보고서의 「한계」 장에 반드시 적는다")
            mark = "⚠"
        elif key in RISK_PLACEMENT_OK:
            mark = "✓"
        else:
            fails.append(f"C3: 「{name}」 의 귀속 '{place}' 을(를) 인식할 수 없다. "
                         f"합법적인 값: {'/'.join(sorted(RISK_PLACEMENT_OK | RISK_PLACEMENT_WARN))}")
            mark = "✗"
        print(f"     {mark} {name} → {place}")
    if args.beta == 1.0:
        print(f"     β = 1.0(기본값, 근거 불필요)")
    else:
        print(f"     β = {args.beta}(근거: {args.beta_justification or '제시되지 않음'})")
    print(f"     → {'✗ 불통과' if any(f.startswith('C3') for f in fails) else '✓ 통과'}")

    # --- 판정 ----------------------------------------------------------------
    print(f"\n{'='*72}")
    for w in warns:
        print(f"⚠ {w}")
    if fails:
        print(f"\n【반려】{len(fails)}개 항목 불통과:\n")
        for i, msg in enumerate(fails, 1):
            print(f"  {i}. {msg}")
        print(f"\n수정한 뒤 이 명령을 다시 실행한다. 통과해야 밸류에이션을 보고서에 쓸 수 있다.\n")
        return 1
    print(f"\n【통과】세 가지 강제 제약을 모두 통과했다. 밸류에이션을 보고서에 쓸 수 있다.")
    if warns:
        print(f"       단, 위의 경고 {len(warns)}건은 보고서에 명시적으로 적어야 한다.")
    print()
    return 0


def cmd_irr(args):
    irr = irr_from_terminal(args.profit, args.mcap, args.pe, args.years, args.payout)
    terminal = args.profit * args.pe
    mult = terminal / args.mcap
    print(f"\nIRR = (2036 시가총액 / 오늘 시가총액)^(1/{args.years}) - 1 + 배당수익률 - 희석률\n")
    print(f"  2036 시가총액 = {args.profit:,.0f} x {args.pe:.1f}x = {terminal:,.0f}")
    print(f"  오늘 시가총액 = {args.mcap:,.0f}")
    print(f"  총 배수       = {mult:.4f}")
    print(f"  기하 연환산   = {mult ** (1.0/args.years) - 1:+.2%}")
    print(f"  배당-희석     = {args.payout:+.2%}")
    print(f"\n  IRR = {irr:+.2%}\n")
    return 0

# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="종말가치 배수와 10년 IRR 추정(영구성장 모형)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("사용법:")[-1])
    sub = parser.add_subparsers(dest="cmd")

    def add_common(p, need_r=True):
        if need_r:
            p.add_argument("--r", type=float, required=True, help="자본비용, 소수(예: 0.06)")
        p.add_argument("--g-shift", type=float, default=0.0,
                       help="g 의 통화 평행이동, 소수. 위안화 기준은 보고서 원래 값 대비 -0.01")
        p.add_argument("--years", type=int, default=10, help="보유기간(년), 기본값 10")
        p.add_argument("--config", help="사용자 정의 회사 설정 JSON. 생략하면 내장 7개사 프리셋을 쓴다")

    p = sub.add_parser("pe", help="단일 시점 엑시트 PE, 전체 산식 출력")
    p.add_argument("--roic", type=float, required=True)
    p.add_argument("--g", type=float, required=True)
    p.add_argument("--r", type=float, required=True)
    p.set_defaults(func=cmd_pe)

    p = sub.add_parser("company", help="단일 회사 3개 구간 추정")
    p.add_argument("--name", required=True)
    p.add_argument("--rf", type=float, help="무위험이자율. 생략하면 위안화 1.70%%")
    add_common(p)
    p.set_defaults(func=cmd_company)

    p = sub.add_parser("table", help="여러 회사 횡단 비교표 + 순위")
    p.add_argument("--rf", type=float, help="무위험이자율. 생략하면 위안화 1.70%%")
    add_common(p)
    p.set_defaults(func=cmd_table)

    p = sub.add_parser("sweep", help="여러 r 구간 민감도 + 순위 안정성 검증")
    p.add_argument("--r", required=True, help="쉼표로 구분. 예: 0.06,0.08,0.10,0.12")
    p.add_argument("--rf", type=float, help="무위험이자율. 생략하면 위안화 1.70%%")
    add_common(p, need_r=False)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("flip", help="r±Δ 민감도: 스트레스 테스트 결론이 반전되는가(매수 거부권 아님)")
    p.add_argument("--name", required=True,
                   help="회사명: 내장 프리셋 / --config 의 키. 인라인 파라미터를 쓸 때는 제목으로만 쓰인다")
    p.add_argument("--r", type=float, required=True, help="기준 자본비용, 소수(예: 0.10)")
    p.add_argument("--delta", type=float, default=0.02,
                   help="민감도 반폭, 소수, 기본값 0.02(즉 ±2pp)")
    p.add_argument("--currency", required=True,
                   help="현금흐름 통화 CNY / USD / HKD: 구간 밖 구간은 참고용이며 반전 판정에 참여하지 않는다")
    p.add_argument("--rf", type=float, help="무위험이자율. 생략하면 --currency 에 대응하는 Rf")
    p.add_argument("--roic", type=float, help="인라인: 2036 정상상태 증분 ROIC, 소수")
    p.add_argument("--g", help="인라인: 3개 구간의 원래 영구성장률, 쉼표로 구분. 예: 0.015,0.03,0.04")
    p.add_argument("--p", help="인라인: 3개 구간 확률, 쉼표로 구분, 합은 1. 예: 0.35,0.50,0.15")
    p.add_argument("--irr10", help="인라인: r=10%% 이고 원래 g 일 때 3개 구간의 10년 IRR(백분율). "
                        "첫 항이 음수이면 등호 표기를 쓴다. 예: --irr10=-2,8,14")
    p.add_argument("--k", type=float, default=0.0, help="인라인: 배당수익률-희석률, 연율 소수, 기본값 0")
    add_common(p, need_r=False)
    p.set_defaults(func=cmd_flip)

    p = sub.add_parser("check", help="분모 폭 점검")
    add_common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("audit", help="세 가지 강제 제약 통과 검사(【통과】/【반려】)")
    p.add_argument("--currency", required=True, help="현금흐름 통화: CNY / USD / HKD")
    p.add_argument("--r", type=float, required=True, help="자본비용, 소수")
    p.add_argument("--roic", type=float, required=True, help="2036 정상상태 증분 ROIC, 소수")
    p.add_argument("--g", required=True, help="3개 구간 영구성장률, 쉼표로 구분. 예: 0.005,0.02,0.03")
    p.add_argument("--rf", type=float, help="무위험이자율, 소수. 주어지면 통화와 맞는지 검증한다")
    p.add_argument("--beta", type=float, default=1.0, help="주식 위험계수, 기본값 1.0")
    p.add_argument("--beta-justification", help="β 가 1.0 에서 벗어나면 필수")
    p.add_argument("--discrete-risks", default="",
                   help="이산 리스크 귀속. 형식은 리스크명:귀속, 쉼표로 구분. "
                        "합법적인 귀속: 시나리오/테일구간/확률(통과), 미모델링(경고). "
                        "할인율/r/beta 로 적으면 일률적으로 반려")
    p.add_argument("--upside-only", action="store_true",
                   help="이 구간이 상방/하방 시나리오 참고용임을 선언하고, 분모가 5pct 에 못 미치는 것을 허용한다")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("irr", help="IRR 을 처음부터 계산(이익과 시가총액 입력)")
    p.add_argument("--profit", type=float, required=True, help="종말가치 연도 이익")
    p.add_argument("--mcap", type=float, required=True, help="오늘 시가총액. 이익과 같은 단위, 같은 통화")
    p.add_argument("--pe", type=float, required=True, help="엑시트 PE")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--payout", type=float, default=0.0, help="배당수익률 - 희석률, 연율 소수")
    p.set_defaults(func=cmd_irr)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

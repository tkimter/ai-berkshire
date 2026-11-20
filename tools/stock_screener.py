#!/usr/bin/env python3
"""
stock_screener.py — 모멘텀 발견 + 가치 검증 종목 스크리너
사용법:
  python3 stock_screener.py                   # watchlist 전체 스캔
  python3 stock_screener.py NVDA TSLA GOOG    # 지정 종목 스캔
  python3 stock_screener.py --update MU       # MU 의 펀더멘털 데이터 갱신

프레임워크:
  1단계(모멘텀 발견): 60일 신고가 + 거래량 증가 확인 → 후보 풀 진입
  2단계(가치 검증): 6개 항목 점수 ≥ 3/6 → 매수 신호
  신호 등급: 3/6=탐색 비중 3% | 4/6=표준 비중 5% | 5-6/6=확신 비중 8%

개선점(NVDA/AMD/MU 백테스트에서 도출):
  1. 매출총이익률 2분기 연속 개선 → 독립 매수 조건(NVDA 2023-01 누락 해결)
  2. EPS 서프라이즈 >30% → 경기순환주 독립 조건(MU 바닥 신호 해결)
  3. 이분법 판단 대신 신호 등급제
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from collections import OrderedDict

# ============================================================
# 설정
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FUND_FILE = os.path.join(DATA_DIR, "fundamentals.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

DEFAULT_WATCHLIST = {
    "us_ai_chip": ["NVDA", "AMD", "MU", "AVGO", "MRVL", "TSM"],
    "us_ai_app": ["GOOG", "META", "MSFT", "AMZN", "CRM", "NOW", "PLTR"],
    "us_ai_infra": ["ETN", "PWR", "VRT", "CRWV"],
    "us_crypto": ["COIN", "HOOD", "MSTR", "CRCL"],
    "hk_internet": ["0700.HK", "9888.HK", "1024.HK", "9992.HK"],
    "a_share": [],  # A주는 다른 데이터 출처가 필요하다. 추후 확장
}


def _safe_stdio():
    """콘솔 인코딩(예: Windows cp949)으로 표현할 수 없는 문자(이모지 등) 때문에 죽지 않게 한다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty() or os.environ.get("PYTHONIOENCODING"):
                stream.reconfigure(errors="replace")
            else:
                # 파이프·리다이렉트 출력은 UTF-8 로 고정한다(중국어 종목명·기호가 '?' 로 뭉개지지 않게)
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ============================================================
# 가격 데이터 수집(curl 로 Python SSL 문제를 우회)
# ============================================================

def fetch_prices_curl(ticker, days=120):
    """curl 로 Yahoo Finance 일봉 데이터를 가져온다"""
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    try:
        result = subprocess.run(
            ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        chart = data.get("chart", {}).get("result", [{}])[0]
        timestamps = chart.get("timestamp", [])
        quote = chart.get("indicators", {}).get("quote", [{}])[0]
        rows = []
        for i, ts in enumerate(timestamps):
            c = quote.get("close", [None] * len(timestamps))[i]
            v = quote.get("volume", [None] * len(timestamps))[i]
            h = quote.get("high", [None] * len(timestamps))[i]
            if c and v and h:
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                rows.append({"date": dt, "close": c, "high": h, "volume": v})
        return rows if len(rows) > 60 else None
    except Exception as e:
        return None


# ============================================================
# 펀더멘털 데이터 관리
# ============================================================

def load_fundamentals():
    """펀더멘털 데이터를 불러온다"""
    if os.path.exists(FUND_FILE):
        with open(FUND_FILE) as f:
            return json.load(f)
    return {}


def save_fundamentals(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FUND_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_fundamental_interactive(ticker):
    """대화식으로 펀더멘털 데이터를 갱신한다"""
    funds = load_fundamentals()
    if ticker not in funds:
        funds[ticker] = {"quarters": {}}
    print(f"\n  {ticker} 펀더멘털 데이터 갱신")
    print(f"  기존 분기: {', '.join(funds[ticker]['quarters'].keys()) or '없음'}")
    date = input("  실적 발표일 (YYYY-MM-DD): ").strip()
    label = input("  라벨 (예: Q1 2024): ").strip()
    rev_yoy = float(input("  매출 전년 동기 대비 증가율 (%): "))
    gm = float(input("  매출총이익률 (%): "))
    eps_beat = float(input("  EPS 서프라이즈 (%): "))

    funds[ticker]["quarters"][date] = {
        "label": label, "rev_yoy": rev_yoy, "gm": gm, "eps_beat": eps_beat
    }
    save_fundamentals(funds)
    print(f"  ✅ {ticker} {label} 저장 완료")


# ============================================================
# 1단계: 모멘텀 발견
# ============================================================

def check_momentum(prices):
    """최근 거래일에 모멘텀 신호가 발생했는지 확인한다"""
    if len(prices) < 61:
        return None

    latest = prices[-1]
    close = latest["close"]

    # 60일 신고가
    past_60_highs = [p["high"] for p in prices[-61:-1]]
    is_60d_high = close > max(past_60_highs)

    # 거래량 증가: 최근 5일 평균 거래량 > 20일 평균 거래량 × 1.5
    vol_5 = sum(p["volume"] for p in prices[-5:]) / 5
    vol_20 = sum(p["volume"] for p in prices[-20:]) / 20
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 0
    is_volume = vol_ratio > 1.5

    # 30일 상승률
    close_30d = prices[-31]["close"] if len(prices) > 30 else prices[0]["close"]
    pct_30d = (close - close_30d) / close_30d * 100

    # 최근 5일 안에 돌파일이 있는지(꼭 오늘일 필요는 없다)
    recent_breakout = False
    for i in range(-5, 0):
        if prices[i]["close"] > max(p["high"] for p in prices[i-60:i]):
            recent_breakout = True
            break

    triggered = (is_60d_high or recent_breakout) and is_volume

    return {
        "triggered": triggered,
        "close": round(close, 2),
        "date": latest["date"],
        "is_60d_high": is_60d_high,
        "vol_ratio": round(vol_ratio, 2),
        "pct_30d": round(pct_30d, 1),
    }


# ============================================================
# 2단계: 가치 검증(6개 항목, 백테스트 개선 반영)
# ============================================================

def check_value(ticker, signal_date=None):
    """6개 항목 가치 검증"""
    funds = load_fundamentals()
    if ticker not in funds or not funds[ticker].get("quarters"):
        return None

    quarters = funds[ticker]["quarters"]
    sorted_q = sorted(quarters.items(), key=lambda x: x[0])

    # 최근 두 분기를 찾는다
    if signal_date:
        valid = [(d, q) for d, q in sorted_q if d <= signal_date]
    else:
        valid = sorted_q

    if not valid:
        return None

    latest = valid[-1]
    prev = valid[-2] if len(valid) >= 2 else None
    prev2 = valid[-3] if len(valid) >= 3 else None

    d = latest[1]
    pd = prev[1] if prev else None
    pd2 = prev2[1] if prev2 else None

    checks = {}

    # 1. 매출 가속(전년 동기 대비 증가율이 개선 중)
    if pd:
        checks["매출 가속"] = d["rev_yoy"] > pd["rev_yoy"]
    else:
        checks["매출 가속"] = d["rev_yoy"] > 20

    # 2. 매출총이익률 방향
    if pd:
        checks["매출총이익률 확대"] = d["gm"] > pd["gm"] or d["gm"] > 55
    else:
        checks["매출총이익률 확대"] = d["gm"] > 45

    # 3. EPS 서프라이즈 > 10%
    checks["어닝 서프라이즈"] = d["eps_beat"] > 10

    # 4. 매출 고성장 > 15%
    checks["매출 고성장"] = d["rev_yoy"] > 15

    # 5. 매출총이익률 양호 > 40%
    checks["매출총이익률 양호"] = d["gm"] > 40

    # 6. ★개선: 매출총이익률 2분기 연속 개선(NVDA 2023-01 누락 해결)
    if pd and pd2:
        checks["매출총이익률 연속 개선"] = d["gm"] > pd["gm"] > pd2["gm"]
    elif pd:
        checks["매출총이익률 연속 개선"] = d["gm"] > pd["gm"]
    else:
        checks["매출총이익률 연속 개선"] = False

    score = sum(1 for v in checks.values() if v)

    # ★개선: 독립 통과 조건
    independent_pass = False
    independent_reason = ""

    # 조건 A: 매출총이익률 2분기 연속 개선 + 매출총이익률 >45%(NVDA 2023-01 상황)
    if checks.get("매출총이익률 연속 개선") and d["gm"] > 45:
        independent_pass = True
        independent_reason = "매출총이익률 연속 개선 + >45%"

    # 조건 B: EPS 서프라이즈 >30%(MU 바닥 상황)
    if d["eps_beat"] > 30:
        independent_pass = True
        independent_reason = "EPS 서프라이즈 >30%(경기순환주 신호)"

    return {
        "score": score,
        "max": 6,
        "checks": checks,
        "fund": d,
        "fund_date": latest[0],
        "fund_label": d.get("label", ""),
        "independent_pass": independent_pass,
        "independent_reason": independent_reason,
    }


# ============================================================
# 신호 등급
# ============================================================

def grade_signal(momentum, value):
    """종합 등급"""
    if not momentum or not momentum["triggered"]:
        return "SKIP", "모멘텀 신호 없음", ""

    if not value:
        return "WATCH", "모멘텀은 발생했으나 펀더멘털 데이터 없음", "펀더멘털 보완"

    score = value["score"]
    ind = value["independent_pass"]

    if score >= 5 or (score >= 4 and ind):
        return "BUY_8%", f"확신 비중({score}/6)", "비중 8% 권장"
    elif score >= 4 or (score >= 3 and ind):
        return "BUY_5%", f"표준 비중({score}/6)", "비중 5% 권장"
    elif score >= 3:
        return "BUY_3%", f"탐색 비중({score}/6)", "비중 3% 권장"
    elif ind:
        return "BUY_3%", f"독립 조건 통과: {value['independent_reason']}", "비중 3% 권장"
    else:
        return "PASS", f"모멘텀은 있으나 펀더멘털 부족({score}/6)", "계속 관찰"


# ============================================================
# 종목 하나 스캔
# ============================================================

def scan_ticker(ticker, verbose=True):
    """단일 종목을 스캔한다"""
    prices = fetch_prices_curl(ticker)
    if not prices:
        if verbose:
            print(f"  {ticker:<8} ⚠️  가격 데이터를 가져올 수 없음")
        return None

    momentum = check_momentum(prices)
    value = check_value(ticker)
    grade, reason, advice = grade_signal(momentum, value)

    result = {
        "ticker": ticker,
        "grade": grade,
        "reason": reason,
        "advice": advice,
        "momentum": momentum,
        "value": value,
    }

    if verbose:
        # 간결한 출력
        m = momentum
        symbol = {"BUY_8%": "🔴", "BUY_5%": "🟡", "BUY_3%": "🟢", "WATCH": "👀", "PASS": "⬜", "SKIP": "  "}
        s = symbol.get(grade, "  ")

        if grade.startswith("BUY"):
            print(f"  {s} {ticker:<8} ${m['close']:<8} 30일 +{m['pct_30d']}% 거래량 {m['vol_ratio']}x  → {grade} {reason}")
            if value:
                v = value
                checks_str = " ".join(f"{'✅' if val else '❌'}{k}" for k, val in v["checks"].items())
                print(f"     펀더멘털({v['fund_label']}): 매출 {v['fund']['rev_yoy']}% 매출총이익률 {v['fund']['gm']}% EPS 서프라이즈 {v['fund']['eps_beat']}%")
                print(f"     {checks_str}")
                if v["independent_pass"]:
                    print(f"     ★독립 통과: {v['independent_reason']}")
        elif grade == "WATCH":
            print(f"  {s} {ticker:<8} ${m['close']:<8} 30일 +{m['pct_30d']}%  → 모멘텀 발생! 펀더멘털 데이터 보완 필요")
        elif grade == "PASS":
            print(f"  {s} {ticker:<8} ${m['close']:<8}  → {reason}")
        # SKIP 은 출력하지 않는다

    return result


# ============================================================
# 메인
# ============================================================

def main():
    _safe_stdio()
    args = sys.argv[1:]

    # 갱신 모드
    if args and args[0] == "--update":
        ticker = args[1] if len(args) > 1 else input("  티커: ").strip().upper()
        update_fundamental_interactive(ticker)
        return

    # 기본 watchlist 초기화
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(DEFAULT_WATCHLIST, f, indent=2)
        print(f"  기본 watchlist 생성: {WATCHLIST_FILE}")

    # 스캔 범위 결정
    if args:
        tickers = [t.upper() for t in args]
    else:
        with open(WATCHLIST_FILE) as f:
            wl = json.load(f)
        tickers = []
        for group, syms in wl.items():
            tickers.extend(syms)

    # 스캔 실행
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*70}")
    print(f"  모멘텀 발견 + 가치 검증 종목 스크리너  {today}")
    print(f"  스캔 범위: {len(tickers)}개 종목")
    print(f"{'='*70}\n")

    buy_signals = []
    watch_signals = []

    for ticker in tickers:
        result = scan_ticker(ticker)
        if result:
            if result["grade"].startswith("BUY"):
                buy_signals.append(result)
            elif result["grade"] == "WATCH":
                watch_signals.append(result)

    # 요약
    print(f"\n{'='*70}")
    print(f"  📋 스캔 결과 요약")
    print(f"{'='*70}")

    if buy_signals:
        print(f"\n  🎯 매수 신호: {len(buy_signals)}개")
        for s in sorted(buy_signals, key=lambda x: x["grade"], reverse=True):
            m = s["momentum"]
            print(f"     {s['grade']:<8} {s['ticker']:<8} ${m['close']:<8} {s['reason']}")
    else:
        print(f"\n  매수 신호 없음")

    if watch_signals:
        print(f"\n  👀 관찰(펀더멘털 보완 필요): {len(watch_signals)}개")
        for s in watch_signals:
            m = s["momentum"]
            print(f"     {s['ticker']:<8} ${m['close']:<8} 30일 +{m['pct_30d']}% | --update {s['ticker']} 로 보완하세요")

    print(f"\n  펀더멘털 데이터 파일: {FUND_FILE}")
    print(f"  Watchlist 파일: {WATCHLIST_FILE}")
    print(f"  --update TICKER 로 펀더멘털을 보완/갱신하세요\n")


if __name__ == "__main__":
    main()

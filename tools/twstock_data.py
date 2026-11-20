#!/usr/bin/env python3
"""대만 주식 데이터 도구 — FinMind 오픈 데이터 API, 외부 의존성 없음(stdlib만 사용).

Claude Code Skills 에 대만 주식 시세, 밸류에이션, 재무, 월 매출 등을 제공한다.
설계 원칙: 독립 모듈로 기존 도구에 영향을 주지 않는다. ashare_data.py 와 같은 스타일.

데이터 출처: FinMind (api.finmindtrade.com). 상장(twse)/장외(tpex, 上櫃) 전 종목을 다룬다.
가입 없이 바로 쓸 수 있다(시간당 요청 한도 있음). 가입 후 받는 API token 으로 한도를 늘릴 수 있으며,
아래 우선순위로 읽는다(token 은 로컬에만 두고 git 에 절대 커밋하지 않는다):
    1. 환경 변수 FINMIND_TOKEN
    2. 로컬 파일 local/finmind_token.txt (local/ 디렉터리는 .gitignore 로 영구 제외됨)

사용법(Skills 가 자동 호출):
    python3 tools/twstock_data.py quote 2330        # 최신 시세 + 밸류에이션 + 시가총액 검산
    python3 tools/twstock_data.py valuation 2330    # PER/PBR/배당수익률 + 52주 고저
    python3 tools/twstock_data.py financials 2330   # 최근 5년 연간 핵심 재무 + 최신 분기
    python3 tools/twstock_data.py revenue 2330      # 최근 13개월 월 매출 및 전년 동기 대비(대만 주식 고유의 월간 공시)
    python3 tools/twstock_data.py dividend 2330     # 최근 수년 배당 정책
    python3 tools/twstock_data.py search 台積        # 종목 코드 검색(번체 종목명/코드 지원, 台積=TSMC)

주의:
    - 모든 금액 단위는 신타이완달러(TWD)
    - FinMind 손익계산서는 단일 분기 값이며, 이 도구가 자동으로 연간 값으로 합산한다
    - Python >= 3.8 필요, 외부 의존성 없음
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

_API = "https://api.finmindtrade.com/api/v4/data"
_TIMEOUT = 30
_TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "local", "finmind_token.txt",
)


def _safe_stdio():
    """콘솔 인코딩(예: Windows cp949)으로 표현할 수 없는 문자(이모지·일부 한자) 때문에 죽지 않게 한다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty() or os.environ.get("PYTHONIOENCODING"):
                stream.reconfigure(errors="replace")
            else:
                # 파이프·리다이렉트 출력은 UTF-8 로 고정한다(중국어 종목명·기호가 '?' 로 뭉개지지 않게)
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _token():
    """FinMind token 을 읽는다: 환경 변수 우선, 다음은 로컬 파일. 둘 다 없으면 익명 접근."""
    t = os.environ.get("FINMIND_TOKEN", "").strip()
    if t:
        return t
    try:
        with open(_TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _get(dataset, data_id=None, start_date=None, end_date=None):
    """FinMind API 를 호출해 data 리스트를 반환한다."""
    params = {"dataset": dataset}
    if data_id:
        params["data_id"] = data_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    token = _token()
    if token:
        params["token"] = token
    url = f"{_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 402, 403) and token:
            raise ConnectionError(
                f"FinMind 가 요청을 거부했습니다(HTTP {e.code}). token 이 무효이거나 만료됐을 가능성이 큽니다. "
                "환경 변수 FINMIND_TOKEN 또는 local/finmind_token.txt 내용을 확인하세요. "
                "token 을 지우면 익명 접근으로 돌아갑니다(시간당 한도 있음)"
            ) from e
        raise ConnectionError(f"FinMind 요청 실패: HTTP {e.code} ({dataset})") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"FinMind 네트워크 요청 실패: {e.reason}") from e
    if payload.get("status") != 200:
        raise ConnectionError(f"FinMind 요청 실패: {payload.get('msg')} ({dataset})")
    return payload.get("data", [])


def _fmt_yi(value):
    """신타이완달러 금액을 억/만 단위로 표시한다."""
    if value is None or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.1f}억"
    if abs(v) >= 1e4:
        return f"{v / 1e4:,.1f}만"
    return f"{v:,.2f}"


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


# FinMind 의 type 값(twse/tpex) → 표시용 시장 구분
_BOARD = {"twse": "상장", "tpex": "장외(上櫃)"}


def _stock_name(stock_id):
    """TaiwanStockInfo 에서 종목명과 시장 구분을 가져온다."""
    try:
        rows = _get("TaiwanStockInfo", data_id=stock_id)
    except Exception:
        return stock_id, ""
    if not rows:
        return stock_id, ""
    board = _BOARD.get(rows[0].get("type", ""), "")
    return rows[0].get("stock_name", stock_id), board


def _latest_shares(stock_id):
    """TaiwanStockShareholding 에서 최신 발행주식수를 가져온다."""
    rows = _get("TaiwanStockShareholding", data_id=stock_id, start_date=_days_ago(14))
    if not rows:
        return None
    return rows[-1].get("NumberOfSharesIssued")


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------

def cmd_quote(stock_id):
    """최신 시세 스냅샷 + 시가총액 검산."""
    name, board = _stock_name(stock_id)
    prices = _get("TaiwanStockPrice", data_id=stock_id, start_date=_days_ago(14))
    if not prices:
        print(f"❌ 종목 {stock_id} 의 시세 데이터를 찾지 못했습니다")
        return
    p = prices[-1]
    prev_close = prices[-2]["close"] if len(prices) >= 2 else None

    pers = _get("TaiwanStockPER", data_id=stock_id, start_date=_days_ago(14))
    per = pers[-1] if pers else {}

    print("=" * 60)
    print(f"대만 주식 시세: {name} ({stock_id}) [{board}]  데이터 출처: FinMind")
    print("=" * 60)
    print(f"  날짜:         {p['date']}")
    print(f"  종가:         {p['close']} TWD")
    if prev_close:
        chg = p["close"] - prev_close
        print(f"  등락:         {chg:+.2f} ({chg / prev_close * 100:+.2f}%)")
    print(f"  시/고/저:     {p['open']} / {p['max']} / {p['min']}")
    print(f"  거래량:       {_fmt_yi(p['Trading_Volume'])}주")
    print(f"  거래대금:     {_fmt_yi(p['Trading_money'])} TWD")
    if per:
        print(f"  PER:          {per.get('PER', '-')}")
        print(f"  PBR:          {per.get('PBR', '-')}")
        print(f"  배당수익률:   {per.get('dividend_yield', '-')}%")

    # 시가총액 검산: 종가 × 발행주식수
    try:
        shares = _latest_shares(stock_id)
        if shares:
            cap = p["close"] * shares
            print(f"\n  발행주식수:   {_fmt_yi(shares)}주")
            print(f"  시가총액:     {_fmt_yi(cap)} TWD (= 종가 {p['close']} × 주식수, 수기 계산 기준)")
    except Exception:
        print("\n  ⚠️ 발행주식수를 가져오지 못했습니다. 시가총액은 따로 검산하세요")


def cmd_valuation(stock_id):
    """밸류에이션 지표 + 52주 고저."""
    name, board = _stock_name(stock_id)
    prices = _get("TaiwanStockPrice", data_id=stock_id, start_date=_days_ago(370))
    if not prices:
        print(f"❌ 종목 {stock_id} 의 시세 데이터를 찾지 못했습니다")
        return
    p = prices[-1]
    high_52w = max(r["max"] for r in prices)
    low_52w = min(r["min"] for r in prices)

    pers = _get("TaiwanStockPER", data_id=stock_id, start_date=_days_ago(370))
    per = pers[-1] if pers else {}
    per_vals = [r["PER"] for r in pers if r.get("PER")]

    print("=" * 60)
    print(f"밸류에이션 지표: {name} ({stock_id}) [{board}]  데이터 출처: FinMind")
    print("=" * 60)
    print(f"  날짜:         {p['date']}")
    print(f"  종가:         {p['close']} TWD")
    print(f"  PER:          {per.get('PER', '-')}")
    if per_vals:
        print(f"  PER 1년 구간: {min(per_vals)} ~ {max(per_vals)}")
    print(f"  PBR:          {per.get('PBR', '-')}")
    print(f"  배당수익률:   {per.get('dividend_yield', '-')}%")
    print(f"  52주 최고:    {high_52w}")
    print(f"  52주 최저:    {low_52w}")

    try:
        shares = _latest_shares(stock_id)
        if shares:
            cap = p["close"] * shares
            print(f"  발행주식수:   {_fmt_yi(shares)}주")
            print(f"  시가총액:     {_fmt_yi(cap)} TWD")
    except Exception:
        pass


# FinMind 손익계산서 type 값 → 한국어 항목명
_IS_KEYS = {
    "Revenue": "매출",
    "GrossProfit": "매출총이익",
    "OperatingIncome": "영업이익",
    "EquityAttributableToOwnersOfParent": "지배주주 순이익",
    "EPS": "EPS",
}


def cmd_financials(stock_id):
    """최근 5년 연간 핵심 재무(단일 분기 합산) + 연말 자본으로 추산한 ROE."""
    name, board = _stock_name(stock_id)
    start = f"{date.today().year - 5}-01-01"
    rows = _get("TaiwanStockFinancialStatements", data_id=stock_id, start_date=start)
    if not rows:
        print(f"❌ 종목 {stock_id} 의 재무 데이터를 찾지 못했습니다")
        return

    # 연도별로 단일 분기 값을 합산: {year: {지표: 누계}}, 분기 수도 기록
    years = {}
    for r in rows:
        if r["type"] not in _IS_KEYS:
            continue
        y = r["date"][:4]
        d = years.setdefault(y, {"_quarters": set()})
        d["_quarters"].add(r["date"])
        d[r["type"]] = d.get(r["type"], 0) + (r["value"] or 0)

    # 연말 지배주주 자본(Q4 재무상태표). 간이 ROE 계산에 쓴다
    equity_by_year = {}
    try:
        bs = _get("TaiwanStockBalanceSheet", data_id=stock_id, start_date=start)
        for r in bs:
            if r["type"] == "EquityAttributableToOwnersOfParent" and r["date"][5:7] == "12":
                equity_by_year[r["date"][:4]] = r["value"]
    except Exception:
        pass

    print("=" * 60)
    print(f"핵심 재무 데이터: {name} ({stock_id}) [{board}]  데이터 출처: FinMind")
    print("=" * 60)
    print("  단위: TWD. FinMind 손익계산서는 단일 분기 값이며, 아래는 연간 합산이다.")

    for y in sorted(years, reverse=True):
        d = years[y]
        nq = len(d["_quarters"])
        suffix = "" if nq == 4 else f"(앞 {nq}개 분기 누계만, 연간 아님)"
        rev = d.get("Revenue")
        gp = d.get("GrossProfit")
        op = d.get("OperatingIncome")
        ni = d.get("EquityAttributableToOwnersOfParent")
        eps = d.get("EPS")
        print(f"\n  --- {y}년 {suffix} ---")
        if rev:
            print(f"  매출:             {_fmt_yi(rev)}")
        if gp and rev:
            print(f"  매출총이익률:     {gp / rev * 100:.1f}%")
        if op and rev:
            print(f"  영업이익률:       {op / rev * 100:.1f}%")
        if ni:
            print(f"  지배주주 순이익:  {_fmt_yi(ni)}")
        if ni and rev:
            print(f"  순이익률:         {ni / rev * 100:.1f}%")
        if eps:
            print(f"  EPS:              {eps:.2f}")
        eq = equity_by_year.get(y)
        if eq and ni and nq == 4:
            print(f"  ROE(간이):        {ni / eq * 100:.1f}% (지배주주 순이익/연말 지배주주 자본, 기초·기말 평균 아님)")


def cmd_revenue(stock_id):
    """최근 13개월 월 매출 및 전년 동기 대비 — 대만 주식 고유의 월간 공시로 펀더멘털 변곡점을 추적한다."""
    name, board = _stock_name(stock_id)
    rows = _get("TaiwanStockMonthRevenue", data_id=stock_id, start_date=_days_ago(800))
    if not rows:
        print(f"❌ 종목 {stock_id} 의 월 매출 데이터를 찾지 못했습니다")
        return

    by_month = {(r["revenue_year"], r["revenue_month"]): r["revenue"] for r in rows}

    print("=" * 60)
    print(f"월 매출: {name} ({stock_id}) [{board}]  데이터 출처: FinMind")
    print("=" * 60)
    print("  단위: TWD (대만 주식은 매월 10일 이전에 전월 매출을 의무 공시한다)")
    print(f"\n  {'월':<10}{'매출':>14}{'전년 동기 대비':>10}")

    keys = sorted(by_month)[-13:]
    for y, m in keys:
        rev = by_month[(y, m)]
        prev = by_month.get((y - 1, m))
        yoy = f"{(rev / prev - 1) * 100:+.1f}%" if prev else "-"
        print(f"  {y}-{m:02d}   {_fmt_yi(rev):>14}{yoy:>10}")


def cmd_dividend(stock_id):
    """최근 수년 배당 정책."""
    name, board = _stock_name(stock_id)
    start = f"{date.today().year - 5}-01-01"
    rows = _get("TaiwanStockDividend", data_id=stock_id, start_date=start)
    if not rows:
        print(f"❌ 종목 {stock_id} 의 배당 데이터를 찾지 못했습니다")
        return

    print("=" * 60)
    print(f"배당 정책: {name} ({stock_id}) [{board}]  데이터 출처: FinMind")
    print("=" * 60)
    print("  단위: TWD/주 (대만 주식은 분기 배당이 흔하므로 연간 배당은 직접 합산해야 한다)")
    print(f"\n  {'귀속 기간':<12}{'현금배당':>8}{'주식배당':>8}  {'배당락일':<12}{'지급일':<12}")

    for r in rows:
        cash = (r.get("CashEarningsDistribution") or 0) + (r.get("CashStatutorySurplus") or 0)
        stock = (r.get("StockEarningsDistribution") or 0) + (r.get("StockStatutorySurplus") or 0)
        if not cash and not stock:
            continue
        ex_date = r.get("CashExDividendTradingDate") or "-"
        pay_date = r.get("CashDividendPaymentDate") or "-"
        # year 는 FinMind 가 돌려주는 값 그대로(민국 연호·분기 표기일 수 있음)
        print(f"  {r.get('year', ''):<12}{cash:>8.2f}{stock:>8.2f}  {ex_date:<12}{pay_date:<12}")


def cmd_search(keyword):
    """종목명/코드로 대만 주식을 검색한다(TaiwanStockInfo 전체 표 필터링)."""
    rows = _get("TaiwanStockInfo")
    seen = {}
    for r in rows:
        if keyword in r.get("stock_name", "") or keyword == r.get("stock_id", ""):
            sid = r["stock_id"]
            if sid not in seen:
                seen[sid] = {
                    "name": r["stock_name"],
                    "type": r.get("type", ""),
                    "industries": [],
                }
            cat = r.get("industry_category", "")
            if cat and cat not in seen[sid]["industries"]:
                seen[sid]["industries"].append(cat)

    if not seen:
        # 台積電(TSMC)은 FinMind 종목명과 맞춰야 하는 검색어 예시라 번체 그대로 둔다
        print(f"❌ '{keyword}' 와(과) 일치하는 대만 주식을 찾지 못했습니다(힌트: 대만 종목명은 대부분 번체자다. 예: 台積電)")
        return

    print("=" * 60)
    print(f"대만 주식 검색 결과: '{keyword}'  데이터 출처: FinMind")
    print("=" * 60)
    for sid, d in sorted(seen.items()):
        board = _BOARD.get(d["type"], d["type"])
        cats = "/".join(d["industries"][:3])
        print(f"  {sid} {d['name']} [{board}] {cats}")


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def main():
    _safe_stdio()
    parser = argparse.ArgumentParser(
        description="대만 주식 데이터 도구 - FinMind 오픈 데이터 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    for cmd, help_text in [
        ("quote", "최신 시세 + 시가총액 검산"),
        ("valuation", "밸류에이션 지표(PER/PBR/배당수익률/52주 고저)"),
        ("financials", "최근 5년 연간 핵심 재무"),
        ("revenue", "최근 13개월 월 매출 및 전년 동기 대비"),
        ("dividend", "최근 수년 배당 정책"),
    ]:
        p = sub.add_parser(cmd, help=help_text)
        p.add_argument("stock_id", help="종목 코드(예: 2330)")

    p_search = sub.add_parser("search", help="종목 코드 검색")
    p_search.add_argument("keyword", help="회사명(번체자) 또는 코드")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "search":
            cmd_search(args.keyword)
        else:
            {
                "quote": cmd_quote,
                "valuation": cmd_valuation,
                "financials": cmd_financials,
                "revenue": cmd_revenue,
                "dividend": cmd_dividend,
            }[args.command](args.stock_id)
    except BrokenPipeError:
        # 출력이 파이프에서 잘린 경우(예: | head) 조용히 종료한다.
        # 주의: BrokenPipeError 는 ConnectionError 의 하위 클래스이므로 반드시 먼저 잡아야 한다
        sys.stderr.close()
        sys.exit(0)
    except ConnectionError as e:
        print(f"❌ {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()

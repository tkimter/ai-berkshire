#!/usr/bin/env python3
"""A주 데이터 도구 — 텐센트 시세(腾讯行情) + 둥팡차이푸(东方财富) 검색/재무, 외부 의존성 없음(stdlib만 사용).

Claude Code Skills 에 A주 실시간 시세, 재무 데이터 등을 제공한다.
설계 원칙: 독립 모듈로 기존 도구에 영향을 주지 않는다. curl 직접 연결로 시스템 프록시를 우회한다.

사용법(Skills 가 자동 호출):
    python3.11 tools/ashare_data.py quote 600519                    # 실시간 시세
    python3.11 tools/ashare_data.py financials 600519               # 핵심 재무 데이터(최근 5년)
    python3.11 tools/ashare_data.py valuation 600519                # 밸류에이션 지표
    python3.11 tools/ashare_data.py search 茅台                      # 종목 코드 검색(검색어는 중국어 종목명 그대로: 茅台=마오타이)

Python >= 3.8 필요, 외부 의존성 없음.
"""

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_EVEN

_TIMEOUT = 15


def _safe_stdio():
    """콘솔 인코딩(예: Windows cp949)으로 표현할 수 없는 문자(이모지·간체자) 때문에 죽지 않게 한다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty() or os.environ.get("PYTHONIOENCODING"):
                stream.reconfigure(errors="replace")
            else:
                # 파이프·리다이렉트 출력은 UTF-8 로 고정한다(중국어 종목명·기호가 '?' 로 뭉개지지 않게)
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _curl(url):
    """curl --noproxy 로 직접 연결해 시스템 프록시를 우회한다."""
    result = subprocess.run(
        ["/usr/bin/curl", "-s", "--noproxy", "*",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"요청 실패: {url}")
    # 텐센트 시세 API 는 GBK 인코딩으로, 나머지는 UTF-8 로 응답한다
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return result.stdout.decode("gbk")


def _curl_json(url, params=None):
    """curl 로 JSON 을 가져온다."""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    return json.loads(_curl(url))


# ---------------------------------------------------------------------------
# 텐센트 시세 API(안정적이며 인증 불필요)
# ---------------------------------------------------------------------------

def _qq_code(code: str) -> str:
    """종목 코드를 텐센트 시세 형식으로 바꾼다."""
    code = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if code.startswith(("6", "9", "5")):
        return f"sh{code}"
    elif code.startswith(("0", "3", "2", "1")):
        return f"sz{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sh{code}"


def _parse_qq_quote(raw: str) -> dict:
    """텐센트 시세 데이터를 파싱한다. 형식: v_shXXXXXX="필드1~필드2~..."; """
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        return {}
    fields = raw[start + 1:end].split("~")
    if len(fields) < 50:
        return {}
    return {
        "name": fields[1],
        "code": fields[2],
        "price": fields[3],
        "prev_close": fields[4],
        "open": fields[5],
        "volume": fields[6],         # 단위: 手(1手 = 100주)
        "buy_vol": fields[7],
        "sell_vol": fields[8],
        "high": fields[33] if len(fields) > 33 else fields[3],
        "low": fields[34] if len(fields) > 34 else fields[3],
        "change_pct": fields[32],
        "change_amt": fields[31],
        "turnover_amt": fields[37] if len(fields) > 37 else "-",
        "turnover_rate": fields[38] if len(fields) > 38 else "-",
        "pe": fields[39] if len(fields) > 39 else "-",
        "market_cap": fields[45] if len(fields) > 45 else "-",    # 시가총액(억 위안)
        "float_cap": fields[44] if len(fields) > 44 else "-",     # 유통 시가총액(억 위안)
        "pb": fields[46] if len(fields) > 46 else "-",
        # 주의: 텐센트 ~ 구분 프로토콜의 47/48번째 필드는 당일 상한가/하한가이며 52주 고저가 아니다(issue #70)
        "limit_up": fields[47] if len(fields) > 47 else "-",
        "limit_down": fields[48] if len(fields) > 48 else "-",
        "total_shares": fields[38] if len(fields) > 38 else "-",  # will recalculate
    }


def _em_secid(code: str) -> str:
    """종목 코드를 둥팡차이푸 secid 형식으로 바꾼다: 상하이는 접두 1., 선전/베이징거래소는 접두 0."""
    code = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if code.startswith(("6", "9", "5")):
        return f"1.{code}"
    return f"0.{code}"


def _fetch_52w(code: str) -> tuple:
    """둥팡차이푸에서 52주 최고/최저(f174/f175)를 가져온다.

    텐센트 시세 프로토콜에는 이 데이터가 없다. push2delay 를 우선 사용하고(메인 push2 는
    연속 요청 제한이 엄격하며, 52주 고저는 지연 시세의 영향을 받지 않는다) 실패하면 push2 로
    되돌아간다. 가져오지 못하면 ("-", "-") 를 반환한다.
    """
    secid = _em_secid(code)
    query = f"api/qt/stock/get?secid={secid}&fields=f174,f175&invt=2&fltt=2"
    for host in ("push2delay.eastmoney.com", "push2.eastmoney.com"):
        try:
            data = _curl_json(f"https://{host}/{query}").get("data") or {}
            high, low = data.get("f174"), data.get("f175")
            if high not in (None, "-") and low not in (None, "-"):
                return high, low
        except Exception:
            continue
    return "-", "-"


def _fmt_yi(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}억"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}만"
    return f"{v:.2f}"


def _fmt_pct(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------

def cmd_quote(code: str):
    """실시간 시세 스냅샷."""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 종목 {code} 을(를) 찾지 못했습니다")
        return

    print("=" * 60)
    print(f"실시간 시세: {d['name']} ({d['code']})")
    print("=" * 60)
    print(f"  현재가:       {d['price']}")
    print(f"  등락률:       {d['change_pct']}%")
    print(f"  등락액:       {d['change_amt']}")
    print(f"  시가:         {d['open']}")
    print(f"  고가:         {d['high']}")
    print(f"  저가:         {d['low']}")
    print(f"  전일 종가:    {d['prev_close']}")
    print(f"  거래량:       {d['volume']} 手(1手=100주)")
    print(f"  거래대금:     {d['turnover_amt']}만")
    print(f"  시가총액:     {d['market_cap']}억")
    print(f"  유통 시총:    {d['float_cap']}억")
    print(f"  PE(동적):     {d['pe']}")
    print(f"  PB:           {d['pb']}")
    print(f"  회전율:       {d['turnover_rate']}%")
    high_52w, low_52w = _fetch_52w(code)
    print(f"  52주 최고:    {high_52w}")
    print(f"  52주 최저:    {low_52w}")


def cmd_valuation(code: str):
    """밸류에이션 지표 요약."""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 종목 {code} 을(를) 찾지 못했습니다")
        return

    price = d["price"]
    market_cap_yi = d["market_cap"]

    print("=" * 60)
    print(f"밸류에이션 지표: {d['name']} ({d['code']})")
    print("=" * 60)
    print(f"  현재가:       {price}")
    print(f"  시가총액:     {market_cap_yi}억")
    print(f"  유통 시총:    {d['float_cap']}억")
    print(f"  PE(동적):     {d['pe']}")
    print(f"  PB:           {d['pb']}")
    high_52w, low_52w = _fetch_52w(code)
    print(f"  52주 최고:    {high_52w}")
    print(f"  52주 최저:    {low_52w}")

    # 시가총액 검산
    try:
        p = Decimal(price)
        cap = Decimal(market_cap_yi) * Decimal("1e8")
        shares = cap / p
        print(f"\n  추산 총주식수: {_fmt_yi(float(shares))}주")
        calc_cap = p * shares
        reported_cap = Decimal(market_cap_yi) * Decimal("1e8")
        diff = abs(calc_cap - reported_cap) / reported_cap * 100
        print(f"  시총 검산:     ✅ 일치(역산 방식, 편차 {float(diff):.1f}%)")
    except Exception:
        pass


def cmd_financials(code: str):
    """최근 5년 핵심 재무 데이터."""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    name = d.get("name", code) if d else code

    code_clean = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    market = "SH" if code_clean.startswith(("6", "9", "5")) else "SZ"

    # 둥팡차이푸 datacenter API(연간 보고서 데이터)
    fin_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "ALL",
        # "年报"(연간 보고서)는 API 필터 값이므로 중국어 그대로 둔다
        "filter": f'(SECUCODE="{code_clean}.{market}")(REPORT_TYPE="年报")',
        "p": "1",
        "ps": "5",
        "sr": "-1",
        "st": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    reports = []
    try:
        data = _curl_json(fin_url, params)
        reports = data.get("result", {}).get("data", [])
    except Exception:
        pass

    # 연간 보고서 필터로 결과가 없으면 그 제한을 뺀다
    if not reports:
        params["filter"] = f'(SECUCODE="{code_clean}.{market}")'
        try:
            data = _curl_json(fin_url, params)
            reports = data.get("result", {}).get("data", [])
        except Exception:
            pass

    print("=" * 60)
    print(f"핵심 재무 데이터: {name} ({code_clean})")
    print("=" * 60)

    if not reports:
        print("  ⚠️ 재무 데이터를 가져오지 못했습니다. WebSearch 로 보완하세요")
        return

    for r in reports[:5]:
        date = r.get("REPORT_DATE", "")[:10]
        report_name = r.get("REPORT_DATE_NAME", "")  # API 가 돌려주는 중국어 값(예: 2024年报)
        revenue = r.get("TOTALOPERATEREVE")
        net_profit = r.get("PARENTNETPROFIT")
        eps = r.get("EPSJB")
        bps = r.get("BPS")
        roe = r.get("ROEJQ")
        rev_growth = r.get("TOTALOPERATEREVETZ")
        profit_growth = r.get("PARENTNETPROFITTZ")

        print(f"\n  --- {date} {report_name} ---")
        if revenue is not None:
            print(f"  매출:               {_fmt_yi(revenue)}")
        if rev_growth is not None:
            print(f"  매출 증가율:        {_fmt_pct(rev_growth)}")
        if net_profit is not None:
            print(f"  지배주주 순이익:    {_fmt_yi(net_profit)}")
        if profit_growth is not None:
            print(f"  순이익 증가율:      {_fmt_pct(profit_growth)}")
        if eps is not None:
            print(f"  기본 EPS:           {eps}")
        if bps is not None:
            print(f"  주당 순자산(BPS):   {bps:.2f}")
        if roe is not None:
            print(f"  ROE(가중):          {_fmt_pct(roe)}")


def cmd_search(keyword: str):
    """종목 코드 검색."""
    url = "https://searchadapter.eastmoney.com/api/suggest/get"
    # Use env var or fall back to the public eastmoney search token
    token = os.environ.get("EASTMONEY_SEARCH_TOKEN") or "D43BF722C8E33BDC906FB84D85E326E8"
    params = {
        "input": keyword,
        "type": "14",
        "token": token,
        "count": "10",
    }
    data = _curl_json(url, params)
    results = data.get("QuotationCodeTable", {}).get("Data", [])

    if not results:
        print(f"❌ '{keyword}' 와(과) 일치하는 종목을 찾지 못했습니다")
        return

    print("=" * 60)
    print(f"검색 결과: '{keyword}'")
    print("=" * 60)
    for r in results:
        code = r.get("Code", "")
        name = r.get("Name", "")
        market = r.get("MktNum", "")
        mkt_label = {"1": "상하이", "2": "선전", "3": "베이징"}.get(str(market), "")
        print(f"  {code} {name} [{mkt_label}]")


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def main():
    _safe_stdio()
    parser = argparse.ArgumentParser(
        description="A주 데이터 도구 - 텐센트 시세 + 둥팡차이푸 재무 데이터",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_quote = sub.add_parser("quote", help="실시간 시세")
    p_quote.add_argument("code", help="종목 코드(예: 600519)")

    p_fin = sub.add_parser("financials", help="핵심 재무 데이터(최근 5년)")
    p_fin.add_argument("code", help="종목 코드")

    p_val = sub.add_parser("valuation", help="밸류에이션 지표")
    p_val.add_argument("code", help="종목 코드")

    p_search = sub.add_parser("search", help="종목 코드 검색")
    p_search.add_argument("keyword", help="회사명(중국어) 또는 키워드")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "quote": lambda: cmd_quote(args.code),
        "financials": lambda: cmd_financials(args.code),
        "valuation": lambda: cmd_valuation(args.code),
        "search": lambda: cmd_search(args.keyword),
    }
    cmds[args.command]()


if __name__ == "__main__":
    main()

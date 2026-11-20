#!/usr/bin/env python3
"""
Morningstar 스크리너 API 에서 공정가치 추정치가 있는 모든 종목을 가져와
잠재 상승률을 계산하고 Top 100 을 출력한다.
"""

import json
import subprocess
import sys
import time
import csv
import os
from datetime import datetime

API_BASE = (
    "https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener"
    "?page={page}&pageSize={page_size}"
    "&sortOrder=FairValueEstimate%20desc"
    "&outputType=json&version=1"
    "&languageId=en-US&currencyId=USD"
    "&universeIds=E0EXG%24XNAS%7CE0EXG%24XNYS"
    "&securityDataPoints=SecId%7CName%7CPriceCurrency%7CTenforeId%7CClosePrice"
    "%7CStarRatingM255%7CQuantitativeFairValue%7CFairValueEstimate"
    "%7CAssessmentOfFairValueUncertainty%7CEconomicMoat%7CIndustryName%7CSectorName"
    "&filters=FairValueEstimate:notnull"
)

PAGE_SIZE = 100
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


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


def fetch_page(page: int) -> dict:
    url = API_BASE.format(page=page, page_size=PAGE_SIZE)
    result = subprocess.run(
        ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def extract_ticker(tenforeid: str) -> str:
    if not tenforeid:
        return ""
    parts = tenforeid.split(".")
    return parts[-1] if len(parts) >= 3 else tenforeid


def main():
    _safe_stdio()
    print(f"\n{'='*80}")
    print(f"  Morningstar 공정가치 스크리닝  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}\n")

    # 첫 페이지에서 전체 건수를 얻는다
    print("  1페이지 가져오는 중...")
    data = fetch_page(1)
    total = data.get("total", 0)
    all_rows = data.get("rows", [])
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f"  총 {total}개 종목, {total_pages}페이지\n")

    # 나머지 페이지 수집
    for page in range(2, total_pages + 1):
        if page % 10 == 0 or page == total_pages:
            print(f"  {page}/{total_pages}페이지 가져오는 중...")
        try:
            data = fetch_page(page)
            rows = data.get("rows", [])
            if not rows:
                break
            all_rows.extend(rows)
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️  {page}페이지 실패: {e}")
            time.sleep(1)

    print(f"\n  총 {len(all_rows)}건 수집")

    # 잠재 상승률 계산
    stocks = []
    for row in all_rows:
        fair_value = row.get("FairValueEstimate")
        close_price = row.get("ClosePrice")
        if not fair_value or not close_price or close_price <= 0:
            continue

        ticker = extract_ticker(row.get("TenforeId", ""))
        upside = (fair_value - close_price) / close_price * 100

        stocks.append({
            "ticker": ticker,
            "name": row.get("Name", ""),
            "close_price": round(close_price, 2),
            "fair_value": round(fair_value, 2),
            "upside_pct": round(upside, 1),
            "star_rating": row.get("StarRatingM255", ""),
            "moat": row.get("EconomicMoat", ""),
            "uncertainty": row.get("AssessmentOfFairValueUncertainty", ""),
            "sector": row.get("SectorName", ""),
            "industry": row.get("IndustryName", ""),
        })

    # 잠재 상승률 순으로 정렬
    stocks.sort(key=lambda x: x["upside_pct"], reverse=True)

    # Top 100 출력
    print(f"\n{'='*80}")
    print(f"  잠재 상승률 Top 100")
    print(f"{'='*80}\n")
    print(f"  {'순위':>4} {'티커':<8} {'회사명':<35} {'현재가':>10} {'공정가치':>10} {'잠재 상승률':>8} {'별점':>4} {'해자':<8} {'산업':<20}")
    print(f"  {'-'*4} {'-'*8} {'-'*35} {'-'*10} {'-'*10} {'-'*8} {'-'*4} {'-'*8} {'-'*20}")

    for i, s in enumerate(stocks[:100], 1):
        print(
            f"  {i:>4} {s['ticker']:<8} {s['name'][:35]:<35} "
            f"${s['close_price']:>9,.2f} ${s['fair_value']:>9,.2f} "
            f"{s['upside_pct']:>+7.1f}% "
            f"{'★'*int(s['star_rating']) if s['star_rating'] else 'N/A':>4} "
            f"{s['moat']:<8} {s['industry'][:20]:<20}"
        )

    # 전체 데이터를 CSV 로 저장
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    csv_path = os.path.join(OUTPUT_DIR, f"morningstar_fair_value_{today}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rank", "ticker", "name", "close_price", "fair_value",
            "upside_pct", "star_rating", "moat", "uncertainty", "sector", "industry"
        ])
        writer.writeheader()
        for i, s in enumerate(stocks, 1):
            writer.writerow({"rank": i, **s})

    print(f"\n  전체 데이터 저장 위치: {csv_path}")
    print(f"  총 {len(stocks)}개 종목(잠재 상승률 순)\n")

    # 통계 요약
    undervalued = [s for s in stocks if s["upside_pct"] > 0]
    overvalued = [s for s in stocks if s["upside_pct"] < 0]
    print(f"  📊 통계 요약:")
    print(f"     저평가 종목: {len(undervalued)}개 ({len(undervalued)/len(stocks)*100:.0f}%)")
    print(f"     고평가 종목: {len(overvalued)}개 ({len(overvalued)/len(stocks)*100:.0f}%)")
    if undervalued:
        avg_upside = sum(s["upside_pct"] for s in undervalued) / len(undervalued)
        print(f"     저평가 종목 평균 잠재 상승률: +{avg_upside:.1f}%")
    if stocks:
        wide_moat_undervalued = [s for s in stocks if s["moat"] == "Wide" and s["upside_pct"] > 0]
        print(f"     넓은 해자 + 저평가: {len(wide_moat_undervalued)}개")


if __name__ == "__main__":
    main()

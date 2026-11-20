#!/usr/bin/env python3
"""star-history.com 과 완전히 같은 모양의 star 증가 곡선 SVG 를 생성한다(라이트/다크 두 버전).

배경: GitHub 가 stargazers 데이터를 저장소 관리자/협업자만 읽을 수 있게 제한하면서 star-history.com
같은 서드파티 차트 서비스가 익명으로 데이터를 가져올 수 없게 됐고, README 의 외부 링크 차트가
깨졌다. 이 스크립트는 저장소 자체 토큰으로 데이터를 가져와 star-history 오픈소스 렌더러
(star-history/star-history 저장소의 shared/packages/xy-chart.tsx 및 utils/)의 SVG 출력을
항목별로 재현한다: xkcd 손그림 필터, monotone 곡선, 내장 폰트, 저장소 아바타가 붙은 제목,
좌상단 범례, 우하단 워터마크.

데이터 출처: GitHub REST API stargazers(Accept: application/vnd.github.star+json,
starred_at 타임스탬프 포함). 페이지 단위로 균등 샘플링한다(페이지당 100건, 각 페이지 첫 건의
타임스탬프만으로 누적 곡선을 정확히 복원할 수 있다).

사용법:
    GITHUB_TOKEN=$(gh auth token) python3 tools/star_history_chart.py

필요한 소재(star-history 오픈소스 저장소에서 추출, 이 저장소에 함께 커밋):
    tools/xkcd.woff              — xkcd 손글씨 폰트
    tools/star-history-logo.png  — 우하단 워터마크 아이콘

출력: assets/star-history.svg 와 assets/star-history-dark.svg
"""

import base64
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = "xbtlin/ai-berkshire"
API = "https://api.github.com"
MAX_SAMPLE_PAGES = 36  # 샘플링 페이지 수 상한. 곡선이 충분히 매끄럽고 요청량도 통제 가능

# 레이아웃·배색 상수는 모두 star-history 렌더러 소스에서 가져왔다
WIDTH = 800
HEIGHT = 800 * 2 / 3
M_TOP, M_RIGHT, M_BOTTOM, M_LEFT = 60, 30, 50, 70  # 제목이 있을 때 top=60
CHART_W = WIDTH - M_LEFT - M_RIGHT
CHART_H = HEIGHT - M_TOP - M_BOTTOM

THEMES = {
    "": {"bg": "white", "stroke": "black", "line": "#dd4528"},
    "-dark": {"bg": "#0d1117", "stroke": "white", "line": "#ff6b6b"},
}

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MONTHS_ABBR = [m[:3] for m in MONTHS]
WEEKDAYS_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def gh_get(path, accept="application/vnd.github+json", raw=False):
    req = urllib.request.Request(path if path.startswith("http") else API + path)
    req.add_header("Accept", accept)
    req.add_header("User-Agent", "star-history-chart")
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and not path.startswith("https://avatars."):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return data if raw else json.loads(data)


def fetch_points():
    repo = gh_get(f"/repos/{REPO}")
    total = repo["stargazers_count"]
    if total == 0:
        sys.exit("저장소에 star 가 없어 차트를 생성할 필요가 없습니다")

    last_page = math.ceil(total / 100)
    n = min(last_page, MAX_SAMPLE_PAGES)
    pages = sorted({round(1 + (last_page - 1) * i / (n - 1)) for i in range(n)}) if n > 1 else [1]

    points = []
    for p in pages:
        data = gh_get(
            f"/repos/{REPO}/stargazers?per_page=100&page={p}",
            accept="application/vnd.github.star+json",
        )
        if data:
            t = datetime.fromisoformat(data[0]["starred_at"].replace("Z", "+00:00"))
            points.append((t, (p - 1) * 100 + 1))
    points.append((datetime.now(timezone.utc), total))
    points.sort()
    # star-history 의 insertZeroPoint: 첫 star 하루 전에 0 지점을 추가
    points.insert(0, (points[0][0] - timedelta(days=1), 0))
    # x 는 엄격히 증가해야 한다(monotone 곡선의 요건). 같은 시각의 중복 샘플을 제거
    dedup = [points[0]]
    for t, v in points[1:]:
        if t > dedup[-1][0]:
            dedup.append((t, v))
    return dedup, total, repo["owner"]["avatar_url"]


def fmt(x):
    """JS 숫자 직렬화를 흉내 낸다: 정수는 소수점 없이, 부동소수는 전체 정밀도로."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return repr(x) if isinstance(x, float) else str(x)


def sign(x):
    return -1.0 if x < 0 else (1.0 if x > 0 else 0.0)


def monotone_x_path(pts):
    """d3-shape curveMonotoneX 의 베지어 경로 출력을 재현한다."""

    def slope3(x0, y0, x1, y1, x2, y2):
        h0, h1 = x1 - x0, x2 - x1
        s0 = (y1 - y0) / h0 if h0 else 0.0
        s1 = (y2 - y1) / h1 if h1 else 0.0
        p = (s0 * h1 + s1 * h0) / (h0 + h1) if h0 + h1 else 0.0
        return (sign(s0) + sign(s1)) * min(abs(s0), abs(s1), 0.5 * abs(p))

    def slope2(x0, y0, x1, y1, t):
        h = x1 - x0
        return (3 * (y1 - y0) / h - t) / 2 if h else t

    def bezier(x0, y0, x1, y1, t0, t1):
        dx = (x1 - x0) / 3
        return (f"C{fmt(x0 + dx)},{fmt(y0 + dx * t0)},"
                f"{fmt(x1 - dx)},{fmt(y1 - dx * t1)},{fmt(x1)},{fmt(y1)}")

    n = len(pts)
    path = f"M{fmt(pts[0][0])},{fmt(pts[0][1])}"
    if n == 1:
        return path
    if n == 2:
        return path + f"L{fmt(pts[1][0])},{fmt(pts[1][1])}"

    t0 = 0.0
    for i in range(2, n):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 2], pts[i - 1], pts[i]
        t1 = slope3(x0, y0, x1, y1, x2, y2)
        path += bezier(x0, y0, x1, y1,
                       slope2(x0, y0, x1, y1, t1) if i == 2 else t0, t1)
        t0 = t1
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    path += bezier(x0, y0, x1, y1, t0, slope2(x0, y0, x1, y1, t0))
    return path


def linear_ticks(stop, count=5):
    """d3.ticks(0, stop, count) 를 재현한다."""
    step = stop / count
    power = math.floor(math.log10(step))
    error = step / 10 ** power
    factor = 10 if error >= math.sqrt(50) else 5 if error >= math.sqrt(10) else 2 if error >= math.sqrt(2) else 1
    step = factor * 10 ** power
    return [step * i for i in range(int(stop // step) + 1)]


def time_ticks(t0, t1, count=5):
    """d3 scaleTime.ticks 를 재현한다: 구간 길이에 따라 일/2일/주/월/3개월/연 간격을 고른다."""
    span = (t1 - t0).total_seconds() * 1000
    target = span / count
    day = 864e5
    intervals = [("day", 1, day), ("day", 2, 2 * day), ("week", 1, 7 * day),
                 ("month", 1, 30 * day), ("month", 3, 90 * day), ("year", 1, 365 * day)]
    choice = intervals[-1]
    for i, iv in enumerate(intervals):
        if target <= iv[2]:
            if i > 0 and target / intervals[i - 1][2] < iv[2] / target:
                choice = intervals[i - 1]
            else:
                choice = iv
            break
    unit, step, _ = choice

    ticks = []
    if unit == "year":
        years = [y for y in linear_ticks(t1.year, count) if y >= t0.year]
        for y in years or range(t0.year + 1, t1.year + 1):
            t = datetime(int(y), 1, 1, tzinfo=timezone.utc)
            if t0 <= t <= t1:
                ticks.append(t)
    elif unit == "month":
        y, m = t0.year, t0.month
        while True:
            m += 1
            if m > 12:
                y, m = y + 1, 1
            if unit == "month" and step == 3 and (m - 1) % 3 != 0:
                continue
            t = datetime(y, m, 1, tzinfo=timezone.utc)
            if t > t1:
                break
            if t >= t0:
                ticks.append(t)
    elif unit == "week":
        # d3 timeWeek 는 일요일을 경계로 한다
        start = (t0 + timedelta(days=(6 - t0.weekday()) % 7 or 7)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        t = start
        while t <= t1:
            if t >= t0:
                ticks.append(t)
            t += timedelta(weeks=1)
    else:
        start = t0.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        t = start
        while t <= t1:
            ticks.append(t)
            t += timedelta(days=step)
    return ticks


def time_tick_label(t):
    """d3 기본 시간 다단계 형식을 재현한다: 연초→%Y, 월초→%B, 일요일→%b %d, 그 외→%a %d."""
    if t.month == 1 and t.day == 1:
        return str(t.year)
    if t.day == 1:
        return MONTHS[t.month - 1]
    if t.weekday() == 6:
        return f"{MONTHS_ABBR[t.month - 1]} {t.day:02d}"
    return f"{WEEKDAYS_ABBR[t.weekday()]} {t.day:02d}"


def number_tick_label(v, unit):
    """star-history getFormatNumber 를 재현한다."""
    if unit == 1:
        return fmt(float(v))
    div, suffix = (1e6, "M") if unit == 1000000 else (1e3, "K")
    if v >= div and v % div == 0:
        return f"{int(v / div)}{suffix}"
    return f"{v / div:.1f}{suffix}"


def render(points, total, theme, font_b64, logo_b64, avatar_b64, avatar_mime):
    t0, t1 = points[0][0], points[-1][0]
    span = (t1 - t0).total_seconds()

    def x(t):
        return CHART_W * (t - t0).total_seconds() / span

    def y(v):
        return CHART_H * (1 - v / total)

    stroke, bg, line_color = theme["stroke"], theme["bg"], theme["line"]

    # X 축(d3 axisBottom, tickSize 0, tickPadding 6, 눈금 위치 +0.5)
    xticks = "".join(
        f'<g class="tick" opacity="1" transform="translate({fmt(x(t) + 0.5)},0)">'
        f'<line stroke="currentColor" y2="0"></line>'
        f'<text fill="currentColor" y="6" dy="0.71em" '
        f'style="font-family: xkcd; font-size: 16px; fill: {stroke};">{time_tick_label(t)}</text></g>'
        for t in time_ticks(t0, t1)
    )
    xaxis = (
        f'<g class="xaxis" transform="translate(0,{fmt(CHART_H)})" fill="none" '
        f'font-size="10" font-family="sans-serif" text-anchor="middle">'
        f'<path class="domain" stroke="currentColor" d="M0.5,0.5H{fmt(CHART_W + 0.5)}" '
        f'filter="url(#xkcdify)" style="stroke: {stroke};"></path>{xticks}</g>'
    )

    # Y 축(d3 axisLeft, tickSize 1, tickPadding 6. 0 눈금은 공백으로 표시)
    yvals = linear_ticks(total)
    first = next(v for v in yvals if v)
    unit = 1000000 if first >= 1000000 else 1000 if first >= 300 else 1
    yticks = "".join(
        f'<g class="tick" opacity="1" transform="translate(0,{fmt(y(v) + 0.5)})">'
        f'<line stroke="currentColor" x2="-1"></line>'
        f'<text fill="currentColor" x="-7" dy="0.32em" '
        f'style="font-family: xkcd; font-size: 16px; fill: {stroke};">'
        f'{" " if v == 0 else number_tick_label(v, unit)}</text></g>'
        for v in yvals
    )
    yaxis = (
        f'<g class="yaxis" fill="none" font-size="10" font-family="sans-serif" text-anchor="end">'
        f'<path class="domain" stroke="currentColor" d="M-1,{fmt(CHART_H + 0.5)}H0.5V0.5H-1" '
        f'filter="url(#xkcdify)" style="stroke: {stroke};"></path>{yticks}</g>'
    )

    line_path = monotone_x_path([(x(t), y(v)) for t, v in points])
    line = (f'<path class="xkcd-chart-xyline" d="{line_path}" fill="none" '
            f'stroke="{line_color}" filter="url(#xkcdify)"></path>')

    # 범례(좌상단): 너비 공식은 drawLegend 에서 가져왔다
    L = len(REPO)
    legend_w = max(L * 7.5 + 8 + 7 + 14, L * 7 + 8 + 14 + 6)
    legend = (
        f'<svg><svg><rect style="fill: {bg};" fill-opacity="0.85" stroke="{stroke}" '
        f'stroke-width="2" rx="5" ry="5" filter="url(#xkcdify)" width="{fmt(float(legend_w))}" '
        f'height="32" x="8" y="5"></rect></svg>'
        f'<svg><rect style="fill: {line_color};" width="8" height="8" rx="2" ry="2" '
        f'filter="url(#xkcdify)" x="15" y="17"></rect>'
        f'<text style="font-size: 15px; fill: {stroke};" x="29" y="25">{REPO}</text></svg></svg>'
    )

    watermark = (
        f'<text style="font-size: 16px; fill: #666666;" '
        f'transform="translate({fmt(CHART_W - 50.0)},{fmt(CHART_H + 40)})" '
        f'text-anchor="middle">star-history.com</text>'
        f'<image transform="translate({fmt(CHART_W - 135.0)},{fmt(CHART_H + 24)})" '
        f'height="20" width="20" href="data:image/png;base64,{logo_b64}"></image>'
    )

    tooltip = (
        f'<svg x="15" y="10" style="visibility: hidden;">'
        f'<rect style="fill: {bg};" fill-opacity="0.9" stroke="{stroke}" stroke-width="2" '
        f'rx="5" ry="5" filter="url(#xkcdify)" width="25" height="30" x="5" y="5"></rect>'
        f'<text style="font-size: 15px; font-weight: bold; fill: {stroke};" x="15" y="25"></text></svg>'
    )

    # 제목 + 저장소 아바타(clipX = 800*0.5-73, logoX = 800*0.5-84)
    title = (
        f'<text style="font-size: 20px; font-weight: bold; fill: {stroke};" x="50%" y="30" '
        f'text-anchor="middle">Star History</text>'
        f'<svg><defs><clipPath id="clip-circle-title"><circle r="11" cx="327" cy="23">'
        f'</circle></clipPath></defs></svg>'
        f'<image x="316" y="12" height="22" width="22" '
        f'href="data:{avatar_mime};base64,{avatar_b64}" clip-path="url(#clip-circle-title)"></image>'
    )

    # Y 축 라벨 오프셋: xy-chart 의 최댓값 구간별 값을 따른다
    offset_y = 2 if total > 100000 else 8 if total > 10000 else 12 if total > 1000 else 20 if total > 100 else 24
    label_x = math.floor(100 / 2 - HEIGHT / 2)
    labels = (
        f'<text style="font-size: 17px; fill: {stroke};" x="50%" y="{fmt(HEIGHT - 10)}" '
        f'text-anchor="middle">Date</text>'
        f'<text text-anchor="end" dy=".75em" transform="rotate(-90)" '
        f'style="font-size: 17px; fill: {stroke};" y="{offset_y}" x="{label_x}">GitHub Stars</text>'
    )

    return (
        f'<svg width="{WIDTH}" xmlns="http://www.w3.org/2000/svg" '
        f'style="stroke-width: 3; font-family: xkcd; background: {bg};" '
        f'height="{fmt(HEIGHT)}" preserveAspectRatio="xMidYMid meet">'
        f'<defs><style type="text/css">@font-face {{\n'
        f'      font-family: "xkcd";\n'
        f'      src: url(data:application/font-woff;charset=utf-8;base64,{font_b64}) format(\'woff\');\n'
        f'    }}</style></defs>'
        f'<filter id="xkcdify" filterUnits="userSpaceOnUse" x="-5" y="-5" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.05" result="noise"/>'
        f'<feDisplacementMap scale="5" xChannelSelector="R" yChannelSelector="G" '
        f'in="SourceGraphic" in2="noise"/></filter>'
        f'<g transform="translate({M_LEFT},{M_TOP})"><g pointer-events="all">'
        f'{watermark}{xaxis}{yaxis}{line}{legend}</g></g>'
        f'{tooltip}{title}{labels}</svg>'
    )


def main():
    tools_dir = Path(__file__).resolve().parent
    out_dir = tools_dir.parent / "assets"

    points, total, avatar_url = fetch_points()
    avatar = gh_get(avatar_url + "&s=64", raw=True)
    avatar_mime = "image/jpeg" if avatar[:2] == b"\xff\xd8" else "image/png"
    avatar_b64 = base64.b64encode(avatar).decode()
    font_b64 = base64.b64encode((tools_dir / "xkcd.woff").read_bytes()).decode()
    logo_b64 = base64.b64encode((tools_dir / "star-history-logo.png").read_bytes()).decode()

    for suffix, theme in THEMES.items():
        path = out_dir / f"star-history{suffix}.svg"
        path.write_text(render(points, total, theme, font_b64, logo_b64, avatar_b64, avatar_mime),
                        encoding="utf-8")
        print(f"생성 완료 {path} ({total:,} stars, 샘플 지점 {len(points)}개)")


if __name__ == "__main__":
    main()

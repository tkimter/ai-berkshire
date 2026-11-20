#!/usr/bin/env python3
"""Report Audit Tool for AI Berkshire.

데이터 표본 검사 도구: 연구 보고서에서 재무 데이터 포인트의 15%를 추출해 신뢰할 수 있는 출처와 대조한다.
통과하면 통과 판정, 통과하지 못하면 반려하고 이유를 밝힌다.

Zero external dependencies — uses only Python stdlib.
Requires Python >= 3.7.

워크플로(3단계):
  Step 1 — 데이터 포인트를 추출하고 15%를 무작위 추출:
    python3 tools/report_audit.py extract --report reports/xxx.md

  Step 2 — Claude 가 표본 목록의 데이터 포인트마다 신뢰할 수 있는 출처(macrotrends/
            stockanalysis/aastocks/eastmoney)에서 수치를 가져와 fetched_value 에 채운다

  Step 3 — 검증 결과를 입력해 통과/반려 판정을 출력:
    python3 tools/report_audit.py verdict --results '[...]'

  한 번에 실행(추출 + 표본 목록 출력만, 네트워크 검증 없음):
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run
"""

import argparse
import json
import math
import os
import re
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN
from random import Random

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)

# ---------------------------------------------------------------------------
# 데이터 포인트 추출: Markdown 보고서에서 재무 수치를 식별한다
# ---------------------------------------------------------------------------

# 매칭 패턴: 숫자 + 단위, 앞에 문맥 라벨이 붙는다
# 예: 매출: 1,239억 위안, PE 18.8x, 매출총이익률 56%, 시가총액 ~$5,670억
#
# 주의: 모든 숫자 캡처 그룹에는 선택적 부호 _SIGN 이 붙어야 한다. 그렇지 않으면 "-1.72%" 가
# "1.72" 로 잡혀, 검증할 때 보고서 값과 출처 값의 부호가 반대가 되고 편차 200% 로 거짓 반려가 나온다.
# 부호는 ASCII 양음 부호, Unicode 마이너스(U+2212), en-dash(U+2013), 전각 양음 부호를 포괄한다.
_SIGN = r'[+\-−–－＋]?'

# 보고서가 한국어이므로 단위는 한국어 표기를 인식한다(영어 표기는 그대로 유지).
#   규모: 조 / 억 / 만 (앞에 천·백·십 이 붙을 수 있다: 5천억, 3백만)
#   통화: 위안 / 홍콩달러 / 미국달러 / 달러 / 원 (+ RMB / USD / HKD / KRW)
#   배수: x / X / 배,  백분율: %,  영어 약어: B / M / T
_MAG = r'[천백십]?(?:조|억|만)'
_CUR = r'(?:위안|홍콩달러|미국달러|달러|원|RMB|USD|HKD|KRW)'
_UNIT = _MAG + r'\s*' + _CUR + r'?|' + _CUR + r'|[xX배]|%|[BMT]'
# 숫자 앞의 어림 표시(~ / 약)와 통화 기호
_PREFIX = r'(?:[~약]\s*)?[\$₩]?'

_PATTERNS = [
    # 백분율
    (r'(' + _SIGN + r'[\d,，\.]+)\s*%',                        '%',    'percent'),
    # 억 위안/억 달러/억 홍콩달러/억 원
    (r'(' + _SIGN + r'[\d,，\.]+)\s*억\s*(' + _CUR + r')?',       '억',   'hundred_million'),
    # 배수 PE/PB/PS
    (r'(' + _SIGN + r'[\d,，\.]+)\s*[xX배]',                   'x',    'multiple'),
    # 조
    (r'(' + _SIGN + r'[\d,，\.]+)\s*조',                        '조',   'trillion'),
    # 달러 절대값(B/T)
    (r'\$\s*(' + _SIGN + r'[\d,，\.]+)\s*([BMT억조])',           '$',    'usd_abs'),
    # 순수 숫자(시가총액, 매출, 사용자 수 등이 표의 | 안에 나오는 경우)
    (r'\|\s*' + _PREFIX + r'(' + _SIGN + r'[\d,，\.]+)\s*\|',     '',     'table_num'),
]

_LABEL_RE = re.compile(
    r'(?P<label>[^\|\n：:]{2,25})[：:\s]+' + _PREFIX + r'(?P<num>' + _SIGN + r'[\d,，\.]+)'
    r'\s*(?P<unit>' + _UNIT + r')?'
)

_TABLE_ROW_RE = re.compile(
    r'\|\s*(?P<label>[^|]{1,40})\s*\|\s*' + _PREFIX + r'(?P<num>' + _SIGN + r'[\d,，\.]+)'
    r'\s*(?P<unit>' + _UNIT + r')?\s*\|'
)


def _clean_num(s: str) -> float:
    """쉼표, 전각 쉼표, 각종 양음 부호가 섞인 숫자 문자열을 float 로 바꾼다.

    ASCII '-'/'+', Unicode 마이너스 '−'(U+2212), en-dash '–'(U+2013),
    전각 '－'(U+FF0D)/'＋'(U+FF0B)를 지원한다. 보고서에서는 이 기호들이 모두 양음 부호로 쓰일 수 있다.
    """
    s = s.replace(',', '').replace('，', '').strip()
    # 각종 부호를 ASCII 로 정규화
    for ch in ('−', '–', '－'):
        s = s.replace(ch, '-')
    s = s.replace('＋', '+')
    try:
        return float(s)
    except ValueError:
        return None


def _is_valid_label(label: str) -> bool:
    """라벨이 의미 있는 재무 필드명인지 판단해 노이즈를 걸러낸다."""
    label = label.strip()
    # 너무 짧음
    if len(label) < 2:
        return False
    # 숫자뿐이거나 연도/분기뿐
    if re.fullmatch(r'[\d\s년분기Q]+', label):
        return False
    # 기호/markdown 표시로 시작
    if re.match(r'^[+\-\*#\|~\$>_`]', label):
        return False
    # markdown 굵게/코드 표시 포함
    if '**' in label or '`' in label or '__' in label:
        return False
    # 라벨이 증가율 표기뿐(+56%, -13% 가 단독으로 라벨이 된 경우)
    if re.fullmatch(r'[+\-]?\d+(\.\d+)?%', label):
        return False
    # 흔한 무의미 라벨
    _SKIP = {'출처', 'sources', 'source', '설명', '주의', '비고', '데이터 출처',
             'n/a', '—', '-', '/', '합계', 'total', '단위', '추세'}
    if label.lower() in _SKIP:
        return False
    return True


# 2열 표 행: | 라벨 | 수치 unit | (재무 보고서의 KV 표 전용)
_KV_TABLE_RE = re.compile(
    r'^\|\s*(?P<label>[^|*\n]{2,40}?)\s*\|\s*' + _PREFIX + r'(?P<num>' + _SIGN + r'[\d,，\.]+)\s*'
    r'(?P<unit>' + _UNIT + r')?\s*[\|（\(]'
)

# 라벨이 붙은 KV 행: 라벨: 수치 단위
_KV_LABEL_RE = re.compile(
    r'(?P<label>[가-힣A-Za-z][^\|\n：:*]{1,30})[：:]\s*' + _PREFIX +
    r'(?P<num>' + _SIGN + r'[\d,，\.]+)\s*(?P<unit>' + _UNIT + r')?'
)


def _parse_md_tables(lines: list) -> list:
    """Markdown 의 모든 표를 파싱해 (row_label, col_header, value, unit, lineno, raw) 목록을 반환한다."""
    results = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 표 머리행 감지(| 를 포함하고 구분행이 아님)
        if '|' in line and not re.match(r'^\|[\-\s\|:]+\|$', line):
            headers_raw = [h.strip().strip('*_').strip() for h in line.split('|')]
            headers_raw = [h for h in headers_raw if h]
            # 다음 행은 구분행이어야 한다
            if i + 1 < len(lines) and re.match(r'^\|[\-\s\|:]+\|$', lines[i+1].strip()):
                i += 2  # 구분행 건너뛰기
                # 데이터 행 읽기
                while i < len(lines):
                    dline = lines[i].strip()
                    if not dline or not dline.startswith('|'):
                        break
                    cells = [c.strip().strip('*_~').strip() for c in dline.split('|')]
                    cells = [c for c in cells if c != '']
                    if len(cells) < 2:
                        i += 1
                        continue
                    row_label = cells[0]
                    for col_idx, cell in enumerate(cells[1:], start=1):
                        col_header = headers_raw[col_idx] if col_idx < len(headers_raw) else f'열{col_idx}'
                        # cell 안의 숫자+단위 추출
                        m = re.search(
                            _PREFIX + r'(' + _SIGN + r'[\d,，\.]+)\s*'
                            r'(' + _UNIT + r')?',
                            cell
                        )
                        if m:
                            val = _clean_num(m.group(1))
                            unit = (m.group(2) or '').strip()
                            if val is not None and val != 0 and abs(val) < 1e15:
                                results.append((row_label, col_header, val, unit, i + 1, dline))
                    i += 1
                continue
        i += 1
    return results


def extract_data_points(md_text: str) -> list:
    """Markdown 보고서에서 식별 가능한 모든 재무 데이터 포인트를 추출한다.

    세 가지 구조를 다룬다:
      1. 여러 열의 Markdown 표(가장 주된 출처): (행 라벨 + 열 제목) → 수치
      2. 콜론이 붙은 KV 행: 라벨: 수치 단위
      3. 굵은 숫자 행: **수치** 단위

    반환 list of dict:
      {id, label, reported_value, unit, raw_text, line_number}
    """
    points = []
    seen = set()

    def _add(label, val, unit, lineno, raw):
        label = re.sub(r'[\*_`]+', '', label).strip()
        if not _is_valid_label(label):
            return
        if val is None or val == 0 or abs(val) > 1e15:
            return
        # 연도/분기뿐인 라벨 제외
        if re.fullmatch(r'(20\d{2}|Q[1-4]|\d{4}\s*Q[1-4])', label.strip()):
            return
        key = f"{label}|{round(val,4)}|{unit}"
        if key in seen:
            return
        seen.add(key)
        points.append({
            'id': len(points) + 1,
            'label': label,
            'reported_value': val,
            'unit': unit,
            'raw_text': raw[:120],
            'line_number': lineno,
        })

    lines = md_text.split('\n')
    in_code = False

    # --- 1. 여러 열의 표 ---
    for row_label, col_header, val, unit, lineno, raw in _parse_md_tables(lines):
        # 무의미한 행 라벨 건너뛰기
        if not _is_valid_label(row_label):
            continue
        # 무의미한 열 제목 건너뛰기(YoY 증가율 열은 따로 표기하는 것이며 검증 대상 데이터가 아니다)
        if col_header.upper() in ('YOY', 'YOY증가율', 'YOY 증가율', '증가율', '전년비', '전년 대비',
                                  '전년동기비', '전년 동기 대비', '변동', '변화', '추세', '설명', '비고'):
            continue
        # label = "행 라벨 · 열 제목"(열 제목이 행 라벨을 보충하는 경우)
        if col_header and col_header != row_label:
            label = f"{row_label} · {col_header}"
        else:
            label = row_label
        _add(label, val, unit, lineno, raw)

    # --- 2. KV 콜론 행 ---
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code or stripped.startswith('> ') or re.match(r'^#{1,6}\s', stripped):
            continue
        if '|' in stripped:
            continue  # 표는 위에서 이미 처리했다

        for m in _KV_LABEL_RE.finditer(stripped):
            label = m.group('label')
            val = _clean_num(m.group('num'))
            unit = (m.group('unit') or '').strip()
            _add(label, val, unit, lineno, stripped)

    return points


def sample_points(points: list, ratio: float = 0.15, seed: int = None) -> list:
    """ratio 비율만큼 데이터 포인트를 무작위 추출한다. 최소 3개, 최대 30개."""
    n = max(3, min(30, math.ceil(len(points) * ratio)))
    n = min(n, len(points))
    rng = Random(seed)
    sampled = rng.sample(points, n)
    # 사람이 대조하기 쉽게 행 번호순으로 정렬
    return sorted(sampled, key=lambda p: p['line_number'])


# ---------------------------------------------------------------------------
# 통과/반려 판정
# ---------------------------------------------------------------------------

_TOLERANCE = 0.01   # 허용 오차 1%


def _pct_diff(reported: float, fetched: float) -> float:
    """상대 편차(absolute)."""
    if reported == 0:
        return 0.0 if fetched == 0 else float('inf')
    return abs(reported - fetched) / abs(reported)


def render_verdict(results: list, report_name: str = "") -> dict:
    """
    검증 결과에 따라 통과/반려 판정을 출력한다.

    results: list of dict. 항목마다 다음을 담는다:
      - id, label, reported_value, unit, fetched_value, fetched_source
      - (선택) fetched_value2, fetched_source2   ← 두 번째 출처

    반환:
      {
        'verdict': 'PASS' | 'FAIL',
        'pass_count': int,
        'fail_count': int,
        'total': int,
        'fail_items': [...],
        'summary': str,
      }
    """
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

    print('=' * 70)
    print(f'{BOLD}보고서 데이터 표본 검사 — 통과/반려 판정{RESET}')
    if report_name:
        print(f'보고서: {report_name}')
    print('=' * 70)
    print()

    fail_items = []
    warn_items = []

    for item in results:
        label = item.get('label', '?')
        reported = float(item.get('reported_value', 0))
        unit = item.get('unit', '')
        fetched = item.get('fetched_value')
        source = item.get('fetched_source', '?')
        fetched2 = item.get('fetched_value2')
        source2 = item.get('fetched_source2', '')

        # --- 주 출처 대조 ---
        if fetched is None:
            # 검증값이 없음 → 건너뛴다(통과/실패에 넣지 않는다)
            print(f'  ⬜ [{item["id"]:>2}] {label[:35]:35s} {reported:>12.2f} {unit}  →  [검증값 없음, 건너뜀]')
            continue

        fetched = float(fetched)
        diff1 = _pct_diff(reported, fetched)

        # --- 두 번째 출처 대조(있는 경우) ---
        diff2 = None
        if fetched2 is not None:
            fetched2 = float(fetched2)
            diff2 = _pct_diff(reported, fetched2)

        # 판단
        pass1 = diff1 <= _TOLERANCE
        pass2 = (diff2 is None) or (diff2 <= _TOLERANCE)

        if pass1 and pass2:
            status = f'{GREEN}✅ 통과{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
        elif not pass1 and not pass2:
            status = f'{RED}❌ 불통과{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
            fail_items.append({
                'id': item['id'],
                'label': label,
                'reported': reported,
                'unit': unit,
                'fetched': fetched,
                'source': source,
                'fetched2': fetched2,
                'source2': source2,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
                'raw_text': item.get('raw_text', ''),
                'line_number': item.get('line_number', 0),
            })
        else:
            # 한 출처는 통과, 한 출처는 불통과 → 경고, 실패에 넣지 않는다
            status = f'{YELLOW}⚠️  경고{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
            warn_items.append({
                'id': item['id'], 'label': label,
                'reported': reported, 'unit': unit,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
            })

        print(f'  {status} [{item["id"]:>2}] {label[:35]:35s}  보고서: {reported:>12.2f} {unit}')
        print(f'              {" " * 38}{detail}')

    print()
    print('-' * 70)

    total = len([r for r in results if r.get('fetched_value') is not None])
    fail_count = len(fail_items)
    warn_count = len(warn_items)
    pass_count = total - fail_count - warn_count

    print(f'  표본 총수: {total}  |  통과: {GREEN}{pass_count}{RESET}  |  경고: {YELLOW}{warn_count}{RESET}  |  불통과: {RED}{fail_count}{RESET}')
    print()

    if fail_count == 0:
        print(f'{BOLD}{GREEN}【통과】모든 표본 데이터가 통과했다. 보고서 발행 가능.{RESET}')
        verdict = 'PASS'
    else:
        print(f'{BOLD}{RED}【반려】데이터 포인트 {fail_count}개가 검증을 통과하지 못했다. 보고서를 수정한 뒤 재심사한다.{RESET}')
        print()
        print(f'{BOLD}반려 사유:{RESET}')
        for fi in fail_items:
            print(f'  ❌ {fi["line_number"]}행 | {fi["label"]}')
            print(f'     보고서 값: {fi["reported"]} {fi["unit"]}')
            print(f'     {fi["source"]}: {fi["fetched"]}  (편차 {fi["diff1_pct"]}%)')
            if fi.get('fetched2') is not None:
                print(f'     {fi["source2"]}: {fi["fetched2"]}  (편차 {fi["diff2_pct"]}%)')
            print(f'     원문: {fi["raw_text"][:80]}')
            print()
        verdict = 'FAIL'

    if warn_count > 0:
        print(f'{YELLOW}주의: 데이터 포인트 {warn_count}개는 두 출처의 결과가 일치하지 않는다(1% 초과). 기준 차이(GAAP/Non-GAAP 또는 환율)일 수 있으니 사람이 재확인한다.{RESET}')
        for wi in warn_items:
            print(f'  ⚠️  {wi["label"]}  보고서:{wi["reported"]} {wi["unit"]}  편차: {wi["diff1_pct"]}% / {wi["diff2_pct"]}%')

    print('=' * 70)

    return {
        'verdict': verdict,
        'pass_count': pass_count,
        'warn_count': warn_count,
        'fail_count': fail_count,
        'total': total,
        'fail_items': fail_items,
        'warn_items': warn_items,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def _force_utf8_stdio():
    """stdout/stderr 를 UTF-8 로 강제 전환한다.

    Windows 콘솔 기본값은 cp949 등 레거시 코드페이지라서, 보고서 안의 €, →, ★ 같은 문자가
    print(json.dumps(...)) 에서 UnicodeEncodeError 를 일으켜 그대로 죽는다.
    errors='replace' 로 극단적인 문자가 나와도 흐름이 끊기지 않게 한다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass  # TextIOWrapper 가 아닐 때(파이프 객체로 리다이렉트된 경우 등)는 무시


def main():
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description='Report Audit Tool — 연구 보고서 데이터 표본 검사 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
워크플로:

  Step 1 — 데이터 포인트를 추출하고 15%를 무작위 추출해 표본 목록을 출력:
    python3 tools/report_audit.py extract --report reports/xxx/xxx-research-20260408.md

  Step 2 — Claude 가 목록의 데이터 포인트마다 신뢰할 수 있는 출처에서 수치를 가져와
            fetched_value / fetched_source / fetched_value2 / fetched_source2 에 채운다

  Step 3 — 검증 결과를 입력해 통과/반려 판정을 출력:
    python3 tools/report_audit.py verdict --results '[
      {"id":1,"label":"매출","reported_value":7518,"unit":"억","fetched_value":7518,"fetched_source":"macrotrends","fetched_value2":7500,"fetched_source2":"stockanalysis"},
      ...
    ]'

  미리보기(표본 목록만 출력하고 검증하지 않음):
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run

  추출 비율 지정(기본값 0.15):
    python3 tools/report_audit.py extract --report reports/xxx.md --ratio 0.20

  난수 시드 고정(같은 표본을 재현):
    python3 tools/report_audit.py extract --report reports/xxx.md --seed 42
        """)

    sub = parser.add_subparsers(dest='command')

    # extract
    ext = sub.add_parser('extract', help='보고서에서 데이터 포인트를 추출해 무작위 추출')
    ext.add_argument('--report', required=True, help='보고서 파일 경로(Markdown)')
    ext.add_argument('--ratio', type=float, default=0.15, help='추출 비율, 기본값 0.15')
    ext.add_argument('--seed', type=int, default=None, help='난수 시드(선택, 재현용)')
    ext.add_argument('--dry-run', action='store_true', help='출력만 하고 JSON 은 내보내지 않는다')

    # verdict
    vrd = sub.add_parser('verdict', help='검증 결과에 따라 통과/반려 판정을 출력')
    vrd.add_argument('--results', required=True, help='JSON 배열. fetched_value 등의 필드를 담는다')
    vrd.add_argument('--report', default='', help='보고서 이름(선택, 표시용)')
    vrd.add_argument('--output-json', action='store_true', help='판정 결과를 JSON 으로 stdout 에 출력')

    args = parser.parse_args()

    if args.command == 'extract':
        if not os.path.exists(args.report):
            print(f'❌ 파일이 없다: {args.report}', file=sys.stderr)
            sys.exit(1)

        with open(args.report, 'r', encoding='utf-8') as f:
            text = f.read()

        all_points = extract_data_points(text)
        sampled = sample_points(all_points, ratio=args.ratio, seed=args.seed)

        print('=' * 70)
        print(f'보고서 데이터 표본 검사 목록')
        print(f'파일: {args.report}')
        print(f'추출된 데이터 포인트 총수: {len(all_points)}  |  추출 비율: {args.ratio:.0%}  |  표본 수: {len(sampled)}')
        if args.seed is not None:
            print(f'난수 시드: {args.seed}(같은 표본을 재현하는 데 쓸 수 있다)')
        print('=' * 70)
        print()
        print(f'{"ID":>3}  {"행":>5}  {"데이터 라벨":<35}  {"보고서 값":>12}  {"단위"}')
        print(f'{"─"*3}  {"─"*5}  {"─"*35}  {"─"*12}  {"─"*6}')
        for p in sampled:
            print(f'{p["id"]:>3}  {p["line_number"]:>5}  {p["label"][:35]:<35}  {p["reported_value"]:>12.2f}  {p["unit"]}')
        print()
        print('↑ 위의 데이터 포인트마다 아래 출처에서 수치를 가져와 fetched_value 에 채운다:')
        print('  미국 주식: macrotrends.net(주) + stockanalysis.com(부)')
        print('  홍콩 주식: aastocks.com(주) + macrotrends ADR(부)')
        print('  A주:       eastmoney.com(주) + cninfo.com.cn(부)')
        print()

        if not args.dry_run:
            # 채워 넣을 수 있는 JSON 템플릿 출력
            template = []
            for p in sampled:
                template.append({
                    'id': p['id'],
                    'label': p['label'],
                    'reported_value': p['reported_value'],
                    'unit': p['unit'],
                    'line_number': p['line_number'],
                    'raw_text': p['raw_text'],
                    'fetched_value': None,       # ← 주 출처 검증값을 채운다
                    'fetched_source': '',        # ← 주 출처 이름을 채운다
                    'fetched_value2': None,      # ← 부 출처 검증값을 채운다(선택)
                    'fetched_source2': '',       # ← 부 출처 이름을 채운다(선택)
                })
            print('표본 목록 JSON(fetched_value 를 채운 뒤 verdict 명령에 전달):')
            print()
            print(json.dumps(template, ensure_ascii=False, indent=2))

    elif args.command == 'verdict':
        try:
            results = json.loads(args.results)
        except json.JSONDecodeError as e:
            print(f'❌ JSON 파싱 실패: {e}', file=sys.stderr)
            sys.exit(1)

        report_name = args.report or ''
        outcome = render_verdict(results, report_name=report_name)

        if args.output_json:
            print(json.dumps(outcome, ensure_ascii=False, indent=2))

        # 0 이 아닌 종료 코드는 반려를 뜻한다. CI/스크립트가 판단하기 쉽게 한다
        sys.exit(0 if outcome['verdict'] == 'PASS' else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()

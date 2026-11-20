#!/usr/bin/env python3
"""report_audit.py 회귀 테스트.

이미 고친 결함 두 가지와 한국어 단위 인식을 다룬다:

  BUG-1  숫자 추출 시 음수 부호 누락
         정규식 7곳이 `([\\d,，\\.]+)` 로 숫자를 캡처했고 부호 자리가 없었다. 보고서의
         "-1.72%" 가 1.72 로 추출되어, 검증할 때 출처의 -1.72 와 비교하면 편차 200% 가
         나오고 **거짓 반려** 가 발생한다. 가장 위험한 종류의 bug 다: 오류를 내지 않고
         조용히 결론을 뒤집는다.

  BUG-2  Windows 콘솔 레거시 코드페이지(cp949) 인코딩 크래시
         main() 의 print(json.dumps(...)) 가 €/→/★ 같은 문자를 만나면
         UnicodeEncodeError 를 내고 그대로 종료한다.

  KO     보고서가 한국어이므로 억/조/만, 위안/홍콩달러/달러/원, 배 를 단위로 인식해야 한다.

Zero external dependencies — unittest 만 쓴다. report_audit.py 자체와 같은 원칙이다.
실행:  python tests/test_report_audit.py
"""

import io
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import report_audit as R  # noqa: E402

_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools')


class TestCleanNumSign(unittest.TestCase):
    """BUG-1 의 최소 단위: _clean_num 은 각종 양음 부호를 인식해야 한다."""

    def test_ascii_minus(self):
        self.assertEqual(R._clean_num('-1.72'), -1.72)

    def test_plain_positive(self):
        self.assertEqual(R._clean_num('1.72'), 1.72)

    def test_ascii_plus_is_stripped(self):
        self.assertEqual(R._clean_num('+3.5'), 3.5)

    def test_unicode_minus_u2212(self):
        """보고서에는 ASCII 하이픈이 아닌 U+2212 진짜 마이너스가 자주 나온다."""
        self.assertEqual(R._clean_num('−4.2'), -4.2)

    def test_en_dash_u2013(self):
        """Markdown 편집기는 - 를 자동으로 en-dash 로 바꾼다."""
        self.assertEqual(R._clean_num('–5.1'), -5.1)

    def test_fullwidth_minus_uff0d(self):
        """전각 입력 모드의 전각 마이너스."""
        self.assertEqual(R._clean_num('－6.3'), -6.3)

    def test_negative_with_thousands_separator(self):
        self.assertEqual(R._clean_num('-1,234.5'), -1234.5)

    def test_negative_with_fullwidth_comma(self):
        self.assertEqual(R._clean_num('-1，234.5'), -1234.5)

    def test_garbage_returns_none(self):
        self.assertIsNone(R._clean_num('n/a'))


class TestNegativeExtractionFromTable(unittest.TestCase):
    """BUG-1 의 엔드투엔드 재현: 보고서 표의 음수는 온전히 추출되어야 한다.

    표 구조는 거짓 반려를 일으킨 시세표를 본뜬 것이다: 하락률 열이 "-1.72%" 로 적혀 있고,
    수정 전에는 1.72 로 추출되어 출처와 대조하면 편차 200% 가 나왔다.
    데이터는 가상이며 형식을 고정하는 용도일 뿐이다.
    """

    MD = (
        "| 회사 | 코드 | 주가 | 당일 | PB |\n"
        "|---|---|---|---|---|\n"
        "| 예시회사 갑 | 000001 | 27.40 | -1.72% | 1.03 |\n"
        "| 예시회사 을 | 000002 | 17.56 | -1.90% | 2.18 |\n"
        "| 예시회사 병 | 000003 | 12.78 | +1.11% | 1.79 |\n"
        "| 매출총이익률 | — | — | -3.10% | — |\n"
    )

    def setUp(self):
        self.values = {p['reported_value'] for p in R.extract_data_points(self.MD)}

    def test_extracts_negative_percentages(self):
        for expected in (-1.72, -1.9, -3.1):
            with self.subTest(value=expected):
                self.assertIn(
                    expected, self.values,
                    f"{expected} 가 추출되지 않았다 —— 음수 부호를 정규식이 또 먹어 버렸을 가능성이 크다")

    def test_does_not_flip_sign(self):
        """회귀의 핵심: -1.72 를 +1.72 로 뽑아서는 절대 안 된다."""
        self.assertNotIn(1.72, self.values, "음수 부호 누락: -1.72 가 1.72 로 추출되었다")
        self.assertNotIn(1.9, self.values, "음수 부호 누락: -1.90 이 1.90 으로 추출되었다")

    def test_plus_sign_normalised_to_positive(self):
        self.assertIn(1.11, self.values)

    def test_negative_count(self):
        self.assertEqual(
            len([v for v in self.values if v < 0]), 3,
            "음수 값이 정확히 3개 추출되어야 한다(-1.72 / -1.90 / -3.10)")


class TestAbsoluteValueGuard(unittest.TestCase):
    """`val > 1e15` 상한 판단은 음수에 대해 항상 거짓이므로 abs() 를 써야 한다."""

    def test_huge_negative_is_filtered(self):
        md = (
            "| 항목 | 수치 |\n"
            "|---|---|\n"
            "| 이상값 | -9999999999999999 |\n"
            "| 정상값 | -12.5 |\n"
        )
        values = {p['reported_value'] for p in R.extract_data_points(md)}
        self.assertIn(-12.5, values)
        self.assertTrue(
            all(abs(v) < 1e15 for v in values),
            "1e15 를 넘는 음수 값이 걸러지지 않았다(abs() 가드 무효)")


class TestKoreanUnits(unittest.TestCase):
    """KO: 한국어 보고서의 단위·키워드 인식."""

    MD = (
        "# 테스트 보고서\n\n"
        "시가총액: 약 5,670억 위안\n"
        "주가: 510홍콩달러\n"
        "PE: 18.8배\n"
        "매출총이익률: 56%\n"
        "순현금: $120억\n\n"
        "| 지표 | FY25 | 전년 대비 | 비고 |\n"
        "|---|---|---|---|\n"
        "| 매출 | 1.2조 원 | 15% | 3 |\n"
        "| 영업이익 | 2,345억 달러 | 8% | 4 |\n"
        "| 사용자 수 | 500만 | 2% | 5 |\n"
        "| 출처 | 7 | 1% | 6 |\n"
    )

    def setUp(self):
        self.points = R.extract_data_points(self.MD)
        self.by_label = {p['label']: p for p in self.points}

    def _unit(self, label):
        return ''.join(self.by_label[label]['unit'].split())

    def test_kv_lines_with_korean_units(self):
        self.assertEqual(self.by_label['시가총액']['reported_value'], 5670.0)
        self.assertEqual(self._unit('시가총액'), '억위안')
        self.assertEqual(self.by_label['주가']['reported_value'], 510.0)
        self.assertEqual(self._unit('주가'), '홍콩달러')
        self.assertEqual(self.by_label['PE']['reported_value'], 18.8)
        self.assertEqual(self._unit('PE'), '배')
        self.assertEqual(self._unit('매출총이익률'), '%')
        self.assertEqual(self.by_label['순현금']['reported_value'], 120.0)
        self.assertEqual(self._unit('순현금'), '억')

    def test_table_cells_with_korean_units(self):
        self.assertEqual(self.by_label['매출 · FY25']['reported_value'], 1.2)
        self.assertEqual(self._unit('매출 · FY25'), '조원')
        self.assertEqual(self.by_label['영업이익 · FY25']['reported_value'], 2345.0)
        self.assertEqual(self._unit('영업이익 · FY25'), '억달러')
        self.assertEqual(self._unit('사용자 수 · FY25'), '만')

    def test_korean_noise_headers_and_labels_skipped(self):
        labels = set(self.by_label)
        self.assertFalse(any('전년 대비' in l or '비고' in l for l in labels),
                         "증가율/비고 열은 검증 대상이 아니다")
        self.assertFalse(any(l.startswith('출처') for l in labels),
                         "'출처' 행은 무의미 라벨로 걸러져야 한다")


class TestLegacyConsoleStdoutSurvival(unittest.TestCase):
    """BUG-2: Windows cp949 콘솔에서 € 가 든 한국어 보고서를 extract 해도 죽지 않아야 한다."""

    MD = (
        "# 테스트 보고서\n\n"
        "| 회사 | FY25 매출 | 매출총이익률 |\n"
        "|---|---|---|\n"
        "| Example Corp | €11,297M | 26.1% |\n"
        "| 예시회사 갑 | ¥23.6억 | -3.10% |\n\n"
        "등급: ★★☆☆☆ → 관찰\n"
    )

    def test_extract_under_cp949_console(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(self.MD)
            path = fh.name
        try:
            env = dict(os.environ)
            # Windows cp949 콘솔을 흉내 낸다. UTF-8 탈출구는 명시적으로 치운다
            env['PYTHONIOENCODING'] = 'cp949'
            env.pop('PYTHONUTF8', None)
            proc = subprocess.run(
                [sys.executable, os.path.join(_TOOLS, 'report_audit.py'),
                 'extract', '--report', path, '--seed', '1'],
                capture_output=True, env=env)
            self.assertEqual(
                proc.returncode, 0,
                "cp949 콘솔에서 extract 가 죽었다:\n"
                + proc.stderr.decode('utf-8', 'replace')[-800:])
            self.assertNotIn(b'UnicodeEncodeError', proc.stderr)
            # 도구가 stdout 을 UTF-8 로 강제하므로 출력은 UTF-8 로 온전히 읽혀야 한다
            out = proc.stdout.decode('utf-8')
            self.assertIn('보고서 데이터 표본 검사 목록', out)
            self.assertIn('예시회사 갑', out)
        finally:
            os.unlink(path)

    def test_verdict_labels_utf8(self):
        """verdict 출력 라벨(【통과】/【반려】)과 종료 코드."""
        import json
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'utf-8'
        # 두 출처가 모두 어긋나야 반려다(한 출처만 어긋나면 경고로 처리된다)
        base = {'id': 1, 'label': '매출', 'reported_value': 100.0, 'unit': '억',
                'fetched_source': 'A', 'fetched_source2': 'B'}
        for fetched, code, tag in ((100.0, 0, '【통과】'), (150.0, 1, '【반려】')):
            with self.subTest(fetched=fetched):
                proc = subprocess.run(
                    [sys.executable, os.path.join(_TOOLS, 'report_audit.py'), 'verdict',
                     '--results', json.dumps(
                         [dict(base, fetched_value=fetched, fetched_value2=fetched)],
                         ensure_ascii=False)],
                    capture_output=True, text=True, encoding='utf-8', env=env)
                self.assertEqual(proc.returncode, code, proc.stderr[-800:])
                self.assertIn(tag, proc.stdout)

    def test_force_utf8_stdio_is_idempotent(self):
        """반복 호출해도 예외가 나지 않아야 한다(stdout 이 이미 TextIOWrapper 가 아닌 것으로 리다이렉트됐을 수 있다)."""
        R._force_utf8_stdio()
        R._force_utf8_stdio()

    def test_force_utf8_stdio_tolerates_non_reconfigurable_stream(self):
        orig = sys.stdout
        try:
            sys.stdout = io.BytesIO()  # reconfigure 메서드가 없다
            R._force_utf8_stdio()      # 예외가 나면 안 된다
        finally:
            sys.stdout = orig


if __name__ == '__main__':
    unittest.main(verbosity=2)

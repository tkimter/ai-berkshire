#!/usr/bin/env python3
"""financial_rigor.py 회귀 테스트.

이미 고친 결함을 다룬다:

  BUG  Windows 콘솔 레거시 코드페이지(cp949) 인코딩 크래시
       verify_market_cap() 은 편차 > 5% 일 때 "❌ 경고" 를 출력하는데, U+274C 가
       레거시 코드페이지 콘솔에서 UnicodeEncodeError 를 내고 그대로 종료한다.

       피해가 특히 크다: **죽는 곳이 하필 「편차 초과」라는, 가장 눈에 띄어야 할 경고 경로다**.
       편차가 정상일 때 출력하는 ✅(U+2705)도 똑같이 죽지만, 그때는 사용자가 적어도
       종료 코드로 알아챌 수 있다. 반면 "검산 실패" 때 조용히 종료하면 스크립트가
       돌지 않았거나 통과한 것으로 오해하게 된다.

실행:  python tests/test_financial_rigor.py
"""

import io
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import financial_rigor as F  # noqa: E402

_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools')


def _run(args, encoding='cp949'):
    """흉내 낸 cp949 콘솔에서 financial_rigor.py 를 실행한다.

    도구가 stdout 을 UTF-8 로 강제하므로, 출력은 항상 UTF-8 로 디코딩한다.
    encoding='utf-8' 을 주면 PYTHONIOENCODING=utf-8 환경으로 실행한다.
    """
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = encoding
    env.pop('PYTHONUTF8', None)
    return subprocess.run(
        [sys.executable, os.path.join(_TOOLS, 'financial_rigor.py')] + args,
        capture_output=True, env=env)


def _out(proc):
    return proc.stdout.decode('utf-8', 'replace')


class TestLegacyConsoleSurvival(unittest.TestCase):

    def test_pass_path_prints_check_mark(self):
        """편차 0%, ✅(U+2705) 출력 —— cp949 에서 죽으면 안 된다."""
        proc = _run(['verify-market-cap', '--price', '8.00',
                     '--shares', '500000000', '--reported', '4000000000',
                     '--currency', 'CNY'])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertNotIn(b'UnicodeEncodeError', proc.stderr)
        self.assertIn('검증 통과', _out(proc))

    def test_fail_path_prints_cross_mark(self):
        """편차 초과, ❌(U+274C) 출력 —— 이 경로가 원래 bug 의 발생 지점이다."""
        proc = _run(['verify-market-cap', '--price', '8.00',
                     '--shares', '500000000', '--reported', '40.00',
                     '--currency', 'CNY'])
        self.assertEqual(
            proc.returncode, 0,
            "편차 초과 경고 경로가 cp949 콘솔에서 죽었다:\n"
            + proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertNotIn(b'UnicodeEncodeError', proc.stderr)
        self.assertIn('❌', _out(proc),
                      "경고 기호는 (대체 문자로라도) 출력되어야 하며, 조용히 종료하면 안 된다")
        self.assertIn('경고', _out(proc))

    def test_warn_path_prints_warning_sign(self):
        """편차 1%~5%, ⚠️(U+26A0 U+FE0F, 변형 선택자 포함) 출력."""
        # 8.00 × 500,000,000 = 4,000,000,000. 보고서 값을 3% 키워 경고 구간을 건드린다
        proc = _run(['verify-market-cap', '--price', '8.00',
                     '--shares', '500000000', '--reported', '4120000000',
                     '--currency', 'CNY'])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertNotIn(b'UnicodeEncodeError', proc.stderr)

    def test_cross_validate_under_cp949(self):
        proc = _run(['cross-validate', '--field', '2025 매출',
                     '--values', '{"출처 갑":1234567890.12,"출처 을":1234567890.12}',
                     '--unit', '위안'])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertNotIn(b'UnicodeEncodeError', proc.stderr)
        self.assertIn('출처 갑', _out(proc))

    def test_cross_validate_korean_unit_utf8(self):
        """--unit 에 한국어 단위를 주면 수치 뒤에 그대로 붙는다(PYTHONIOENCODING=utf-8)."""
        proc = _run(['cross-validate', '--field', '매출',
                     '--values', '{"사업보고서":12345,"Yahoo":12345}',
                     '--unit', '억 위안'], encoding='utf-8')
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertIn('12,345.00 억 위안', _out(proc))

    def test_three_scenario_under_cp949(self):
        proc = _run(['three-scenario', '--price', '8.00', '--eps', '0.5000',
                     '--shares', '5.0000', '--growth', '0.15', '0.03', '-0.10',
                     '--pe', '22', '15', '10', '--years', '3',
                     '--currency', 'CNY'])
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode('utf-8', 'replace')[-800:])
        self.assertNotIn(b'UnicodeEncodeError', proc.stderr)
        for name in ('낙관 (Bull)', '중립 (Base)', '비관 (Bear)'):
            self.assertIn(name, _out(proc))


class TestForceUtf8Stdio(unittest.TestCase):

    def test_idempotent(self):
        F._force_utf8_stdio()
        F._force_utf8_stdio()

    def test_tolerates_non_reconfigurable_stream(self):
        orig = sys.stdout
        try:
            sys.stdout = io.BytesIO()  # reconfigure 메서드가 없다
            F._force_utf8_stdio()      # 예외가 나면 안 된다
        finally:
            sys.stdout = orig


class TestFmtNumberKoreanUnits(unittest.TestCase):

    def test_eok_units(self):
        self.assertEqual(F.fmt_number(F.exact(7518), '억'), '7518.00억')
        self.assertEqual(F.fmt_number(F.exact(12345), '억'), '1.23조')
        self.assertEqual(F.fmt_number(F.exact(12345), '억위안'), '1.23조위안')

    def test_non_eok_units_unchanged(self):
        self.assertEqual(F.fmt_number(F.exact(4e9), ''), '4.00B')


class TestMarketCapMathUnaffected(unittest.TestCase):
    """인코딩 수정이 계산 로직을 건드리지 않았는지 확인한다."""

    def test_exact_match_returns_true(self):
        self.assertTrue(F.verify_market_cap(8.00, 500000000, 4000000000, 'CNY'))

    def test_gross_mismatch_returns_false(self):
        self.assertFalse(F.verify_market_cap(8.00, 500000000, 40.00, 'CNY'))


if __name__ == '__main__':
    unittest.main(verbosity=2)

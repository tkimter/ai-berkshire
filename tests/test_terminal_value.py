#!/usr/bin/env python3
"""terminal_value.py 회귀 테스트(issue #96 flip 스트레스 테스트 포함).

범위:
  - stress_pass / flip_analysis: r±Δ 하에서 결론의 반전과 안정. 통화 구간 밖 구간은 판정에 참여하지 않는다
  - flip CLI: --currency 필수, 구간 밖 표시, 인라인 파라미터 / --config 로 신규 회사 지원
  - 기존 pe / evaluate 가 깨지지 않는다

실행:  python3 tests/test_terminal_value.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import terminal_value as TV  # noqa: E402

_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools')
_TV = os.path.join(_TOOLS, 'terminal_value.py')


def _run(args):
    # 하위 프로세스 출력은 UTF-8 로 고정한다(Windows 콘솔 코드페이지 cp949 에 좌우되지 않게).
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, _TV] + args,
        capture_output=True, text=True, encoding='utf-8', env=env)


class TestStressPass(unittest.TestCase):

    def test_covers_cost_of_capital(self):
        self.assertTrue(TV.stress_pass(10.0, 0.10))
        self.assertTrue(TV.stress_pass(10.5, 0.10))
        self.assertFalse(TV.stress_pass(9.9, 0.10))
        self.assertIsNone(TV.stress_pass(None, 0.10))


class TestFlipAnalysis(unittest.TestCase):

    def test_tencent_hkd_style_flips_at_pm_2pp(self):
        """Issue #96 / PR #108 review: HKD 구간 [9%, 11.5%].
        r=10%±2pp 일 때 8%/12% 두 구간은 구간 밖이라 참고용이며 반전 판정에 참여하지 않는다.
        8% 구간이 "통과" 하더라도 이를 근거로 반전을 보고해서는 안 된다(그러면 r 을 낮춰서 사는 것이다)."""
        spec = TV.PRESET['텐센트']
        result = TV.flip_analysis(
            spec, r=0.10, delta=0.02, g_shift=-0.01, rf=TV.RF['USD'],
            band=TV.CURRENCY_BANDS['HKD'])
        self.assertEqual(len(result['rates']), 3)
        for got, want in zip(result['rates'], (0.08, 0.10, 0.12)):
            self.assertAlmostEqual(got, want)
        self.assertEqual(result['in_band'], (False, True, False))
        self.assertTrue(result['passes'][0], 'r-2pp=8% 는 수치상 통과하지만 구간 밖이다')
        self.assertFalse(result['passes'][1], '기준 r=10% 는 미통과여야 한다')
        self.assertFalse(result['flipped'], '구간 밖 구간이 반전을 일으켜서는 안 된다')

    def test_tencent_hkd_pm_1pp_in_band_stable(self):
        """메인테이너 재현: ±1pp 3개 구간이 모두 구간 안, 기대 IRR 7.66%/6.30%/5.11%, 전부 미통과 → 안정."""
        result = TV.flip_analysis(
            TV.PRESET['텐센트'], r=0.10, delta=0.01, g_shift=-0.01, rf=TV.RF['USD'],
            band=TV.CURRENCY_BANDS['HKD'])
        self.assertEqual(result['in_band'], (True, True, True))
        for got, want in zip(result['means'], (7.66, 6.30, 5.11)):
            self.assertAlmostEqual(got, want, places=2)
        self.assertTrue(all(p is False for p in result['passes']))
        self.assertFalse(result['flipped'])

    def test_flip_inside_band_is_reported(self):
        """CNY 구간 [6%, 9%] 안에서 r=7.5%±1pp: 6.5%/7.5% 통과, 8.5% 미통과 → 구간 안 반전."""
        result = TV.flip_analysis(
            TV.PRESET['텐센트'], r=0.075, delta=0.01, g_shift=-0.01,
            band=TV.CURRENCY_BANDS['CNY'])
        self.assertEqual(result['in_band'], (True, True, True))
        self.assertEqual(result['passes'], [True, True, False])
        self.assertTrue(result['flipped'])

    def test_no_band_keeps_all_tiers(self):
        """band=None(라이브러리 함수 직접 호출)이면 구간 필터를 하지 않고 원래 판정을 유지한다."""
        result = TV.flip_analysis(
            TV.PRESET['텐센트'], r=0.10, delta=0.02, g_shift=-0.01, rf=TV.RF['USD'])
        self.assertEqual(result['in_band'], (None, None, None))
        self.assertTrue(result['flipped'])

    def test_stable_when_always_fail(self):
        """높은 r + 낮은 ROIC 프리셋에서는 ±2pp 안에서 항상 미통과 → 반전 없음."""
        # MiniMax 는 높은 r 하에서 기대 IRR 이 크게 음수라 ±2pp 에서도 미통과다
        spec = TV.PRESET['MiniMax']
        result = TV.flip_analysis(
            spec, r=0.10, delta=0.02, g_shift=-0.01, rf=TV.RF['CNY'])
        self.assertFalse(result['flipped'])
        self.assertTrue(all(p is False for p in result['passes']))

    def test_delta_must_be_positive(self):
        with self.assertRaises(ValueError):
            TV.flip_analysis(TV.PRESET['텐센트'], r=0.10, delta=0.0)


_TENCENT_INLINE = ['--roic', '0.20', '--g', '0.015,0.030,0.040', '--p', '0.35,0.50,0.15',
                   '--irr10', '0.3,9.3,15.4', '--k', '0.02']


class TestFlipCLI(unittest.TestCase):

    def test_flip_cli_out_of_band_tiers_excluded(self):
        """메인테이너 review 시나리오: HKD r=10%±2pp, 8% 구간은 구간 밖으로 표시되고 반전을 일으키지 않는다."""
        proc = _run([
            'flip', '--name', '텐센트', '--r', '0.10', '--delta', '0.02',
            '--currency', 'HKD', '--g-shift', '-0.01', '--rf', '0.047',
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        out = proc.stdout
        self.assertIn('【안정】', out)
        self.assertNotIn('【반전】', out)
        self.assertEqual(out.count('구간 밖, 참고용'), 2)
        self.assertIn('비중 스트레스 테스트', out)
        self.assertIn('매수/보유/회피에 대한 유일한 거부권이 아니다', out)
        self.assertIn('매수 결론에 맞추려고', out)

    def test_flip_cli_reports_flip_inside_band(self):
        proc = _run([
            'flip', '--name', '텐센트', '--r', '0.075', '--delta', '0.01',
            '--currency', 'CNY', '--g-shift', '-0.01',
        ])
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertIn('【반전】', proc.stdout)
        self.assertNotIn('구간 밖', proc.stdout.split('판정 규칙')[1])
        self.assertIn('통과', proc.stdout)
        self.assertIn('미통과', proc.stdout)

    def test_flip_cli_requires_currency(self):
        proc = _run(['flip', '--name', '텐센트', '--r', '0.10'])
        self.assertEqual(proc.returncode, 2)
        self.assertIn('--currency', proc.stderr)

    def test_flip_cli_base_r_out_of_band_rejected(self):
        proc = _run(['flip', '--name', '텐센트', '--r', '0.08', '--currency', 'HKD'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('【반려】', proc.stdout)

    def test_flip_cli_unknown_company(self):
        proc = _run(['flip', '--name', '존재하지않는회사', '--r', '0.10', '--currency', 'USD'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('알 수 없는 회사', proc.stderr)
        self.assertIn('인라인 파라미터', proc.stderr)

    def test_flip_cli_inline_params_match_preset(self):
        """신규 회사: 인라인 파라미터와 같은 값의 프리셋은 출력이 완전히 같다."""
        common = ['--r', '0.10', '--delta', '0.01', '--currency', 'HKD', '--g-shift', '-0.01']
        inline = _run(['flip', '--name', '텐센트'] + _TENCENT_INLINE + common)
        preset = _run(['flip', '--name', '텐센트'] + common)
        self.assertEqual(inline.returncode, 0, inline.stderr[-800:])
        self.assertEqual(inline.stdout, preset.stdout)

    def test_flip_cli_inline_negative_irr10(self):
        """비관 구간 IRR 이 음수인 것은 흔하다: --irr10=-2,8,14 표기를 쓸 수 있다(docstring 예시)."""
        proc = _run(['flip', '--name', '어떤회사', '--roic', '0.18', '--g', '0.015,0.03,0.04',
                     '--p', '0.35,0.50,0.15', '--irr10=-2.0,8.0,14.0', '--k', '0.01',
                     '--r', '0.10', '--currency', 'USD'])
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertIn('어떤회사', proc.stdout)
        self.assertIn('기준 r', proc.stdout)

    def test_flip_cli_inline_params_incomplete(self):
        proc = _run(['flip', '--name', '신규회사', '--roic', '0.2', '--r', '0.10',
                     '--currency', 'USD'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('--g', proc.stderr)

    def test_flip_cli_inline_probs_must_sum_to_one(self):
        args = list(_TENCENT_INLINE)
        args[args.index('--p') + 1] = '0.3,0.5,0.3'
        proc = _run(['flip', '--name', '신규회사'] + args + ['--r', '0.10', '--currency', 'USD'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('확률의 합', proc.stderr)

    def test_flip_cli_config_file(self):
        """신규 회사: skill 에 적힌 JSON 형식대로 --config 로 전달한다."""
        cfg = {'신규회사': {'roic': 0.20, 'g': [0.015, 0.030, 0.040],
                        'p': [0.35, 0.50, 0.15], 'irr10': [0.3, 9.3, 15.4], 'k': 0.02}}
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                         encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False)
            path = fh.name
        try:
            proc = _run(['flip', '--name', '신규회사', '--config', path, '--r', '0.10',
                         '--delta', '0.01', '--currency', 'HKD', '--g-shift', '-0.01'])
        finally:
            os.unlink(path)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertIn('+6.30%', proc.stdout)
        self.assertIn('【안정】', proc.stdout)


class TestAuditCLI(unittest.TestCase):
    """--discrete-risks 귀속 값(한국어)과 판정 라벨."""

    _BASE = ['audit', '--currency', 'USD', '--r', '0.10', '--roic', '0.20',
             '--g', '0.015,0.03,0.04', '--rf', '0.047']

    def test_audit_accepts_korean_placements(self):
        proc = _run(self._BASE + ['--discrete-risks',
                                  '상장폐지:시나리오,VIE:테일 구간,규제:확률,지정학:미모델링'])
        self.assertEqual(proc.returncode, 0, proc.stdout[-800:] + proc.stderr[-400:])
        self.assertIn('【통과】', proc.stdout)
        self.assertIn('미모델링', proc.stdout)

    def test_audit_rejects_discount_rate_placement(self):
        proc = _run(self._BASE + ['--discrete-risks', '상장폐지:할인율'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('【반려】', proc.stdout)

    def test_audit_rejects_unknown_placement(self):
        proc = _run(self._BASE + ['--discrete-risks', '상장폐지:모름'])
        self.assertEqual(proc.returncode, 1)
        self.assertIn('인식할 수 없다', proc.stdout)


class TestCoreRegression(unittest.TestCase):

    def test_exit_pe_basic(self):
        pe, retention, numerator, spread = TV.exit_pe(0.20, 0.02, 0.06)
        self.assertIsNotNone(pe)
        self.assertAlmostEqual(spread, 0.04)
        self.assertAlmostEqual(retention, 0.10)
        self.assertAlmostEqual(pe, numerator / spread)

    def test_pe_cli(self):
        proc = _run(['pe', '--roic', '0.20', '--g', '0.02', '--r', '0.06'])
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        self.assertIn('엑시트 PE', proc.stdout)


if __name__ == '__main__':
    unittest.main()

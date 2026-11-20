#!/usr/bin/env python3
"""실제 임시 Git 저장소로 회귀 검증한다: 색인이 보고서 원문보다 먼저 공개되면 안 된다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "reports/엔비디아/한글 과거보고서.md"
STAGED = "reports/7개사투자연구-20261002/엔비디아/보고서-20261002.md"


class ReportsIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "tools").mkdir()
        (self.repo / "reports/_index").mkdir(parents=True)
        shutil.copy(ROOT / "tools/reports_index.py", self.repo / "tools/reports_index.py")
        shutil.copy(ROOT / "reports/_index/config.json", self.repo / "reports/_index/config.json")
        self.write("README.md", "# 테스트 색인\n")
        self.write(BASELINE, "# 과거 보고서\n")
        self.git("init", "-q")
        self.git("config", "core.quotePath", "true")
        self.git("add", ".")
        self.git("-c", "user.name=Index Test", "-c", "user.email=index@example.invalid",
                 "commit", "-qm", "baseline")

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-30T12:00:00+08:00",
                   GIT_COMMITTER_DATE="2026-09-30T12:00:00+08:00")
        return subprocess.run(["git", *args], cwd=self.repo, env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=True)

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_index(self, *args, expected=0):
        result = subprocess.run([sys.executable, "tools/reports_index.py", *args],
                                cwd=self.repo, capture_output=True, text=True, encoding="utf-8",
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def items(self):
        return json.loads((self.repo / "reports/index.json").read_text(encoding="utf-8"))["reports"]

    def test_local_drafts_ignored_files_and_intent_to_add_are_not_published(self):
        self.write(".gitignore", "reports/비공개/\n")
        for path in (STAGED, "reports/비공개/보고서.md", "reports/자리표시/보고서.md"):
            self.write(path, "# 로컬 미공개 제목\n")
        self.git("add", "-N", "reports/자리표시/보고서.md")
        output = self.run_index().stdout
        self.assertEqual([i["path"] for i in self.items()], [BASELINE])
        self.assertNotIn("로컬 미공개 제목", (self.repo / "reports/README.md").read_text(encoding="utf-8"))
        self.assertNotIn("7개사투자연구", output)
        self.run_index("--check")

    def test_staged_report_is_included_and_unstaging_invalidates_index(self):
        path = STAGED
        self.write(path, "# 새 보고서\n")
        self.git("add", "--", path)
        self.run_index()
        self.assertIn(path, [i["path"] for i in self.items()])
        self.run_index("--check")
        self.git("reset", "-q", "HEAD", "--", path)
        before = (self.repo / "reports/index.json").read_bytes()
        self.run_index("--check", expected=1)
        self.assertEqual(before, (self.repo / "reports/index.json").read_bytes())
        self.run_index()
        self.assertNotIn(path, [i["path"] for i in self.items()])

    def test_removing_report_from_git_excludes_remaining_working_copy(self):
        self.run_index()
        path = BASELINE
        self.git("rm", "--cached", "--", path)
        self.assertTrue((self.repo / path).is_file())
        self.run_index("--check", expected=1)
        self.run_index()
        self.assertEqual(self.items(), [])

    def test_git_failure_does_not_overwrite_published_index(self):
        self.run_index()
        before = (self.repo / "reports/index.json").read_bytes()
        # Windows에서는 git 객체 파일이 읽기 전용이라 그대로는 지워지지 않는다
        for dirpath, _, filenames in os.walk(self.repo / ".git"):
            for name in filenames:
                os.chmod(os.path.join(dirpath, name), 0o700)
        shutil.rmtree(self.repo / ".git")
        result = self.run_index(expected=1)
        self.assertIn("Git 스테이징 영역을 읽을 수 없어", result.stderr)
        self.assertEqual(before, (self.repo / "reports/index.json").read_bytes())

    def test_non_ascii_git_date_is_independent_of_quote_path_config(self):
        self.run_index()
        self.assertEqual(self.items()[0]["date"], "2026-09-30")
        self.assertEqual(self.items()[0]["date_source"], "git")

    def test_index_keys_and_keyword_rules_are_korean(self):
        cases = {
            "reports/엔비디아/엔비디아-실적-2026Q3.md": ("기업", "실적"),
            "reports/엔비디아/엔비디아-게시글-20261002.md": ("기업", "게시글"),
            "reports/엔비디아/증빙/출처목록.md": ("기업", "초안"),
            "reports/엔비디아-AMD-비교-20261002.md": ("테마", "비교"),
        }
        for path in cases:
            self.write(path, "# 제목 [a]|b\n\n작성일: 2026년 9월 7일\n")
        self.write("reports/엔비디아/덮어쓰기.md", "---\ntype: 밸류·비중\n---\n# 덮어쓰기\n")
        self.git("add", "reports")
        self.run_index()
        got = {i["path"]: i for i in self.items()}
        for path, (bucket, rtype) in cases.items():
            self.assertEqual((got[path]["bucket"], got[path]["type"]), (bucket, rtype), path)
        self.assertEqual(got[BASELINE]["type"], "연구")
        self.assertEqual(got["reports/엔비디아/덮어쓰기.md"]["type"], "밸류·비중")
        self.assertEqual(got["reports/엔비디아/엔비디아-실적-2026Q3.md"]["date"], "2026-09-07")
        self.assertEqual(got["reports/엔비디아/엔비디아-실적-2026Q3.md"]["date_source"], "본문")
        readme = (self.repo / "reports/README.md").read_text(encoding="utf-8")
        self.assertIn("[제목 (a)¦b]", readme)
        self.assertNotIn("출처목록", readme)
        generated = readme + (self.repo / "reports/index.json").read_text(encoding="utf-8")
        # 생성물에 한자(CJK 통합 한자 영역)가 없어야 한다
        self.assertNotRegex(generated, "[%s-%s]" % (chr(0x4E00), chr(0x9FFF)))


if __name__ == "__main__":
    unittest.main()

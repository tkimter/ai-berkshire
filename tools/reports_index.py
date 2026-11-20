#!/usr/bin/env python3
"""reports/ 아래 Git에 올라간 보고서를 훑어 연구 색인을 만든다.

산출물 두 가지:
  reports/index.json  —— 기계가 읽는 목록. 스크립트·웹페이지용
  reports/README.md   —— 사람이 읽는 색인. GitHub의 보고서 입구

메타데이터 우선순위: 파일의 YAML front-matter > 파일명 > 본문 > git 커밋 날짜.
보고서 파일 자체는 수정하지 않는다.
새 보고서는 먼저 git add 해야 한다. 미추적·무시·intent-to-add 파일은 공개 색인에 넣지 않는다.

언어: 보고서는 한국어 기준이다. 기존 중국어 보고서도 계속 색인되도록 파일명 키워드는
한국어·중국어를 모두 인식한다. index.json의 bucket/type 값은 tools/build_site.py가
그대로 읽으므로 내부 키(중국어)를 유지하고, 사람이 읽는 README에서만 한국어 라벨로 바꿔 보여 준다.

사용법:
  python3 tools/reports_index.py            # 색인 생성
  python3 tools/reports_index.py --check     # 갱신 필요 여부만 확인 (CI용, 파일을 쓰지 않음)
"""
import json
import os
import re
import subprocess
import sys
from collections import defaultdict, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "reports")
CONFIG = os.path.join(REPORTS, "_index", "config.json")

DATE_IN_NAME = re.compile(r"(20[2-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")
DATE_IN_BODY = re.compile(r"(20[2-3]\d)\s*[-/年년]\s*(\d{1,2})\s*[-/月월]\s*(\d{1,2})")
H1 = re.compile(r"^#\s+(.+?)\s*$")

# 보고서 유형: 위에서부터 차례로 맞춰 보고 먼저 걸린 것으로 정한다.
# 왼쪽 라벨은 index.json에 들어가는 내부 키(변경 금지, build_site.py가 사용), 키워드는 한·중·영 모두.
TYPE_RULES = [
    # 감사/재검토류 완성 보고서는 여기 해당하지 않는다. 중간 산출물은 is_draft가 가린다
    ("底稿", ["研究底稿", "核验", "评审", "verify", "底稿", "对账",
              "연구초안", "초안", "독자리뷰", "검증기록", "대사"]),
    ("财报", ["earnings", "财报", "中报", "年报", "季报", "业绩", "电话会", "q1", "q2", "q3", "q4",
              "실적", "분기보고", "반기보고", "사업보고", "컨퍼런스콜"]),
    ("公众号", ["公众号", "wechat", "推文", "공식계정"]),
    ("深度系列", ["看懂", "深度研究", "deep-dive", "深度投研", "제대로알기", "심층연구"]),
    ("横评对比", ["横评", "对比", "vs", "对决", "pk", "换仓", "轮动", "비교", "대결", "로테이션"]),
    ("组织管理", ["7s", "管理层", "组织", "management", "경영진", "조직"]),
    ("估值仓位", ["估值", "赔率", "凯利", "仓位", "valuation", "fair_value", "终值",
                  "밸류에이션", "배당률", "켈리", "비중", "터미널밸류", "종말가치"]),
    ("筛选", ["funnel", "筛选", "召回", "screen", "候选池", "스크리닝", "후보풀", "퍼널"]),
]

# 사람이 읽는 색인(reports/README.md, 루트 README)에 쓰는 한국어 표시 라벨
TYPE_KO = {
    "研究": "연구", "财报": "실적", "公众号": "공식계정", "深度系列": "심층시리즈",
    "横评对比": "비교", "组织管理": "조직·경영", "估值仓位": "밸류·비중",
    "筛选": "스크리닝", "底稿": "초안",
}
# front-matter의 type: 은 한국어 라벨로 써도 내부 키로 바꿔 받는다
TYPE_FROM_KO = {v: k for k, v in TYPE_KO.items()}
WECHAT_MARKS = ("公众号", "공식계정")
ROOT_GROUP = "종합·비교"


def type_label(t):
    return TYPE_KO.get(t, t)


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def git_report_paths():
    """Git 스테이징 영역의 경로. 아직 커밋 대상이 아닌 로컬 원고는 색인에 올리지 않는다."""
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "--cached", "-z", "--", "reports/"],
            cwd=ROOT, stderr=subprocess.DEVNULL)
        # git add -N 한 파일은 ls-files에 나오지만 실제 내용은 다음 커밋에 들어가지 않는다.
        intent = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=A", "-z", "--", "reports/"],
            cwd=ROOT, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Git 스테이징 영역을 읽을 수 없어 생성을 중단한다. 커밋되지 않은 로컬 파일이 공개되는 것을 막기 위해서다") from exc
    paths = {os.fsdecode(p) for p in raw.split(b"\0") if p}
    return paths - {os.fsdecode(p) for p in intent.split(b"\0") if p}


def git_dates():
    """한 번 훑어서 파일별 최근 커밋 날짜를 얻는다."""
    out = {}
    try:
        raw = subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "log",
             "--pretty=format:__D__%ad", "--date=short", "--name-only"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        ).decode("utf-8", "replace")
    except Exception:
        return out
    cur = None
    for line in raw.splitlines():
        if line.startswith("__D__"):
            cur = line[5:].strip()
        elif line.strip() and cur and line not in out:
            out[line] = cur
    return out


def parse_front_matter(lines):
    """아주 단순한 YAML front-matter 해석. 첫 줄 --- 부터 다음 --- 사이의 key: value만 읽는다."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, i + 1
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return {}, 0


def read_head(path, n=40):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [next(f).rstrip("\n") for _ in range(n)]
    except StopIteration:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:
        return []


def guess_type(name, relpath):
    hay = (name + " " + relpath).lower()
    for label, keys in TYPE_RULES:
        for k in keys:
            if k in hay:
                return label
    return "研究"  # 내부 키. 표시 라벨은 TYPE_KO


def is_draft(relr, cfg):
    """중간 산출물 판정: 증빙·감사·재계산·초안 등은 사람이 읽는 색인에 넣지 않는다. 규칙은 config.json의 drafts 참고."""
    rules = cfg.get("drafts") or {}
    parts = relr.split("/")
    stem = re.sub(r"\.md$", "", parts[-1])
    if any(mark in stem for mark in WECHAT_MARKS):
        return False
    dirs = [d.lower() for d in parts[:-1]]
    draft_dirs = {d.lower() for d in rules.get("dirs", [])}
    if any(d in draft_dirs for d in dirs):
        return True
    for d in parts[:-1]:
        base = display_name(d)
        if any(base.endswith(suf) for suf in rules.get("dir_suffixes", [])):
            return True
    stem = display_name(stem).lower()
    return any(re.search(pat, stem) for pat in rules.get("file_patterns", []))


def guess_date(meta, filename, parent, head, gitmap, relpath):
    if meta.get("date"):
        d = meta["date"].replace("/", "-")
        if re.match(r"^20\d\d-\d\d-\d\d$", d):
            return d, "front-matter"
    for src in (filename, parent):
        m = DATE_IN_NAME.search(src)
        if m:
            return "%s-%s-%s" % m.groups(), "파일명"
    for line in head[:15]:
        m = DATE_IN_BODY.search(line)
        if m:
            y, mo, dy = m.groups()
            return "%s-%02d-%02d" % (y, int(mo), int(dy)), "본문"
    if relpath in gitmap:
        return gitmap[relpath], "git"
    return "", "없음"


def bucket_of(top, cfg):
    top = cfg["aliases"].get(top, top)
    if top in cfg["screens"]:
        return "筛选池", top
    if top in cfg["themes"]:
        return "专题", top
    if top in cfg["masters"]:
        return "大师研究", top
    if top in cfg["other"]:
        return "其他", top
    return "公司", top


def collect(cfg, gitmap):
    items = []
    unknown_dirs = set()
    tracked = git_report_paths()
    excluded = []
    known = (set(cfg["themes"]) | set(cfg["masters"]) | set(cfg["screens"])
             | set(cfg["other"]) | set(cfg.get("companies", [])))
    for dirpath, dirnames, filenames in os.walk(REPORTS):
        dirnames[:] = [d for d in dirnames if d not in cfg["skip_dirs"]]
        for fn in filenames:
            if not fn.endswith(".md") or fn in cfg["skip_files"]:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            if rel not in tracked:
                excluded.append(rel)
                continue
            relr = os.path.relpath(full, REPORTS).replace(os.sep, "/")
            parts = relr.split("/")
            top = parts[0] if len(parts) > 1 else ""
            head = read_head(full)
            meta, _ = parse_front_matter(head)
            title = meta.get("title", "")
            if not title:
                for line in head:
                    m = H1.match(line)
                    if m:
                        title = m.group(1)
                        break
            if not title:
                title = re.sub(r"-?\d{8}$", "", fn[:-3])
            title = re.sub(r"[*`]", "", title).strip()

            if top:
                bucket, group = bucket_of(top, cfg)
                if bucket == "公司" and top not in known and top not in cfg["aliases"]:
                    unknown_dirs.add(top)
            else:
                bucket, group = "专题", ROOT_GROUP

            date, dsrc = guess_date(meta, fn, parts[-2] if len(parts) > 1 else "", head, gitmap, rel)
            series = parts[1] if len(parts) > 2 else ""
            rtype = meta.get("type") or ("底稿" if is_draft(relr, cfg) else guess_type(fn, relr))
            rtype = TYPE_FROM_KO.get(rtype, rtype)
            items.append(OrderedDict([
                ("title", title),
                ("path", rel),
                ("bucket", bucket),
                ("group", group),
                ("series", series),
                ("type", rtype),
                ("date", date),
                ("date_source", dsrc),
                ("ticker", cfg["tickers"].get(group, "")),
            ]))
    items.sort(key=lambda x: (x["date"], x["path"]), reverse=True)
    return items, sorted(unknown_dirs), sorted(excluded)


def display_name(name):
    return re.sub(r"-20[2-3]\d[01]\d[0-3]\d$", "", name) or name


UNSAFE = {"%": "%25", " ": "%20", "(": "%28", ")": "%29", "#": "%23", "?": "%3F",
          "[": "%5B", "]": "%5D", "<": "%3C", ">": "%3E", '"': "%22"}


def url_path(path):
    """Markdown 링크를 깨뜨리는 문자만 이스케이프한다. 한글·한자는 눈으로 대조할 수 있게 그대로 둔다."""
    return "".join(UNSAFE.get(c, c) for c in path)


def md_link(text, path):
    text = text.replace("[", "〔").replace("]", "〕").replace("|", "丨")
    return "[%s](%s)" % (text, url_path(path.replace("reports/", "", 1)))


def published(items):
    """사람이 읽는 색인에는 완성 보고서만 싣는다. 초안·증빙·감사 등 중간 산출물은 index.json에만 남긴다."""
    return [i for i in items if i["type"] != "底稿"]


def render(items, cfg):
    items = published(items)
    by_bucket = defaultdict(lambda: defaultdict(list))
    for it in items:
        by_bucket[it["bucket"]][it["group"]].append(it)

    latest = max((i["date"] for i in items if i["date"]), default="")
    L = []
    L.append("# 연구 보고서 색인")
    L.append("")
    L.append("> 이 파일은 `tools/reports_index.py`가 자동 생성한다. 손으로 고치지 않는다.")
    L.append("> 새 보고서는 먼저 `git add` 한 뒤 `python3 tools/reports_index.py`를 실행하고, 보고서와 색인을 함께 커밋한다.")
    L.append("> 완성 보고서만 싣는다. 증빙·감사·재계산·초안 등 중간 산출물은 여기에 없으며 전체 목록은 `index.json`에 있다.")
    L.append("")
    L.append("**보고서 %d건** · **기업 %d곳** · **테마 %d개** · 최근 업데이트 %s" % (
        len(items), len(by_bucket["公司"]), len(by_bucket["专题"]), latest or "—"))
    L.append("")
    L.append("[최근 업데이트](#최근-업데이트) · [기업별](#기업별) · [테마 연구](#테마-연구) · "
             "[대가 연구](#대가-연구) · [스크리닝 풀](#스크리닝-풀)")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## 최근 업데이트")
    L.append("")
    L.append("| 날짜 | 보고서 | 소속 | 유형 |")
    L.append("|------|------|------|------|")
    seen = defaultdict(int)
    shown = []
    for it in items:
        if it["bucket"] == "筛选池":
            continue
        key = it["group"] + "/" + (it["series"] or "")
        if seen[key] >= 3:
            continue
        seen[key] += 1
        shown.append(it)
        if len(shown) >= 40:
            break
    for it in shown:
        L.append("| %s | %s | %s | %s |" % (
            it["date"] or "—", md_link(it["title"], it["path"]),
            display_name(it["group"]), type_label(it["type"])))
    L.append("")
    L.append("---")
    L.append("")

    def section(title, bucket, anchor_note=""):
        groups = by_bucket.get(bucket, {})
        if not groups:
            return
        L.append("## %s" % title)
        L.append("")
        if anchor_note:
            L.append(anchor_note)
            L.append("")
        order = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        for name, lst in order:
            lst = sorted(lst, key=lambda x: (x["date"], x["title"]), reverse=True)
            last = lst[0]["date"] or "—"
            L.append("<details>")
            L.append("<summary><b>%s</b> · %d건 · 최근 %s</summary>" % (
                display_name(name), len(lst), last))
            L.append("")
            cur_series = None
            for it in lst:
                if it["series"] and it["series"] != cur_series:
                    cur_series = it["series"]
                    L.append("")
                    L.append("*%s*" % display_name(cur_series))
                    L.append("")
                elif not it["series"] and cur_series is not None:
                    cur_series = None
                    L.append("")
                L.append("- `%s` %s — %s" % (it["date"] or "  —  ", md_link(it["title"], it["path"]), type_label(it["type"])))
            L.append("")
            L.append("</details>")
            L.append("")
        L.append("---")
        L.append("")

    section("기업별", "公司")
    section("테마 연구", "专题")
    section("대가 연구", "大师研究")

    screens = by_bucket.get("筛选池", {})
    if screens:
        L.append("## 스크리닝 풀")
        L.append("")
        L.append("> 아래는 스크리닝과 추론의 **중간 산출물**이며 완성 보고서가 아니다. 재현과 추적용이다.")
        L.append("")
        L.append("| 풀 | 파일 수 | 최근 업데이트 |")
        L.append("|------|--------|----------|")
        for name, lst in sorted(screens.items(), key=lambda kv: -len(kv[1])):
            last = max((x["date"] for x in lst if x["date"]), default="—")
            L.append("| [%s](%s) | %d | %s |" % (
                display_name(name), url_path(name), len(lst), last))
        L.append("")
    return "\n".join(L) + "\n"


ROOT_README = os.path.join(ROOT, "README.md")
MARK_START = "<!-- REPORTS-INDEX:START tools/reports_index.py가 자동 갱신한다. 손으로 고치지 않는다 -->"
MARK_END = "<!-- REPORTS-INDEX:END -->"
BANNER_START = "<!-- REPORTS-BANNER:START tools/reports_index.py가 자동 갱신한다. 손으로 고치지 않는다 -->"
BANNER_END = "<!-- REPORTS-BANNER:END -->"


def index_stats(items):
    items = published(items)
    groups = defaultdict(set)
    for it in items:
        if it["bucket"] != "筛选池":
            groups[it["bucket"]].add(it["group"])
    latest = max((i["date"] for i in items if i["date"]), default="—")
    return len(items), len(groups["公司"]), len(groups["专题"]), latest


def root_banner_block(items):
    """첫 화면 배너: 매일 갱신되는 내용의 입구. 본문 깊숙한 곳이 아니라 제목 영역에 둔다."""
    total, companies, themes, latest = index_stats(items)
    return "\n".join([
        BANNER_START,
        "",
        "> 📊 보고서 %d건 · 기업 %d곳 · 테마 %d개. 전체 목록은 [연구 보고서 색인](reports/README.md)에 있다. 최근 업데이트 %s."
        % (total, companies, themes, latest),
        "",
        BANNER_END,
    ])


def root_readme_block(items):
    """루트 README의 연구 색인 입구 블록을 만든다."""
    total, companies, themes, latest = index_stats(items)
    fresh = [i for i in published(items) if i["bucket"] != "筛选池"][:8]

    L = [MARK_START, ""]
    L.append("**📊 [전체 연구 색인 →](reports/README.md)** ｜ 보고서 %d건 · 기업 %d곳 · 테마 %d개 · 최근 업데이트 %s"
             % (total, companies, themes, latest))
    L.append("")
    L.append("최근 업데이트:")
    L.append("")
    L.append("| 날짜 | 보고서 | 소속 |")
    L.append("|------|------|------|")
    seen = defaultdict(int)
    rows = 0
    for it in fresh:
        if seen[it["group"]] >= 2:
            continue
        seen[it["group"]] += 1
        rows += 1
        L.append("| %s | [%s](%s) | %s |" % (
            it["date"] or "—",
            it["title"].replace("[", "〔").replace("]", "〕").replace("|", "丨"),
            url_path(it["path"]), display_name(it["group"])))
        if rows >= 6:
            break
    L.append("")
    L.append(MARK_END)
    return "\n".join(L)


def update_root_readme(items):
    if not os.path.exists(ROOT_README):
        return None, None
    old = open(ROOT_README, encoding="utf-8").read()
    new = old
    for start, end, builder in (
        (BANNER_START, BANNER_END, root_banner_block),
        (MARK_START, MARK_END, root_readme_block),
    ):
        if start in new and end in new:
            head = new.split(start)[0]
            tail = new.split(end, 1)[1]
            new = head + builder(items) + tail
    return old, new


def main():
    check = "--check" in sys.argv
    cfg = load_config()
    try:
        items, unknown, excluded = collect(cfg, git_dates())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    index_path = os.path.join(REPORTS, "index.json")
    readme_path = os.path.join(REPORTS, "README.md")
    payload = json.dumps(
        {"count": len(items), "published": len(published(items)),
         "drafts": len(items) - len(published(items)), "reports": items},
        ensure_ascii=False, indent=2) + "\n"
    readme = render(items, cfg)
    root_old, root_new = update_root_readme(items)

    if check:
        stale = []
        pairs = [(index_path, payload), (readme_path, readme)]
        if root_old is not None:
            pairs.append((ROOT_README, root_new))
        for p, new in pairs:
            old = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
            if old != new:
                stale.append(os.path.basename(p))
        if stale:
            print("색인이 오래됐다. python3 tools/reports_index.py 를 실행한다: " + ", ".join(stale))
            return 1
        print("색인이 최신 상태다")
        return 0

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(payload)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    if root_new is not None and root_new != root_old:
        with open(ROOT_README, "w", encoding="utf-8") as f:
            f.write(root_new)
        print("루트 README의 연구 색인 블록을 갱신했다")

    missing = [i for i in items if not i["date"]]
    print("보고서 %d건 색인 완료 -> reports/README.md, reports/index.json (완성 보고서 %d건, 초안 등 중간 산출물 %d건은 index.json에만 기록)"
          % (len(items), len(published(items)), len(items) - len(published(items))))
    if missing:
        print("  날짜를 알 수 없음: %d건" % len(missing))
    if excluded:
        print("  Git에 없는 로컬 보고서(무시 파일 포함) 제외: %d건. 공개하려면 먼저 git add 한 뒤 색인을 다시 만든다" % len(excluded))
    if unknown:
        print("  config.json의 companies 목록에 없는 새 폴더(기본값인 기업으로 처리): %s" % ", ".join(unknown))
    return 0


if __name__ == "__main__":
    sys.exit(main())

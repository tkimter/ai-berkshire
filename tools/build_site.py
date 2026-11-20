#!/usr/bin/env python3
"""Git에 올라간 보고서로 정적 읽기 사이트를 만든다. PC·휴대폰·전자잉크 리더에서 읽을 수 있다.

입력: reports/index.json(tools/reports_index.py가 생성), reports/ 아래 README.md, docs/ 아래 Markdown.
      모두 Git이 추적하는 파일만 쓴다.
출력: site/ 폴더. 프레임워크 없는 순수 HTML. 기업·테마·날짜·유형 네 축으로 색인을 만들고 사이트 내 검색과 RSS를 둔다.

index.json의 bucket/type 값(한국어)을 그대로 쓴다.
  bucket: 기업 / 테마 / 대가연구 / 스크리닝풀 / 기타
  type:   연구 / 실적 / 게시글 / 심층시리즈 / 비교 / 조직·경영 / 밸류·비중 / 스크리닝 / 초안

사용법: python3 tools/build_site.py [--out site]
의존성: markdown (pip install markdown)
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/tkimter/ai-berkshire"
# 사이트 공개 주소. 기본값은 저장소 URL에서 만든 GitHub Pages 주소이고, 환경변수 SITE_URL로 덮어쓴다.
SITE_URL = os.environ.get("SITE_URL") or "https://%s.github.io/%s/" % tuple(REPO_URL.rsplit("/", 2)[-2:])
if not SITE_URL.endswith("/"):
    SITE_URL += "/"
SITE_NAME = "AI Berkshire 리서치"
# 방문 통계: goatcounter.com에 가입한 뒤 사이트 코드(예: "aiberkshire")를 환경변수 GOATCOUNTER_CODE에 넣는다.
# 비워 두면 통계 스크립트를 넣지 않는다. 아무 페이지 주소 뒤에 #notrack 을 붙여 열면 그 기기는 집계에서 빠진다.
GOATCOUNTER = os.environ.get("GOATCOUNTER_CODE", "")
# Baidu 통계 사이트 ID(hm.js? 뒤의 32자). 환경변수 BAIDU_TONGJI_ID로 지정하며 비워 두면 넣지 않는다.
BAIDU_TONGJI = os.environ.get("BAIDU_TONGJI_ID", "")
FRONT = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)
H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
DATE8 = re.compile(r"(20[2-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".csv", ".json", ".txt", ".html"}

# index.json의 bucket 값
B_COMPANY, B_THEME, B_SCREEN = "기업", "테마", "스크리닝풀"
# index.json의 type 값. T_GUIDE는 이 사이트에서만 쓰는 값이다(폴더 README, 시리즈 안내)
T_RESEARCH, T_SCREEN, T_DRAFT, T_GUIDE = "연구", "스크리닝", "초안", "안내"
TYPE_ORDER = ["심층시리즈", "연구", "실적", "밸류·비중", "조직·경영", "비교", "게시글", "스크리닝", "초안"]
NOISE_BUCKETS = {B_SCREEN}


def sh(args):
    return subprocess.check_output(args, cwd=ROOT).decode("utf-8", "replace")


def tracked(prefix):
    out = subprocess.check_output(["git", "ls-files", "-z", "--", prefix], cwd=ROOT)
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def page_id(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def slug(name):
    # 글자·숫자가 아닌 것은 모두 "-"로 바꾼다. 한글은 그대로 URL에 남는다.
    s = re.sub(r"[\W_]+", "-", name).strip("-")
    return s or page_id(name)


CHOSEONG = "ㄱㄱㄴㄷㄷㄹㅁㅂㅂㅅㅅㅇㅈㅈㅊㅋㅌㅍㅎ"  # 된소리는 예사소리 칸에 넣는다


def initial(name):
    """기업 색인의 묶음 머리글자: 영문은 대문자, 한글은 첫소리, 그 밖은 #."""
    c = name.strip()[:1]
    if not c:
        return "#"
    if re.match(r"[A-Za-z]", c):
        return c.upper()
    if "가" <= c <= "힣":
        return CHOSEONG[(ord(c) - 0xAC00) // 588]
    return "#"


def read(path):
    full = os.path.join(ROOT, path)
    if os.path.isfile(full):
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read()
    return blob(path).decode("utf-8", "replace")


def blob(path):
    """Git에 올라간 내용을 읽는다. 작업 폴더에 파일이 없으면(예: 다른 곳에서 커밋하지 않은 삭제) HEAD에서 읽는다."""
    return subprocess.check_output(["git", "show", "HEAD:%s" % path], cwd=ROOT,
                                   stderr=subprocess.DEVNULL)


def available(path):
    if os.path.isfile(os.path.join(ROOT, path)):
        return True
    try:
        blob(path)
        return True
    except subprocess.CalledProcessError:
        return False


# ---------- 항목 수집 ----------

def h1_title(path, fallback):
    m = H1.search(FRONT.sub("", read(path)))
    return m.group(1).strip() if m else fallback


def collect():
    items = []
    idx = json.load(open(os.path.join(ROOT, "reports", "index.json"), encoding="utf-8"))
    for r in idx["reports"]:
        if not available(r["path"]):
            continue
        items.append({
            "title": r["title"], "path": r["path"], "bucket": r["bucket"], "group": r["group"],
            "series": r.get("series", ""), "type": r.get("type", T_RESEARCH), "date": r.get("date", ""),
        })
    # 폴더 README: index.json에는 없으므로 여기서 안내 글로 싣는다
    seen = {i["path"] for i in items}
    dir_meta = {}
    for i in items:
        dir_meta.setdefault(os.path.dirname(i["path"]), (i["bucket"], i["group"]))
    for p in tracked("reports/"):
        if not p.endswith("README.md") or p in seen or "/_index/" in p:
            continue
        d = os.path.dirname(p)
        bucket, group = dir_meta.get(d, (None, None))
        while bucket is None and d.count("/") > 0:
            d = os.path.dirname(d)
            bucket, group = dir_meta.get(d, (None, None))
        if bucket is None:
            parts = p.split("/")
            bucket, group = (B_THEME, parts[1] if len(parts) > 2 else "연구 개요")
        items.append({"title": h1_title(p, "%s 안내" % group), "path": p,
                      "bucket": bucket, "group": group, "series": "", "type": T_GUIDE,
                      "date": git_date(p)})
    for p in tracked("docs/"):
        if not p.endswith(".md") or os.path.basename(p) in ("ROADMAP.md", "README.md"):
            continue
        items.append({"title": h1_title(p, os.path.basename(p)[:-3]), "path": p,
                      "bucket": B_THEME, "group": "에세이·종합", "series": "", "type": T_RESEARCH,
                      "date": git_date(p)})
    for it in items:
        it["id"] = page_id(it["path"])
        it["url"] = "r/%s.html" % it["id"]
    items.sort(key=lambda x: (x["date"] or "0000"), reverse=True)
    return items


# ---------- 내용 선별: 완성본만 싣고 중간 산출물은 싣지 않는다 ----------
# 중간 산출물(감사, 검증, 증빙, 초안, 데이터 수집, 검색 로그, 자동 스캔, 스크리닝풀의 관점별 원고 등)은 GitHub에만 두고
# 읽기 사이트에는 완성 보고서만 싣는다. 제외한 페이지를 본문이 가리키면 링크는 GitHub 원문으로 간다.
MID_DIR = re.compile(r"/(evidence|증빙|research|data|sources|audit[^/]*|감사[^/]*|[^/]*리뷰기록[^/]*|[^/]*검증[^/]*|[^/]*증빙)/", re.I)
# 분명한 중간 산출물 표시만 본다. "검증", "증빙", "감사" 같은 낱말 하나만으로는 완성 연구의 제목일 수 있어 제외하지 않는다
MID_NAME = re.compile(
    r"초안|검증\s?보고|검증\s?기록|검증\s?설명|검증\s?범위|감사\s?설명|감사\s?기록|감사\s?범위|재검토\s?기록|리뷰\s?기록|"
    r"출처\s?목록|^출처와|data[_-]?collection|데이터\s?수집|search[-_]?log|^sources$|"
    r"작업\s?원고|작업\s?자료|draft|todo|재검토\s?대기|표본\s?점검|부록|^재무표$|^계산|financial[-_]rigor|"
    r"readme__|__readme|독자\s?리뷰|audit[-_]notes|증빙$", re.I)
POOL_PERSPECTIVE = re.compile(r"/0[1-4]-[^/]*(관점|시각)\.md$")
BOTTLENECK_RUN = re.compile(r"^reports/bottleneck-map/(20\d\d-\d\d-\d\d|daily)/")

WHY_AUTO = "자동 스캔·일일 보고"
WHY_DIR = "증빙/감사/조사 폴더"
WHY_DRAFT = "감사·검증 초안"
WHY_POOL = "스크리닝풀 관점별 원고"
WHY_INDEX = "색인 페이지"
WHY_SHORT = "너무 짧음"
WHY_DUP = "중복 또는 구버전"


def exclude_reason(it):
    path, name, title = it["path"], os.path.basename(it["path"]), it["title"]
    if BOTTLENECK_RUN.match(path):
        return WHY_AUTO
    if MID_DIR.search("/" + path):
        return WHY_DIR
    if MID_NAME.search(name[:-3]) or MID_NAME.search(title.strip()):
        return WHY_DRAFT
    if it["type"] == T_DRAFT and "시리즈안내" not in re.sub(r"\s+", "", title):
        return WHY_DRAFT
    if it["bucket"] == B_SCREEN and POOL_PERSPECTIVE.search(path):
        return WHY_POOL
    if path in ("reports/README.md",) or path.startswith("reports/_index/"):
        return WHY_INDEX
    if it["bucket"] == B_SCREEN and name == "README.md" and path.count("/") > 2:
        return WHY_POOL
    if it["type"] == T_GUIDE and it.get("_size", 9999) < 600:
        return WHY_SHORT
    if it.get("_size", 9999) < 800:
        return WHY_SHORT
    return ""


def attach_workpapers(kept, hidden):
    """완성본에 GitHub의 초안을 붙인다. 프로젝트 폴더(reports/기업/프로젝트/)는 같은 폴더와 하위 폴더의 초안을 모두 붙이고,
    기업 폴더 바로 아래의 보고서는 파일명이나 하위 폴더명의 날짜가 같은 초안만 붙인다."""
    for it in kept:
        d = os.path.dirname(it["path"])
        project = it["path"].count("/") >= 3
        dm = DATE8.search(os.path.basename(it["path"]))
        day = "".join(dm.groups()) if dm else (it["date"] or "").replace("-", "")
        rows = []
        for h in hidden:
            hp = h["path"]
            if project:
                if hp.startswith(d + "/"):
                    rows.append(h)
            elif day and len(day) == 8 and hp.startswith(d + "/") and day in hp[len(d):]:
                rows.append(h)
        it["_work"] = sorted(rows, key=lambda r: r["path"])[:20]


def curate(items):
    kept, dropped, hidden = [], defaultdict(int), []
    for it in items:
        it["_size"] = len(read(it["path"]).encode("utf-8"))
        why = exclude_reason(it)
        if why:
            dropped[why] += 1
            if why not in (WHY_AUTO, WHY_INDEX, WHY_SHORT):
                it["_why"] = why
                hidden.append(it)
        else:
            kept.append(it)
    # 중복 제거: 내용이 완전히 같으면 하나만 남긴다. 같은 폴더·같은 제목의 여러 판은 가장 최근이고 가장 긴 것만 남긴다
    seen_hash, best = {}, {}
    for it in sorted(kept, key=lambda x: (x["date"] or "", x["_size"]), reverse=True):
        h = hashlib.sha1(read(it["path"]).encode("utf-8")).hexdigest()
        key = (os.path.dirname(it["path"]), re.sub(r"\s+", "", it["title"]))
        if h in seen_hash or key in best:
            dropped[WHY_DUP] += 1
            continue
        seen_hash[h] = 1
        best[key] = it
    kept = [it for it in kept if best.get((os.path.dirname(it["path"]), re.sub(r"\s+", "", it["title"]))) is it]
    for it in kept:
        if it["type"] == T_DRAFT:
            it["type"] = T_GUIDE
    attach_workpapers(kept, hidden)
    print("수록 %d건, 제외 %d건: %s" % (len(kept), sum(dropped.values()),
          ", ".join("%s %d" % kv for kv in sorted(dropped.items(), key=lambda x: -x[1]))))
    return kept


def git_date(path):
    try:
        out = sh(["git", "log", "-1", "--format=%cs", "--", path]).strip()
        return out
    except subprocess.CalledProcessError:
        return ""


# ---------- HTML 틀 ----------

CSS = """
:root{--bg:#fbfbf9;--card:#fff;--fg:#1f2328;--muted:#656d76;--line:#e3e4e2;--accent:#0b5cad;--accent-bg:#eaf2fb;
--th:#f3f4f2;--code:#f3f4f2;--shadow:0 1px 2px rgba(0,0,0,.05);--radius:10px;--w:46rem;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme]){--bg:#15171a;--card:#1c1f23;--fg:#e6e6e3;--muted:#9aa1a9;
--line:#2d3136;--accent:#6cb0ff;--accent-bg:#1d2a3a;--th:#23272c;--code:#23272c;--shadow:none;color-scheme:dark}}
:root[data-theme=dark]{--bg:#15171a;--card:#1c1f23;--fg:#e6e6e3;--muted:#9aa1a9;--line:#2d3136;--accent:#6cb0ff;
--accent-bg:#1d2a3a;--th:#23272c;--code:#23272c;--shadow:none;color-scheme:dark}
html{font-size:17px;-webkit-text-size-adjust:100%}
html[data-size=s1]{font-size:15px}html[data-size=s3]{font-size:19px}html[data-size=s4]{font-size:22px}
*{box-sizing:border-box}
body{margin:0;color:var(--fg);background:var(--bg);line-height:1.8;
font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR","Noto Sans CJK KR","Malgun Gothic",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);
-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{max-width:72rem;margin:0 auto;padding:0 1rem;display:flex;align-items:center;gap:1rem;height:3.2rem}
.brand{font-weight:700;color:var(--fg);white-space:nowrap}
nav.main{display:flex;gap:.2rem;overflow-x:auto;scrollbar-width:none;flex:1;min-width:0}nav.main::-webkit-scrollbar{display:none}
nav.main a{color:var(--fg);padding:.3rem .65rem;border-radius:6px;white-space:nowrap;font-size:.93rem}
nav.main a:hover,nav.main a.on{background:var(--accent-bg);color:var(--accent);text-decoration:none}
.tools{display:flex;gap:.3rem;white-space:nowrap;flex-shrink:0}
.tools button{font:inherit;font-size:.82rem;color:var(--fg);background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:.15rem .5rem;cursor:pointer}
.tools select{font:inherit;font-size:.82rem;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.1rem .3rem}
main{max-width:var(--w);margin:0 auto;padding:0 1rem 3rem;overflow-wrap:anywhere}
main.wide{max-width:72rem}
.crumb{font-size:.82rem;color:var(--muted);margin:1.2rem 0 0}.crumb a{color:var(--muted)}
h1{font-size:1.75rem;line-height:1.35;margin:.8rem 0 .5rem;letter-spacing:.01em}
h2{font-size:1.3rem;line-height:1.45;margin:2.2rem 0 .8rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
h3{font-size:1.08rem;margin:1.6rem 0 .5rem}
.meta{color:var(--muted);font-size:.84rem;margin:.15rem 0 1rem}
ul.list{list-style:none;padding:0;margin:0;background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
ul.list li{padding:.75rem 1rem;border-bottom:1px solid var(--line)}ul.list li:last-child{border-bottom:0}
ul.list li:hover{background:var(--accent-bg)}
ul.list li>a{display:block;color:var(--fg);font-weight:500}ul.list li>a:hover{color:var(--accent);text-decoration:none}
ul.list .meta{margin:.15rem 0 0}
.grid{display:flex;flex-wrap:wrap;gap:.5rem;margin:.6rem 0}
.grid a.btn{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:.35rem .9rem;
color:var(--fg);font-size:.92rem;box-shadow:var(--shadow)}
.grid a.btn:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.grid.big a.btn{border-radius:var(--radius);padding:.7rem 1.1rem;font-weight:600}
.idx{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:0}
.idx li{border-bottom:1px solid var(--line)!important}
article{font-size:1.02rem}
article p{margin:.9rem 0}
article a{text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1px}
.table-wrap{overflow-x:auto;margin:1.2rem 0;border:1px solid var(--line);border-radius:var(--radius);background:var(--card)}
table{border-collapse:collapse;font-size:.86rem;line-height:1.5;min-width:100%}
th,td{border-bottom:1px solid var(--line);padding:.45rem .7rem;vertical-align:top;text-align:left}
th{background:var(--th);font-weight:600;white-space:nowrap}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--th) 45%,transparent)}
blockquote{border-left:3px solid var(--accent);margin:1.2rem 0;padding:.2rem 1rem;color:var(--muted);background:var(--card)}
pre{overflow-x:auto;background:var(--code);border-radius:8px;padding:.8rem;font-size:.82rem;line-height:1.5}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;background:var(--code);padding:.1em .3em;border-radius:4px}
pre code{background:none;padding:0}
img{max-width:100%;height:auto;border-radius:6px}
hr{border:0;border-top:1px solid var(--line);margin:2rem 0}
details.toc{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:.2rem 1rem;margin:1rem 0}
summary{cursor:pointer;padding:.5rem 0;font-weight:600}
.toc ul{padding-left:1.1rem;margin:.2rem 0 .6rem;font-size:.9rem;line-height:1.7}
.toc a{color:var(--fg)}
.layout{display:block}
aside.side{display:none}
@media (min-width:1180px){main.doc{max-width:72rem}.layout{display:grid;grid-template-columns:minmax(0,46rem) 15rem;gap:3rem;justify-content:center}
aside.side{display:block}aside.side .toc{position:sticky;top:4.5rem;max-height:calc(100vh - 6rem);overflow:auto;font-size:.85rem;
border-left:1px solid var(--line);padding-left:1rem}aside.side .toc ul{padding-left:.8rem}
details.toc{display:none}}
.resume{position:fixed;left:50%;bottom:1.2rem;transform:translateX(-50%);z-index:12;background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:999px;padding:.45rem .6rem .45rem 1rem;box-shadow:0 4px 16px rgba(0,0,0,.12);font-size:.9rem;white-space:nowrap}
.resume button{font:inherit;margin-left:.6rem;border:0;border-radius:999px;background:var(--accent);color:#fff;padding:.2rem .8rem;cursor:pointer}
.resume .x{margin-left:.5rem;color:var(--muted);cursor:pointer;padding:0 .3rem}
ul.list li.done>a{color:var(--muted);font-weight:400}.rd{color:var(--accent)}
ul.work li>a{font-weight:400;font-size:.95rem}
.fixline{margin:2.4rem 0 .6rem;padding-top:.8rem;border-top:1px solid var(--line);color:var(--muted);font-size:.85rem}
.intro{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:1rem 1.2rem;margin:1rem 0 1.4rem}
.intro p{margin:.3rem 0}
.layers{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.8rem;margin:1rem 0}
.layers div{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:.9rem 1rem}
.layers b{display:block;margin-bottom:.2rem}.layers span{color:var(--muted);font-size:.88rem}
.progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:11}
footer{max-width:72rem;margin:3rem auto 0;padding:1.2rem 1rem 2rem;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
footer a{color:var(--muted);text-decoration:underline}
input.q{font:inherit;font-size:1.05rem;width:100%;padding:.7rem 1rem;border:1px solid var(--line);border-radius:var(--radius);
background:var(--card);color:var(--fg);outline:none}input.q:focus{border-color:var(--accent)}
@media (max-width:640px){html{font-size:16px}h1{font-size:1.45rem}.bar{gap:.5rem;padding:0 .6rem}.brand{display:none}
.tools .lbl{display:none}ul.list li{padding:.7rem .8rem}}
"""

PREF_JS = """
(function(){var h=document.documentElement,g=function(k){try{return localStorage.getItem(k)}catch(e){return null}};
var t=g('aib-theme'),s=g('aib-size');
if(t&&t!=='auto')h.setAttribute('data-theme',t);if(s)h.setAttribute('data-size',s);
var sz=['s1','','s3','s4'];
window.aibSize=function(d){var c=h.getAttribute('data-size')||'',i=sz.indexOf(c);i=Math.max(0,Math.min(3,i+d));
if(sz[i])h.setAttribute('data-size',sz[i]);else h.removeAttribute('data-size');try{localStorage.setItem('aib-size',sz[i])}catch(e){}};
window.aibTheme=function(v){if(v==='auto')h.removeAttribute('data-theme');else h.setAttribute('data-theme',v);
try{localStorage.setItem('aib-theme',v)}catch(e){}};
document.addEventListener('DOMContentLoaded',function(){var sel=document.getElementById('theme');
if(sel)sel.value=h.getAttribute('data-theme')||'auto';var bar=document.querySelector('.progress');
if(bar){var f=function(){var d=document.documentElement,m=d.scrollHeight-d.clientHeight;bar.style.width=(m>0?d.scrollTop/m*100:0)+'%'};
addEventListener('scroll',f,{passive:true});f()}});})();
"""

def about_page(n_reports, n_companies, updated):
    return """
<h1>AI Berkshire 소개</h1>
<div class="meta">AI로 가치투자 연구를 하는 오픈소스 프로젝트 · 완성 보고서 %(n)d건 · 기업 %(c)d곳 · %(u)s 기준</div>

<h2>무엇인가</h2>
<p>AI Berkshire는 오픈소스 투자 연구 방법론이다. 가치투자의 분석 틀을 Claude Code와 Codex가 불러 쓸 수 있는 연구 스킬(Skill)로 적어 두어,
한 사람과 AI 에이전트가 투자 연구팀 하나의 작업량을 해낼 수 있게 한다. 1차 자료인 실적 공시를 읽고, 숫자를 교차 검증하고,
여러 관점에서 반론을 맞세운 뒤, 결론이 분명한 보고서로 정리한다.</p>
<p>이 사이트는 프로젝트의 읽기 입구다. 완성된 연구를 모두 싣고 기업·테마·날짜·유형별로 정리했으며 PC·휴대폰·전자책 리더에서 읽을 수 있다.</p>

<h2>두 곳, 두 가지 정밀도</h2>
<div class="layers">
<div><b>이 사이트</b><span>완성 보고서 전체. 평소에 읽고, 기업별로 과거 판단을 넘겨 보고, 찾아보는 곳이다.</span></div>
<div><b><a href="%(repo)s">GitHub 저장소</a></b><span>초안 전체. 연구 스킬, 감사·검증 기록, 증빙, 중간 원고가 모두 있다. 각 보고서 페이지 아래에 해당 초안 목록이 있다.</span></div>
</div>

<h2>연구 방법의 원칙</h2>
<ul>
<li><b>1차 자료만 쓴다</b>: 거래소 공시, 사업보고서, 실적 발표의 실제 발언. 과거 보고서는 단서일 뿐 증거가 아니다.</li>
<li><b>사실과 판단을 나눠 쓴다</b>: 추정과 판단은 모두 표시하고, 숫자에는 출처와 기준을 적는다.</li>
<li><b>결론을 반드시 낸다</b>: "한편으로는, 다른 한편으로는" 식으로 얼버무리지 않고, 검증할 수 있는 판단과 검증 시점을 적는다.</li>
<li><b>추적할 수 있다</b>: 같은 기업의 보고서를 시간순으로 모아, 판단이 어떻게 왜 바뀌었는지 대조할 수 있다.</li>
</ul>

<h2>사이트 사용법</h2>
<ul>
<li><a href="companies/index.html">기업별</a>: 기업마다 한 페이지. 심층시리즈, 실적, 밸류에이션 등 유형별로 나뉜다.</li>
<li><a href="topics/index.html">테마</a>: 산업 연구, 비교, 스크리닝 풀.</li>
<li><a href="dates/index.html">날짜별</a>과 <a href="types/index.html">유형별</a>: 최근에 무엇을 썼는지 본다.</li>
<li><a href="search.html">검색</a>: 기업명이나 키워드를 넣는다. 예: "엔비디아 실적".</li>
<li>오른쪽 위에서 글자 크기와 밝기를 바꿀 수 있다. 읽은 글에는 진행률이 표시되고 다음에 열면 이어 읽을 수 있다(본인 브라우저에만 저장된다).</li>
<li>데이터 오류를 찾았다면: 보고서 끝의 "오류 제보"를 누르면 GitHub 오류 제보 양식이 보고서 이름이 채워진 채 열린다. 올바른 값과 출처 링크를 함께 적는다.</li>
<li>RSS로 업데이트를 구독할 수 있다: <a href="feed.xml">feed.xml</a>.</li>
</ul>

<h2>직접 돌려 보기</h2>
<p>연구 스킬, 사용 설명, 보고서 원문은 모두 <a href="%(repo)s">GitHub</a>에 있다. 저장소 첫 화면의 안내대로 설치하면 Claude Code나 Codex에서 불러 쓸 수 있다.
issue와 개선 제안을 환영한다.</p>

<h2>면책</h2>
<p class="meta">이 사이트의 내용은 개인 연구 기록이며 투자 권유가 아니다. 보고서의 판단은 틀릴 수 있고, 데이터는 회사 공시 원문이 기준이다. 투자에는 위험이 따르며 결정은 스스로 판단한다.</p>
""" % {"n": n_reports, "c": n_companies, "u": updated, "repo": REPO_URL}


READ_JS = r"""
(function(){var K='aib-read',get=function(){try{return JSON.parse(localStorage.getItem(K)||'{}')}catch(e){return{}}},
put=function(d){try{localStorage.setItem(K,JSON.stringify(d))}catch(e){}};
document.addEventListener('DOMContentLoaded',function(){var b=document.body,root=b.getAttribute('data-root')||'',page=b.getAttribute('data-page');
var d=get();
if(page){var rec=d[page]||{p:0},el=document.documentElement;
 if(rec.p>0.05&&rec.p<0.95){var n=document.createElement('div');n.className='resume';
  n.innerHTML='지난번 '+Math.round(rec.p*100)+'%까지 읽음 <button>이어 읽기</button><span class="x">×</span>';
  n.querySelector('button').onclick=function(){scrollTo(0,rec.p*(el.scrollHeight-el.clientHeight));n.remove()};
  n.querySelector('.x').onclick=function(){n.remove()};document.body.appendChild(n);setTimeout(function(){n.remove()},15000)}
 var t=null;addEventListener('scroll',function(){clearTimeout(t);t=setTimeout(function(){var m=el.scrollHeight-el.clientHeight;
  var p=m>0?el.scrollTop/m:1,cur=get();var r=cur[page]||{};r.p=p;r.t=Date.now();r.title=b.getAttribute('data-title');
  if(p>0.9)r.done=1;cur[page]=r;put(cur)},400)},{passive:true});
 var r0=d[page]||{};r0.t=Date.now();r0.title=b.getAttribute('data-title');if(r0.p==null)r0.p=0;d[page]=r0;put(d)}
var links=document.querySelectorAll('ul.list li>a');for(var i=0;i<links.length;i++){var h=links[i].getAttribute('href')||'';
 var key=h.replace(/^(\.\.\/)+/,'');var r=d[key];if(r){var m=links[i].parentNode.querySelector('.meta');
 if(m){m.insertAdjacentHTML('beforeend',' · <span class="rd">'+(r.done?'읽음':Math.round((r.p||0)*100)+'% 읽음')+'</span>')}
 if(r.done)links[i].parentNode.classList.add('done')}}
var box=document.getElementById('recent-read');if(box){var arr=Object.keys(d).map(function(k){return{k:k,r:d[k]}})
 .filter(function(x){return x.r.title}).sort(function(a,b){return b.r.t-a.r.t}).slice(0,6);
 if(arr.length){box.innerHTML='<h2>최근 읽은 글</h2><ul class="list">'+arr.map(function(x){var e=document.createElement('a');e.textContent=x.r.title;
  return '<li><a href="'+root+x.k+'">'+e.innerHTML+'</a><div class="meta">'+(x.r.done?'다 읽음':Math.round((x.r.p||0)*100)+'% 읽음')+'</div></li>'}).join('')+'</ul>'}}
});})();
"""

NAV = [("index.html", "홈"), ("companies/index.html", "기업"), ("topics/index.html", "테마"),
       ("dates/index.html", "날짜"), ("types/index.html", "유형"),
       ("search.html", "검색"), ("about.html", "소개")]


def analytics_tag():
    """통계 스크립트. 아무 페이지 주소에 #notrack 을 붙여 열면 그 기기에서는 통계 스크립트를 싣지 않고, #track 으로 되돌린다."""
    if not (GOATCOUNTER or BAIDU_TONGJI):
        return ""
    loads = []
    if BAIDU_TONGJI:
        loads.append("window._hmt=window._hmt||[];var b=document.createElement('script');"
                     "b.async=true;b.src='https://hm.baidu.com/hm.js?%s';document.head.appendChild(b);" % BAIDU_TONGJI)
    if GOATCOUNTER:
        loads.append("var g=document.createElement('script');g.async=true;g.src='//gc.zgo.at/count.js';"
                     "g.setAttribute('data-goatcounter','https://%s.goatcounter.com/count');document.head.appendChild(g);" % GOATCOUNTER)
    return ("<script>(function(){var skip=false;try{if(location.hash==='#notrack'){localStorage.setItem('skipgc','1');"
            "alert('이 기기의 방문은 앞으로 통계에 집계되지 않습니다')}if(location.hash==='#track'){localStorage.removeItem('skipgc')}"
            "skip=!!localStorage.getItem('skipgc')}catch(e){}if(skip)return;%s})();</script>" % "".join(loads))


def shell(title, body, depth, crumb="", section="", main_class="", progress=False, page=""):
    rel = "../" * depth
    links = "".join('<a href="%s%s"%s>%s</a>' % (rel, u, ' class="on"' if t == section else "", t) for u, t in NAV)
    head = (
        '<header class="top"><div class="bar"><a class="brand" href="{r}index.html">AI Berkshire</a>'
        '<nav class="main">{links}</nav><div class="tools">'
        '<button onclick="aibSize(-1)" title="글자 작게">A−</button><button onclick="aibSize(1)" title="글자 크게">A+</button>'
        '<select id="theme" onchange="aibTheme(this.value)" title="화면 모드"><option value="auto">자동</option>'
        '<option value="light">밝게</option><option value="dark">어둡게</option></select>'
        '</div></div></header>'
    ).format(r=rel, links=links)
    crumb_html = '<div class="crumb">%s</div>' % crumb if crumb else ""
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#fbfbf9">'
        '<title>%s · %s</title><link rel="stylesheet" href="%sstyle.css">'
        '<link rel="alternate" type="application/rss+xml" title="%s" href="%sfeed.xml">'
        '<script>%s</script>' + analytics_tag() + '</head><body data-root="%s" data-page="%s" data-title="%s">%s%s<main class="%s">%s%s</main>'
        '<footer>%s | <a href="%sabout.html">사이트 소개</a> | <a href="%s">GitHub 저장소</a> | <a href="%sfeed.xml">RSS 구독</a> | 생성 시각 %s</footer></body></html>'
    ) % (html.escape(title), SITE_NAME, rel, SITE_NAME, rel, PREF_JS + READ_JS, rel, page, html.escape(title, quote=True),
         '<div class="progress"></div>' if progress else "", head, main_class, crumb_html, body,
         SITE_NAME, rel, REPO_URL, rel, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


def li(it, depth, show_group=True):
    rel = "../" * depth
    bits = [it["date"] or "날짜 미상"]
    if show_group and it["group"]:
        bits.append(it["group"])
    if it["type"]:
        bits.append(it["type"])
    return '<li><a href="%s%s">%s</a><div class="meta">%s</div></li>' % (
        rel, it["url"], html.escape(it["title"]), " · ".join(html.escape(b) for b in bits))


def ul(items, depth, show_group=True, limit=None):
    rows = items if limit is None else items[:limit]
    return '<ul class="list">%s</ul>' % "".join(li(i, depth, show_group) for i in rows)





# ---------- Markdown → HTML ----------

LINK_ATTR = re.compile(r'(href|src)="([^"]+)"')


def convert(it, by_path, out_dir):
    text = FRONT.sub("", read(it["path"]))
    m1 = H1.search(text)
    if m1 and (m1.start() < 1500 or m1.group(1).strip() == it["title"]):
        text = text[:m1.start()] + text[m1.end():]
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    body = md.convert(text)
    base = os.path.dirname(it["path"])
    missing = []

    def fix(m):
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", url):
            return m.group(0)
        clean = url.split("#")[0].split("?")[0]
        target = os.path.normpath(os.path.join(base, clean)).replace("\\", "/")
        if target in by_path:
            return '%s="../%s"' % (attr, by_path[target]["url"])
        ext = os.path.splitext(target)[1].lower()
        src = os.path.join(ROOT, target)
        if ext in ASSET_EXT and available(target):
            dst = os.path.join(out_dir, "files", target)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    with open(dst, "wb") as fh:
                        fh.write(blob(target))
            return '%s="../files/%s"' % (attr, quote(target))
        if available(target):
            return '%s="%s/blob/main/%s"' % (attr, REPO_URL, quote(target))
        missing.append(url)
        return m.group(0)

    body = LINK_ATTR.sub(fix, body)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    toc = md.toc if md.toc and md.toc.count("<li>") >= 3 else ""
    return body, toc


# ---------- 페이지 생성 ----------

def write(out_dir, rel_path, content):
    p = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


# 테마 폴더 안의 개별 기업 보고서를 기업 페이지에 함께 걸 때 쓰는 이름 대응(제목 머리의 이름 -> 기업 페이지 이름)
COMPANY_ALIAS = {"구글": "Google", "Alphabet": "Google", "알파벳": "Google", "테슬라": "Tesla",
                 "Amazon": "아마존", "아마존": "아마존", "마이크로소프트": "마이크로소프트", "애플": "애플"}
HOME = "홈"


def build(out_dir):
    items = curate(collect())
    by_path = {i["path"]: i for i in items}
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    write(out_dir, "style.css", CSS)
    write(out_dir, ".nojekyll", "")

    companies = defaultdict(list)
    topics = defaultdict(list)
    screens = defaultdict(list)
    months = defaultdict(list)
    types = defaultdict(list)
    for it in items:
        if it["bucket"] == B_COMPANY:
            companies[it["group"]].append(it)
        elif it["bucket"] == B_SCREEN:
            screens[it["group"]].append(it)
        else:
            topics[it["group"]].append(it)
        if it["date"]:
            months[it["date"][:7]].append(it)
        types[it["type"]].append(it)

    # 테마 폴더에 있는 개별 기업 보고서(예: 빅테크 7개사를 한 곳씩 다룬 보고서)는 해당 기업 페이지에도 건다
    alias = COMPANY_ALIAS
    names = sorted(set(companies) | set(alias), key=len, reverse=True)
    for it in items:
        if it["bucket"] not in (B_THEME,):
            continue
        t = it["title"].strip()
        hit = None
        for n in names:
            if re.match(re.escape(n) + r"(\(|:|\s)", t):
                hit = alias.get(n, n)
                break
        if not hit:
            m = re.match(r"^([^(:\s]{1,12})\s?\(([A-Z0-9]{1,6}(\.[A-Z]{1,2})?)\)", t)
            if m:
                hit = alias.get(m.group(1), m.group(1))
        if hit and it not in companies[hit]:
            companies[hit].append(it)
            it["_also"] = hit
    for c in companies:
        companies[c].sort(key=lambda x: x["date"] or "", reverse=True)

    # 테마 표시 이름: 폴더 README의 제목을 먼저 쓴다
    tname = {}
    for it in items:
        if os.path.basename(it["path"]) != "README.md":
            continue
        d = os.path.basename(os.path.dirname(it["path"]))
        if d in topics and d not in tname:
            tname[d] = it["title"]
            if it["group"] != d and it in topics.get(it["group"], []):
                topics[it["group"]].remove(it)
                topics[d].append(it)
                it["group"] = d
    disp = lambda g: tname.get(g, g)

    comp_url = {c: "companies/%s/index.html" % slug(c) for c in companies}
    topic_url = {t: "topics/%s/index.html" % slug(t) for t in topics}
    screen_url = {s: "screens/%s/index.html" % slug(s) for s in screens}

    def group_link(it, depth):
        rel = "../" * depth
        if it["bucket"] == B_COMPANY and it["group"] in comp_url:
            return '<a href="%s%s">%s</a>' % (rel, comp_url[it["group"]], html.escape(it["group"]))
        if it["bucket"] == B_SCREEN and it["group"] in screen_url:
            return '<a href="%s%s">%s</a>' % (rel, screen_url[it["group"]], html.escape(it["group"]))
        g = it["group"]
        if g in topic_url:
            return '<a href="%s%s">%s</a>' % (rel, topic_url[g], html.escape(disp(g)))
        return html.escape(disp(g))

    # 보고서 페이지
    for it in items:
        body, toc = convert(it, by_path, out_dir)
        same = [x for x in (companies.get(it["group"]) or topics.get(it["group"]) or screens.get(it["group"]) or [])
                if x["id"] != it["id"]][:12]
        meta = " · ".join(x for x in [it["date"], it["type"]] if x)
        head = "<h1>%s</h1><div class=\"meta\">%s | %s | <a href=\"%s/blob/main/%s\">GitHub 원문</a></div>" % (
            html.escape(it["title"]), group_link(it, 1), html.escape(meta), REPO_URL, quote(it["path"]))
        if toc:
            head += '<details class="toc"><summary>목차</summary>%s</details>' % toc
        tail = ""
        issue = "%s/issues/new?%s" % (REPO_URL, "&".join("%s=%s" % (k, quote(v, safe="")) for k, v in [
            ("template", "data_error.yml"), ("title", "[Data] " + it["title"][:60]),
            ("ticker", it["group"] if it["bucket"] == B_COMPANY else ""),
            ("source", "%s (읽기 사이트: %s%s)" % (it["path"], SITE_URL, it["url"]))]))
        tail += ('<p class="fixline">데이터 오류를 찾았다면 <a href="%s" rel="nofollow">오류 제보</a>'
                 '(올바른 값과 출처를 함께 적는다)</p>') % html.escape(issue)
        if it.get("_work"):
            tail += ('<h2>초안과 검증 기록 (GitHub)</h2><div class="meta">이 파일들은 읽기 사이트에 싣지 않는다. 누르면 GitHub 원문이 열린다.</div>'
                     '<ul class="list work">%s</ul>') % "".join(
                '<li><a href="%s/blob/main/%s">%s</a><div class="meta">%s · %s</div></li>' % (
                    REPO_URL, quote(w["path"]), html.escape(w["title"]), html.escape(w["_why"]),
                    html.escape(w["path"][len(os.path.dirname(it["path"])) + 1:] if w["path"].startswith(os.path.dirname(it["path"]) + "/") else w["path"]))
                for w in it["_work"])
        if same:
            tail += "<h2>같은 묶음의 다른 보고서</h2>" + ul(same, 1, show_group=False)
        crumb = '<a href="../index.html">%s</a> › %s' % (HOME, group_link(it, 1))
        side = '<aside class="side"><div class="toc"><div class="meta">이 글의 목차</div>%s</div></aside>' % toc if toc else "<aside class=\"side\"></aside>"
        page = '<div class="layout"><div>%s<article>%s</article>%s</div>%s</div>' % (head, body, tail, side)
        write(out_dir, it["url"], shell(it["title"], page, 1, crumb, main_class="doc", progress=True, page=it["url"]))

    # 기업 색인과 기업 페이지
    def company_page(name, rows):
        groups = defaultdict(list)
        for r in rows:
            groups[r["type"]].append(r)
        order = [T_GUIDE] + TYPE_ORDER
        parts = ["<h1>%s</h1><div class=\"meta\">모두 %d건, 최근 업데이트 %s</div>" % (
            html.escape(name), len(rows), rows[0]["date"] if rows and rows[0]["date"] else "—")]
        for k in order + [k for k in groups if k not in order]:
            if k in groups:
                parts.append("<h2>%s (%d)</h2>%s" % (html.escape(k), len(groups[k]), ul(groups[k], 2, show_group=False)))
        return "".join(parts)

    for c, rows in companies.items():
        write(out_dir, comp_url[c], shell(c, company_page(c, rows), 2,
                                          '<a href="../../index.html">%s</a> › <a href="../index.html">기업</a>' % HOME))
    letters = defaultdict(list)
    for c in companies:
        letters[initial(c)].append(c)
    top = sorted(companies, key=lambda c: -len(companies[c]))[:24]
    body = "<h1>기업별</h1><div class=\"meta\">기업 %d곳, 보고서 %d건</div><h2>보고서가 많은 기업</h2><div class=\"grid\">%s</div>" % (
        len(companies), sum(len(v) for v in companies.values()),
        "".join('<a class="btn" href="../%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top))
    body += "<h2>전체 기업 (알파벳·가나다순)</h2>"
    for L in sorted(letters):
        names = sorted(letters[L], key=lambda c: (c.casefold(), c))
        body += "<h3>%s</h3><ul class=\"list idx\">%s</ul>" % (L, "".join(
            '<li><a href="../%s">%s</a><div class="meta">%d건 · 최근 %s</div></li>' % (
                comp_url[c], html.escape(c), len(companies[c]), companies[c][0]["date"] or "—") for c in names))
    write(out_dir, "companies/index.html", shell("기업별", body, 1, section="기업"))

    # 테마
    def simple_group_page(name, rows, depth, crumb):
        by_series = defaultdict(list)
        for r in rows:
            by_series[r["series"] or ""].append(r)
        parts = ["<h1>%s</h1><div class=\"meta\">모두 %d건</div>" % (html.escape(name), len(rows))]
        if len(by_series) > 1:
            for s in sorted(by_series, key=lambda s: (s == "", s), reverse=True):
                parts.append("<h2>%s (%d)</h2>%s" % (html.escape(s or "주 보고서"), len(by_series[s]), ul(by_series[s], depth, show_group=False)))
        else:
            parts.append(ul(rows, depth, show_group=False))
        return shell(name, "".join(parts), depth, crumb)

    for t, rows in topics.items():
        write(out_dir, topic_url[t], simple_group_page(
            disp(t), rows, 2, '<a href="../../index.html">%s</a> › <a href="../index.html">테마</a>' % HOME))
    for s, rows in screens.items():
        write(out_dir, screen_url[s], simple_group_page(
            s, rows, 2, '<a href="../../index.html">%s</a> › <a href="../../topics/index.html">테마</a>' % HOME))
    tnames = sorted(topics, key=lambda t: topics[t][0]["date"] or "", reverse=True)
    body = "<h1>테마와 비교</h1><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d건 · 최근 %s</div></li>' % (
            topic_url[t], html.escape(disp(t)), len(topics[t]), topics[t][0]["date"] or "—") for t in tnames)
    body += "<h2>스크리닝 풀</h2><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d건 · 최근 %s</div></li>' % (
            screen_url[s], html.escape(s), len(screens[s]), screens[s][0]["date"] or "—")
        for s in sorted(screens, key=lambda s: screens[s][0]["date"] or "", reverse=True))
    write(out_dir, "topics/index.html", shell("테마", body, 1, section="테마"))

    # 날짜
    years = defaultdict(list)
    for m in months:
        years[m[:4]].append(m)
    body = "<h1>날짜별</h1>"
    for y in sorted(years, reverse=True):
        body += "<h2>%s년</h2><div class=\"grid\">%s</div>" % (y, "".join(
            '<a class="btn" href="%s.html">%d월 %d</a>' % (m, int(m[5:]), len(months[m])) for m in sorted(years[y], reverse=True)))
    write(out_dir, "dates/index.html", shell("날짜별", body, 1, section="날짜"))
    for m, rows in months.items():
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s년 %d월</h1><div class=\"meta\">%d건</div>%s" % (m[:4], int(m[5:]), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>스크리닝 풀 일일 보고 (%d)</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "dates/%s.html" % m, shell("%s년 %d월" % (m[:4], int(m[5:])), body, 1,
                                                   '<a href="../index.html">%s</a> › <a href="index.html">날짜</a>' % HOME))

    # 유형
    tlist = [t for t in TYPE_ORDER if t in types] + [t for t in types if t not in TYPE_ORDER]
    body = "<h1>유형별</h1><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s.html">%s %d</a>' % (slug(t), html.escape(t), len(types[t])) for t in tlist)
    write(out_dir, "types/index.html", shell("유형별", body, 1, section="유형"))
    for t in tlist:
        rows = types[t]
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s</h1><div class=\"meta\">%d건</div>%s" % (html.escape(t), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>스크리닝 풀 (%d)</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "types/%s.html" % slug(t), shell(
            t, body, 1, '<a href="../index.html">%s</a> › <a href="index.html">유형</a>' % HOME))

    # 검색
    sdata = [{"t": i["title"], "g": i["group"], "k": i["type"], "d": i["date"], "u": i["url"]} for i in items]
    write(out_dir, "search.json", json.dumps(sdata, ensure_ascii=False, separators=(",", ":")))
    body = ("<h1>검색</h1><p>기업명, 키워드, 날짜(예: 2026-09)를 넣는다. 제목·기업·유형에서 찾는다.</p>"
            '<input class="q" id="q" type="search" placeholder="예: 엔비디아 실적" autofocus>'
            '<div class="meta" id="n"></div><ul class="list" id="out"></ul>'
            "<script>var D=null;function esc(s){return s.replace(/[&<>\"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]})}"
            "function run(){var q=document.getElementById('q').value.trim().toLowerCase();var out=document.getElementById('out'),n=document.getElementById('n');"
            "if(!q){out.innerHTML='';n.textContent='';return}var ws=q.split(/\\s+/);var r=D.filter(function(x){var s=(x.t+' '+x.g+' '+x.k+' '+x.d).toLowerCase();return ws.every(function(w){return s.indexOf(w)>=0})});"
            "n.textContent='모두 '+r.length+'건'+(r.length>200?', 앞의 200건만 표시':'');"
            "if(!r.length){out.innerHTML='<li>해당하는 보고서가 없다. 이 기업의 연구를 보고 싶다면 GitHub에서 <a rel=\"nofollow\" href=\"" + REPO_URL + "/issues/new?template=suggestion.yml&title='+encodeURIComponent('[제안] 연구 요청: '+q)+'\">연구를 제안</a>할 수 있다.</li>';}"
            "else{out.innerHTML=r.slice(0,200).map(function(x){return '<li><a href=\"'+x.u+'\">'+esc(x.t)+'</a><div class=\"meta\">'+esc([x.d,x.g,x.k].filter(Boolean).join(' · '))+'</div></li>'}).join('')}"
            "clearTimeout(window._lt);window._lt=setTimeout(function(){if(q.length>=2&&q!==window._lq&&window._hmt){window._lq=q;"
            "window._hmt.push(['_trackEvent','사이트 검색',r.length?'결과 있음':'결과 없음',q])}},1500)}"
            "fetch('search.json').then(function(r){return r.json()}).then(function(d){D=d;document.getElementById('q').addEventListener('input',run);run()});</script>")
    write(out_dir, "search.html", shell("검색", body, 0, section="검색"))

    # 소개 페이지
    write(out_dir, "about.html", shell("소개", about_page(len(items), len(companies),
                                                        items[0]["date"] if items else "—"), 0, section="소개"))

    # 첫 화면
    pool, seen_titles = [], set()
    for i in items:
        tkey = re.sub(r"\s+", "", i["title"])
        if tkey in seen_titles or i["bucket"] in NOISE_BUCKETS or i["series"] == "evidence" or i["type"] == T_GUIDE:
            continue
        seen_titles.add(tkey)
        pool.append(i)
    bundles = defaultdict(list)
    for i in pool:
        bundles[(i["date"], i["group"], i["bucket"])].append(i)
    recent_rows, used, shown = [], set(), 0
    for i in pool:
        key = (i["date"], i["group"], i["bucket"])
        if key in used:
            continue
        rows = bundles[key]
        if len(rows) >= 3:
            used.add(key)
            url = comp_url.get(i["group"]) if i["bucket"] == B_COMPANY else (
                topic_url.get(i["group"]) or screen_url.get(i["group"]))
            name = i["group"] if i["bucket"] == B_COMPANY else disp(i["group"])
            titles = "; ".join(r["title"].split(":")[0].split("독립")[0].strip() for r in rows[:7])
            recent_rows.append('<li><a href="%s">%s (%d건)</a><div class="meta">%s · %s%s</div></li>' % (
                url or rows[0]["url"], html.escape(name), len(rows), i["date"], html.escape(titles[:90]),
                " 등" if len(rows) > 7 else ""))
        else:
            recent_rows.append(li(i, 0))
        shown += 1
        if shown >= 30:
            break
    body = "<h1>%s</h1><p class=\"meta\">보고서 %d건 · 기업 %d곳 · 최근 업데이트 %s</p>" % (
        SITE_NAME, len(items), len(companies), items[0]["date"] if items else "—")
    body += "<div class=\"grid big\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s</a>' % (u, t) for u, t in [
            ("companies/index.html", "기업별"), ("topics/index.html", "테마와 비교"), ("dates/index.html", "날짜별"),
            ("types/index.html", "유형별"), ("search.html", "검색")])
    body += '<div id="recent-read"></div>'
    body += "<h2>최근 업데이트</h2><ul class=\"list\">%s</ul>" % "".join(recent_rows)
    body += "<h2>보고서가 많은 기업</h2><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top[:16])
    write(out_dir, "index.html", shell(HOME, '<div class="hero">' + body + "</div>", 0, section=HOME))
    write(out_dir, "404.html", shell("없는 페이지", "<h1>없는 페이지</h1><p><a href=\"index.html\">홈으로</a></p>", 0))

    # RSS
    feed_items = [i for i in items if i["bucket"] not in NOISE_BUCKETS][:50]
    base = SITE_URL
    rss = ['<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>%s</title><link>%s</link><description>투자 연구 보고서</description>' % (SITE_NAME, base)]
    for i in feed_items:
        rss.append("<item><title>%s</title><link>%s%s</link><guid>%s%s</guid><pubDate>%s</pubDate><description>%s</description></item>" % (
            html.escape(i["title"]), base, i["url"], base, i["url"],
            datetime.strptime(i["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000") if i["date"] else "",
            html.escape(" · ".join(x for x in [i["group"], i["type"]] if x))))
    rss.append("</channel></rss>")
    write(out_dir, "feed.xml", "".join(rss))

    print("보고서 페이지 %d건, 기업 %d곳, 테마 %d개, 월 %d개 생성 -> %s" % (len(items), len(companies), len(topics) + len(screens), len(months), out_dir))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site"))
    args = ap.parse_args()
    build(args.out)

#!/bin/bash
# 읽기 사이트를 다시 만들어 gh-pages 브랜치에 올린다(https://tkimter.github.io/ai-berkshire/).
# 사용법: bash tools/deploy_site.sh
# 설명: 저장소 토큰에 workflow 권한이 없어 Actions를 쓰지 않고, 로컬에서 빌드한 뒤 gh-pages에 푸시한다.
#       네트워크가 불안정할 때를 대비해 폴더별로 나눠 커밋하고 묶음마다 푸시하며, 실패하면 자동으로 다시 시도한다.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${TMPDIR:-/tmp}/aib-site-$$"
SITE="$TMP/site"; WT="$TMP/ghp"
PY="${PYTHON:-python3}"
mkdir -p "$TMP"
"$PY" "$ROOT/tools/build_site.py" --out "$SITE" || exit 1
cd "$ROOT" && git fetch -q origin gh-pages
git worktree add -q --detach "$WT" origin/gh-pages || exit 1
cd "$WT"
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$SITE/." .
push() { for i in 1 2 3 4 5 6; do git -c http.postBuffer=524288000 -c http.version=HTTP/1.1 push -q origin HEAD:refs/heads/gh-pages 2>/dev/null && return 0; sleep 5; done; echo "푸시 실패: $1"; return 1; }
batch() { git add -A -- "$@" 2>/dev/null; git diff --cached --quiet && return 0; git -c core.quotepath=false commit -q -m "읽기 사이트 업데이트: $*"; push "$*"; }
batch index.html style.css 404.html .nojekyll search.html search.json feed.xml
batch companies topics screens dates types
batch files
for h in 0 1 2 3 4 5 6 7 8 9 a b c d e f; do batch r/$h*; done
git add -A; git diff --cached --quiet || { git -c core.quotepath=false commit -q -m "읽기 사이트 업데이트: 정리"; push 정리; }
cd "$ROOT" && git worktree remove --force "$WT"; rm -rf "$TMP"
gh api -X POST repos/tkimter/ai-berkshire/pages/builds >/dev/null 2>&1
echo "게시 완료: https://tkimter.github.io/ai-berkshire/"

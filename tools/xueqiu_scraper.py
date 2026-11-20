#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
쉐추(雪球, xueqiu.com) 범용 크롤러: 지정한 사용자의 전체 타임라인을 훑어 키워드로 본인 원글만 골라낸다.

특징:
  - Playwright 로그인 상태 재사용: 처음 한 번 headful 로 직접 로그인하면 state 를 로컬에 저장
  - 이중 fetch 경로: 페이지 내 JS fetch 우선, 실패하면 context.request(APIRequestContext)로 대체
  - 이어받기: 10페이지마다 진행 상황 저장. 중단 후 다시 실행하면 직전 위치부터 자동으로 이어감
  - 요청 제한 회피: 2-4초 무작위 지연 + 50페이지마다 30초 휴식 + 5회 연속 타임아웃 시 진행 상황을 저장하고 자동 종료
  - 단순 리포스트 제외: 수집 대상 사용자가 직접 쓴 내용만 수록(text 가 비어 있지 않고 "转发微博"가 아닌 것)

자격 증명은 환경 변수로 전달하며 **코드 저장소에 넣지 않는다**:
  export XQ_PHONE=13xxxxxxxxx
  export XQ_PASSWORD=xxx
설정하지 않아도 된다. 처음 실행하면 headful 브라우저가 떠서 직접 로그인할 수 있다(QR/문자/비밀번호 아무거나).

사용 예시:
  # 돤융핑(段永平)의 핀둬둬 관련 발언
  # (키워드는 쉐추 원문과 대조하므로 중국어 그대로: 拼多多=핀둬둬, 黄峥=황정)
  python3 xueqiu_scraper.py \\
      --user-id 1247347556 \\
      --keywords 拼多多,PDD,Temu,黄峥 \\
      --output /tmp/dyp-pdd.md

  # 다른 사용자 + 다른 키워드(茅台=마오타이)
  python3 xueqiu_scraper.py --user-id 6784593966 --keywords 茅台 --output /tmp/out.md

로그인 상태 캐시는 기본 /tmp/xueqiu_state.json 이며 --state-path 로 바꿀 수 있다.
"""

import argparse
import asyncio
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright


def _safe_stdio():
    """콘솔 인코딩(예: Windows cp949)으로 표현할 수 없는 문자(기호·간체자) 때문에 죽지 않게 한다."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty() or os.environ.get("PYTHONIOENCODING"):
                stream.reconfigure(errors="replace")
            else:
                # 파이프·리다이렉트 출력은 UTF-8 로 고정한다(중국어 종목명·기호가 '?' 로 뭉개지지 않게)
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def is_match(text, keywords):
    t = (text or '').lower()
    return any(k.lower() in t for k in keywords)


def parse_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(ts)


def clean(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', '', s)
    for ent, rep in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' ')]:
        s = s.replace(ent, rep)
    return re.sub(r'&#\d+;', '', s).strip()


async def browser_fetch_json(page, url, timeout_s=15):
    """페이지 JS fetch 우선, 실패하면 context.request 로 대체한다."""
    js = f"""
        async () => {{
            const ctl = new AbortController();
            const to = setTimeout(() => ctl.abort(), {int(timeout_s*1000)});
            try {{
                const r = await fetch({json.dumps(url)}, {{
                    headers: {{'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}},
                    credentials: 'include', signal: ctl.signal
                }});
                const text = await r.text();
                clearTimeout(to);
                try {{ return JSON.parse(text); }}
                catch(e) {{ return {{_raw: text.substring(0, 300)}}; }}
            }} catch(e) {{
                clearTimeout(to);
                return {{_error: e.toString()}};
            }}
        }}
    """
    try:
        result = await asyncio.wait_for(page.evaluate(js), timeout=timeout_s + 5)
        if result and not result.get('_error') and not result.get('_raw'):
            return result
    except Exception:
        pass
    try:
        resp = await page.context.request.get(url, headers={
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://xueqiu.com/',
        }, timeout=timeout_s * 1000)
        if resp.ok:
            return await resp.json()
    except Exception:
        return None
    return None


async def verify_login(page, user_id):
    test = await browser_fetch_json(
        page,
        f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page=2&count=1'
    )
    return bool(test and test.get('statuses') is not None)


async def interactive_login(pw, state_path, user_id):
    phone = os.environ.get('XQ_PHONE', '')
    print("\n[로그인 필요] headful 브라우저를 엽니다. 그 안에서 쉐추(雪球) 로그인을 마치세요")
    if phone:
        print(f"        환경 변수 XQ_PHONE = {phone}   (비밀번호는 XQ_PASSWORD)")
    else:
        print("        XQ_PHONE/XQ_PASSWORD 미설정. 브라우저에서 직접 QR 을 스캔하거나 로그인 정보를 입력하세요")
    browser = await pw.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled'],
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='zh-CN',  # 쉐추 사이트 로케일(바꾸지 않는다)
        viewport={'width': 1280, 'height': 800},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = await context.new_page()
    await page.goto('https://xueqiu.com/', wait_until='domcontentloaded')
    print(">>> 브라우저에서 로그인을 마치세요. 스크립트가 5초마다 확인하며, 성공이 감지되면 자동으로 계속합니다(최대 10분)")
    ok = False
    for i in range(120):
        await asyncio.sleep(5)
        try:
            if await verify_login(page, user_id):
                ok = True
                print(f"  ✓ 로그인 성공({i+1}번째 확인)")
                break
        except Exception as e:
            print(f"  확인 중 예외(무시): {e}")
        if (i + 1) % 6 == 0:
            print(f"  ...로그인 대기 중({(i+1)*5}초 경과)")
    if not ok:
        print("10분 안에 로그인이 감지되지 않아 종료합니다")
        await browser.close()
        return None
    await context.storage_state(path=state_path)
    print(f"로그인 상태 저장 → {state_path}")
    return browser, context, page


async def load_with_state(pw, state_path, user_id):
    if not os.path.exists(state_path):
        return None
    browser = await pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
    )
    context = await browser.new_context(
        storage_state=state_path,
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='zh-CN',  # 쉐추 사이트 로케일(바꾸지 않는다)
        viewport={'width': 1280, 'height': 800},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = await context.new_page()
    loaded = False
    for attempt in range(3):
        try:
            await page.goto('https://xueqiu.com/', wait_until='domcontentloaded', timeout=15000)
            loaded = True
            break
        except Exception as e:
            print(f"  첫 화면 로드 실패({attempt+1}번째): {e}")
            await asyncio.sleep(5)
    if not loaded:
        try:
            await page.goto('about:blank')
        except Exception:
            pass
    await asyncio.sleep(2)
    if await verify_login(page, user_id):
        print("✓ 저장된 로그인 상태를 재사용했습니다")
        return browser, context, page
    print("저장된 state 가 만료됐습니다")
    await browser.close()
    return None


async def fetch_all_timeline(page, user_id, keywords, progress_path, dump_all_path=''):
    collected = {}
    # all_posts: 해당 사용자의 모든 원글을 보관(키워드로 거르지 않음). 오프라인 다주제 분석용
    all_posts = {}
    if dump_all_path and os.path.exists(dump_all_path):
        try:
            for e in json.load(open(dump_all_path)):
                all_posts[e['id']] = e
            print(f"  ↪ 기존 전체 캐시 로드: {len(all_posts)}건")
        except Exception as e:
            print(f"  전체 캐시 읽기 실패: {e}")
    print("\n=== 전체 타임라인 순회 ===")
    data = await browser_fetch_json(
        page,
        f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page=1&count=20'
    )
    if not data or data.get('error_code'):
        print(f"  1페이지 실패: {data}")
        return collected
    max_page = data.get('maxPage', 600)
    total = data.get('total', '?')
    print(f"  사용자 ID: {user_id} | 전체 글 수: {total} | 전체 페이지 수: {max_page}")

    total_posts = 0
    found = 0

    def process(d):
        nonlocal total_posts, found
        for post in d.get('statuses', []):
            total_posts += 1
            text = clean(post.get('text', '') or post.get('description', ''))
            title = clean(post.get('title', ''))
            rt = post.get('retweeted_status') or {}
            rt_text = clean(rt.get('text', ''))
            own_text = (text or '').strip()
            # 쉐추가 단순 리포스트에 자동으로 넣는 문구(사이트 값과 비교하므로 중국어 그대로 둔다)
            if own_text in ('', '转发微博', '轉發微博', 'Repost'):
                continue
            pid = str(post.get('id', ''))
            date = parse_ts(post.get('created_at', 0))
            entry = {'id': pid, 'date': date, 'title': title, 'text': own_text,
                     'url': f'https://xueqiu.com/{user_id}/{pid}'}
            if rt:
                rt_user = (rt.get('user') or {}).get('screen_name', '')
                entry['retweet_of'] = f'@{rt_user}: {rt_text}'
            # 전체 캐시(거르지 않음)
            if dump_all_path and pid not in all_posts:
                all_posts[pid] = entry
            # 키워드로 걸러 수집
            if keywords and is_match(title + ' ' + own_text, keywords):
                if pid not in collected:
                    collected[pid] = entry
                    found += 1
                    preview = own_text[:80] if own_text else (rt_text[:80] if rt_text else title[:80])
                    print(f"  ✓ [{date}] {preview}...")

    process(data)
    start_page = 2
    if os.path.exists(progress_path):
        try:
            with open(progress_path) as f:
                prev = json.load(f)
            start_page = max(2, prev.get('next_page', 2))
            for e in prev.get('collected', []):
                collected[e['id']] = e
                found += 1
            print(f"  ↪ 이어받기: {start_page}페이지부터 시작, 기존 {found}건")
        except Exception as e:
            print(f"  진행 파일 읽기 실패: {e}")

    def save_progress(next_page):
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump({'next_page': next_page, 'collected': list(collected.values())},
                      f, ensure_ascii=False)
        if dump_all_path:
            with open(dump_all_path, 'w', encoding='utf-8') as f:
                json.dump(list(all_posts.values()), f, ensure_ascii=False)

    consec_fail = 0
    for p in range(start_page, max_page + 1):
        try:
            data = await browser_fetch_json(
                page,
                f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page={p}&count=20',
                timeout_s=15,
            )
        except Exception as e:
            print(f"  {p}페이지 예외: {e}")
            data = None
        if not data:
            consec_fail += 1
            print(f"  {p}페이지 무응답/타임아웃(연속 {consec_fail}회)")
            if consec_fail >= 5:
                print("  5회 연속 실패. 진행 상황을 저장하고 종료합니다(다시 실행하면 자동으로 이어받음)")
                save_progress(p)
                break
            await asyncio.sleep(5 * consec_fail)
            continue
        consec_fail = 0
        if data.get('error_code'):
            print(f"  {p}페이지 오류: {data.get('error_code')} {data.get('error_description')}")
            save_progress(p)
            break
        statuses = data.get('statuses', [])
        if not statuses:
            print(f"  {p}페이지가 비어 있어 종료합니다")
            break
        prev_found = found
        process(data)
        if p % 10 == 0 or found > prev_found:
            print(f"  {p}/{max_page}페이지 | 스캔 {total_posts}건 | 일치 {found}건")
        if p % 10 == 0:
            save_progress(p + 1)
        if p % 50 == 0:
            print(f"  ⏸ {p}페이지 후 30초 휴식")
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(random.uniform(2.0, 4.0))
    else:
        if os.path.exists(progress_path):
            os.remove(progress_path)

    # 마지막으로 전체 캐시를 디스크에 기록
    if dump_all_path:
        with open(dump_all_path, 'w', encoding='utf-8') as f:
            json.dump(list(all_posts.values()), f, ensure_ascii=False)
        print(f"  전체 캐시 → {dump_all_path} ({len(all_posts)}건)")
    print(f"\n완료: {total_posts}건 스캔, {found}건 일치")
    return collected


def format_md(collected, user_id, keywords):
    posts = sorted(collected.values(), key=lambda x: x.get('date', ''))
    lines = [
        f"# 쉐추(雪球) 발언 정리: 사용자 {user_id}",
        "",
        f"> **정보 출처**: 쉐추(雪球) https://xueqiu.com/u/{user_id}",
        f"> **정리 일자**: {datetime.now().strftime('%Y-%m-%d')}",
        f"> **수록 건수**: {len(posts)}건",
        f"> **키워드 필터**: {', '.join(keywords)}",
        f"> **수집 방식**: Playwright 로그인 상태 + user_timeline.json 전체 순회(본인 원글만)",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(posts, 1):
        lines.append(f"## {i}. {p.get('date','?')}")
        lines.append("")
        if p.get('title'):
            lines += [f"**【{p['title']}】**", ""]
        if p.get('retweet_of'):
            lines += [f"> 리포스트 원문: {p['retweet_of']}", ""]
        if p.get('text'):
            lines.append(p['text'])
            lines.append("")
        lines += [f"출처: {p.get('url','')}", "", "---", ""]
    return '\n'.join(lines)


def parse_args():
    ap = argparse.ArgumentParser(description="쉐추(雪球) 사용자 타임라인 크롤러(키워드로 본인 원글만 선별)")
    ap.add_argument('--user-id', type=int, help='쉐추 사용자 ID(프로필 URL 의 숫자 부분)')
    ap.add_argument('--keywords', type=str, default='',
                    help='키워드 목록, 쉼표로 구분(쉐추 원문과 대조하므로 중국어로 입력). 예: 拼多多,PDD,黄峥,Temu')
    ap.add_argument('--output', type=str, default='', help='markdown 출력 경로')
    ap.add_argument('--raw-json', type=str, default='', help='(선택) 일치한 항목의 원본 JSON 출력 경로')
    ap.add_argument('--state-path', type=str, default='/tmp/xueqiu_state.json',
                    help='로그인 상태 캐시 파일(기본 /tmp/xueqiu_state.json)')
    ap.add_argument('--dump-all', type=str, default='',
                    help='전체 캐시 경로: 크롤링하면서 해당 사용자의 모든 원글을 여기에도 기록한다. 이후 오프라인 다주제 분석용')
    ap.add_argument('--from-cache', type=str, default='',
                    help='크롤링을 건너뛰고 기존 전체 캐시 JSON 을 걸러 markdown 을 만든다(--keywords 와 --output 필요)')
    return ap.parse_args()


def filter_from_cache(cache_path, keywords, user_id):
    posts = json.load(open(cache_path))
    out = []
    for p in posts:
        if is_match((p.get('title','') + ' ' + p.get('text','')), keywords):
            out.append(p)
    return {p['id']: p for p in out}


async def main():
    _safe_stdio()
    args = parse_args()
    keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]

    # 오프라인 필터 모드
    if args.from_cache:
        if not (keywords and args.output):
            print("--from-cache 는 --keywords 와 --output 을 함께 지정해야 합니다")
            return
        user_id = args.user_id or 0
        collected = filter_from_cache(args.from_cache, keywords, user_id)
        print(f"캐시 {args.from_cache} 에서 {len(collected)}건 선별(키워드: {keywords})")
        if not collected:
            return
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(format_md(collected, user_id, keywords))
        print(f"Markdown → {args.output}")
        return

    if not args.user_id:
        print("--user-id 가 필요합니다")
        return

    progress_path = args.state_path + f'.progress.{args.user_id}'
    raw_json = args.raw_json or f'/tmp/xueqiu_{args.user_id}_raw.json'

    print("=" * 60)
    print(f"쉐추 크롤러 | user_id={args.user_id} | keywords={keywords} | dump_all={args.dump_all}")
    print("=" * 60)

    async with async_playwright() as pw:
        session = await load_with_state(pw, args.state_path, args.user_id)
        if not session:
            session = await interactive_login(pw, args.state_path, args.user_id)
        if not session:
            print("로그인할 수 없어 종료합니다")
            return
        browser, _, page = session
        collected = await fetch_all_timeline(page, args.user_id, keywords, progress_path, args.dump_all)
        await browser.close()

    print(f"\n=== 최종: {len(collected)}건 일치 ===")
    if not collected:
        return
    with open(raw_json, 'w', encoding='utf-8') as f:
        json.dump(list(collected.values()), f, ensure_ascii=False, indent=2)
    print(f"원본 JSON → {raw_json}")
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(format_md(collected, args.user_id, keywords))
        print(f"Markdown  → {args.output}")


if __name__ == '__main__':
    asyncio.run(main())

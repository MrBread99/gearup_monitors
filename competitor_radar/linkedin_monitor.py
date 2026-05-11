"""
ExitLag LinkedIn 动态监控
==========================================
抓取 ExitLag LinkedIn 公司页公开 Updates 区块。
发现新动态时返回 competitor_radar 类型 issue，由聚合入口统一发 POPO。

说明:
- LinkedIn 没有可直接公开使用的公司动态 API，这里只解析公开 HTML。
- 首次运行只保存当前可见动态为基线，不报警，避免部署当天刷历史内容。
- 若 requests 被拦截，降级到共享 Playwright；仍失败则登记数据源异常。
==========================================
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from html import unescape
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import report_scrape_block


COMPANY_NAME = "ExitLag"
COMPANY_URL = "https://www.linkedin.com/company/exitlag"
POSTS_URL = "https://www.linkedin.com/company/exitlag/posts/?feedView=all"
SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "linkedin_monitor_snapshot.json",
)
SNAPSHOT_VERSION = 1
MAX_SNAPSHOT_ENTRIES = 100
MAX_NEW_POSTS_PER_RUN = 5
HEALTH_ALERT_FAILURES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

_latest_linkedin_status: dict = {}
_last_fetch_status: int | None = None


def load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_version") == SNAPSHOT_VERSION:
                return data
        except Exception:
            pass
    return {"_version": SNAPSHOT_VERSION}


def save_snapshot(data: dict):
    data["_version"] = SNAPSHOT_VERSION
    posts = data.get("exitlag", [])
    if isinstance(posts, list) and len(posts) > MAX_SNAPSHOT_ENTRIES:
        data["exitlag"] = posts[-MAX_SNAPSHOT_ENTRIES:]
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_health(snapshot: dict) -> dict:
    health_map = snapshot.setdefault("_health", {})
    return health_map.setdefault("exitlag_linkedin", {
        "consecutive_failures": 0,
        "last_success_at": "",
        "last_failure_at": "",
        "last_status_code": None,
        "last_post_count": 0,
        "failure_alert_active": False,
    })


def _record_health_failure(snapshot: dict, status_code: int | None, reason: str) -> None:
    health = _get_health(snapshot)
    health["consecutive_failures"] = int(health.get("consecutive_failures", 0) or 0) + 1
    health["last_failure_at"] = _now_iso()
    health["last_status_code"] = status_code
    health["last_failure_reason"] = reason

    failures = health["consecutive_failures"]
    print(f"[LinkedIn] 数据源失败 {failures}/{HEALTH_ALERT_FAILURES}: {reason}")
    if failures >= HEALTH_ALERT_FAILURES and not health.get("failure_alert_active"):
        report_scrape_block("exitlag_linkedin", COMPANY_URL, status_code)
        health["failure_alert_active"] = True


def _record_health_success(snapshot: dict, post_count: int) -> dict | None:
    health = _get_health(snapshot)
    previous_failures = int(health.get("consecutive_failures", 0) or 0)
    was_alerting = bool(health.get("failure_alert_active"))

    health["consecutive_failures"] = 0
    health["last_success_at"] = _now_iso()
    health["last_status_code"] = 200
    health["last_post_count"] = post_count
    health["last_failure_reason"] = ""
    health["failure_alert_active"] = False

    if was_alerting or previous_failures >= HEALTH_ALERT_FAILURES:
        return {
            "game": "ExitLag LinkedIn",
            "region": "Global",
            "country": "",
            "issue": (
                "ExitLag LinkedIn 数据源已恢复\n"
                f"    恢复前连续失败: {previous_failures} 次\n"
                f"    当前解析动态数: {post_count}"
            ),
            "alert_type": "competitor_radar",
            "source_name": "ExitLag LinkedIn",
            "source_url": COMPANY_URL,
        }
    return None


def _fetch_with_requests(url: str) -> tuple[str | None, int]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200 and "Updates" in resp.text and "ExitLag" in resp.text:
            return resp.text, 200
        return None, resp.status_code
    except Exception as e:
        print(f"[LinkedIn] requests 抓取失败 {url}: {e}")
        return None, 0


def _fetch_with_playwright(url: str) -> tuple[str | None, int]:
    try:
        from utils.playwright_client import pw_fetch
        return pw_fetch(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[LinkedIn] Playwright 抓取失败 {url}: {e}")
        return None, 0


def fetch_linkedin_html() -> str | None:
    """
    获取 LinkedIn 页面 HTML。
    优先 company 页，因为公开页面已包含 Updates；posts 页作为备用。
    """
    global _last_fetch_status
    last_status = None
    for url in (COMPANY_URL, POSTS_URL):
        html, status = _fetch_with_requests(url)
        if html:
            print(f"[LinkedIn] requests 成功获取 {url}")
            _last_fetch_status = 200
            return html
        last_status = status

    for url in (COMPANY_URL, POSTS_URL):
        html, status = _fetch_with_playwright(url)
        if html and "Updates" in html and "ExitLag" in html:
            print(f"[LinkedIn] Playwright 成功获取 {url}")
            _last_fetch_status = 200
            return html
        last_status = status

    _last_fetch_status = last_status
    return None


def _clean_line(line: str) -> str:
    return unescape(line).replace("\xa0", " ").strip()


def _is_relative_time(line: str) -> bool:
    text = line.strip()
    return bool(re.match(r"^\d+\s*(m|h|d|w|mo|yr)(\s+Edited)?$", text, re.I)) or bool(
        re.match(r"^\d+\s+(minute|hour|day|week|month|year)s?\s+ago(\s+Edited)?$", text, re.I)
    )


def _is_noise_line(line: str) -> bool:
    if not line:
        return True
    if line in {"``", "`", "Like", "Comment", "Share", "Report this post", "…more"}:
        return True
    if re.match(r"^\d+$", line):
        return True
    if re.match(r"^\d+\s+Comment(s)?$", line):
        return True
    if line.startswith("Image:") or line.startswith("No alternative text"):
        return True
    return False


def _build_slug(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def parse_linkedin_posts(html: str) -> list[dict]:
    """
    从 LinkedIn 公开页面文本中抽取 Updates。
    LinkedIn 页面没有稳定公开 JSON，这里以相对时间行作为动态分隔点。
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean_line(line) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]

    try:
        start = next(i for i, line in enumerate(lines) if line == "Updates")
        lines = lines[start + 1:]
    except StopIteration:
        pass

    time_indexes = [i for i, line in enumerate(lines) if _is_relative_time(line)]
    posts = []
    seen_slugs = set()

    for idx, time_idx in enumerate(time_indexes):
        next_time_idx = time_indexes[idx + 1] if idx + 1 < len(time_indexes) else len(lines)
        relative_time = lines[time_idx]
        segment = lines[time_idx + 1:next_time_idx]
        content_lines = []

        for line in segment:
            if _is_noise_line(line):
                continue
            if line == COMPANY_NAME or "followers" in line.lower():
                continue
            if line in {"Join now", "Sign in", "See jobs", "Follow"}:
                continue
            content_lines.append(line)

        content = " ".join(content_lines)
        content = re.sub(r"\s+", " ", content).strip()
        if len(content) < 30:
            continue

        slug = _build_slug(content)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        posts.append({
            "slug": slug,
            "date": relative_time,
            "content": content,
            "url": COMPANY_URL,
        })

    return posts


def get_linkedin_status_summary() -> str:
    if not _latest_linkedin_status:
        return ""
    return (
        f"  [ExitLag LinkedIn] {_latest_linkedin_status['date']} | "
        f"{_latest_linkedin_status['content'][:120]}... | {_latest_linkedin_status['url']}"
    )


def check_exitlag_linkedin() -> list:
    """
    检查 ExitLag LinkedIn 公司动态，返回新增动态 issue。
    """
    snapshot = load_snapshot()
    html = fetch_linkedin_html()
    if not html:
        _record_health_failure(snapshot, _last_fetch_status, "页面不可达或公开 Updates 区块不可用")
        save_snapshot(snapshot)
        return []

    posts = parse_linkedin_posts(html)
    if not posts:
        print("[LinkedIn] 未解析到 ExitLag 动态。")
        _record_health_failure(snapshot, 200, "页面可达但解析到 0 条动态，可能是 LinkedIn 结构变化")
        save_snapshot(snapshot)
        return []

    issues = []
    recovery_issue = _record_health_success(snapshot, len(posts))
    if recovery_issue:
        issues.append(recovery_issue)

    _latest_linkedin_status.update({
        "date": posts[0]["date"],
        "content": posts[0]["content"],
        "url": posts[0]["url"],
    })

    key = "exitlag"
    current_slugs = [post["slug"] for post in posts]
    if key not in snapshot:
        snapshot[key] = current_slugs
        save_snapshot(snapshot)
        print(f"[LinkedIn] 首次运行，已保存 {len(current_slugs)} 条动态为基线，不报警。")
        return issues

    seen = set(snapshot.get(key, []))
    new_posts = [post for post in posts if post["slug"] not in seen]
    if not new_posts:
        print("[LinkedIn] 无新动态。")
        save_snapshot(snapshot)
        return issues

    if len(new_posts) > MAX_NEW_POSTS_PER_RUN:
        print(f"[LinkedIn] 发现 {len(new_posts)} 条新动态，只报警最近 {MAX_NEW_POSTS_PER_RUN} 条。")
        new_posts = new_posts[:MAX_NEW_POSTS_PER_RUN]

    for post in new_posts:
        content = post["content"]
        if len(content) > 900:
            content = content[:900].rstrip() + "..."
        issues.append({
            "game": "ExitLag LinkedIn",
            "region": "Global",
            "country": "",
            "issue": (
                "ExitLag LinkedIn 新动态\n"
                f"    发布时间: {post['date']}\n"
                f"    内容: {content}"
            ),
            "alert_type": "competitor_radar",
            "source_name": "ExitLag LinkedIn",
            "source_url": post["url"],
        })

    updated = list(seen.union(current_slugs))
    snapshot[key] = updated[-MAX_SNAPSHOT_ENTRIES:]
    save_snapshot(snapshot)
    print(f"[LinkedIn] 检测到 {len(issues)} 条新动态。")
    return issues


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    issues = check_exitlag_linkedin()
    if issues:
        for issue in issues:
            print(f"[{issue['game']}] {issue['issue']}")
    else:
        print("无新 LinkedIn 动态。")

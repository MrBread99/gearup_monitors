"""
竞品博客动态监控
==========================================
定时抓取 ExitLag / LagoFast 官方博客，
发现新文章时通过 Qwen AI 生成中文摘要并发送 POPO 报警。

抓取策略（绕过反爬）：
- ExitLag: WordPress REST API 优先 → Playwright + stealth → requests HTML 解析
- LagoFast: requests + __NEXT_DATA__ JSON 解析 → Playwright fallback

去重机制：
- 快照文件记录已见文章 slug，跨运行持久化（GitHub Actions cache）。
- 首次运行仅保存基线，不生成报警。
==========================================
"""

import requests as req_lib
import json
import os
import sys
import re
import time
import random
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import report_scrape_block

# ==========================================
# 配置
# ==========================================

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "blog_monitor_snapshot.json",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

API_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# 快照最多保留条数（防无限膨胀）
MAX_SNAPSHOT_ENTRIES = 200


# ==========================================
# 快照管理
# ==========================================

def load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_snapshot(data: dict):
    for key in data:
        if isinstance(data[key], list) and len(data[key]) > MAX_SNAPSHOT_ENTRIES:
            data[key] = data[key][-MAX_SNAPSHOT_ENTRIES:]
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==========================================
# AI 摘要（Qwen）
# ==========================================

_qwen_client = None


def _get_qwen_client():
    global _qwen_client
    if _qwen_client is not None:
        return _qwen_client
    if not QWEN_API_KEY:
        return None
    try:
        from openai import OpenAI
        _qwen_client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        return _qwen_client
    except Exception as e:
        print(f"[Blog] Qwen 客户端初始化失败: {e}")
        return None


def _summarize_blog_post(competitor: str, title: str, content: str) -> str:
    """调用 Qwen AI 生成博客文章中文摘要。"""
    client = _get_qwen_client()
    if not client:
        return f"(AI 未配置，标题原文) {title}"

    if len(content) > 3000:
        content = content[:3000] + "..."

    prompt = (
        f"你是一个全球游戏加速器（GPN）的资深商业情报分析师。\n"
        f"竞品【{competitor}】刚发布了一篇新博客文章。\n\n"
        f"【文章标题】: {title}\n"
        f"【文章内容】: {content}\n\n"
        f"请用中文分析并输出:\n"
        f"1. 【文章摘要】: 用 2-3 句话概括文章核心内容\n"
        f"2. 【商业情报】: 从加速器竞争角度分析这篇文章的意图"
        f"（如：SEO 抢流量、推广新功能、蹭热门游戏热度等）\n"
        f"3. 【应对建议】: 我们应该如何回应？(1-2 句)\n"
        f"(输出纯文本，不要使用 Markdown 加粗或特殊符号)"
    )
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个敏锐的游戏加速器情报专家。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return str(resp.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Blog] AI 摘要失败: {e}")
        return f"(AI 分析失败) 标题: {title}"


# ==========================================
# ExitLag 博客抓取（WordPress）
# ==========================================

def _fetch_exitlag_via_wp_api() -> list | None:
    """
    通过 WordPress REST API 获取最新博客文章（最可靠，含全文）。
    ExitLag 博客基于 WordPress，REST API 默认公开。
    """
    api_url = "https://www.exitlag.com/blog/wp-json/wp/v2/posts"
    params = {
        "per_page": 10,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,slug,title,link,date,excerpt,content",
    }
    try:
        time.sleep(random.uniform(1.0, 3.0))
        resp = req_lib.get(api_url, params=params, headers=API_HEADERS, timeout=20)
        if resp.status_code == 200:
            posts = resp.json()
            results = []
            for post in posts:
                title_html = post.get("title", {}).get("rendered", "")
                excerpt_html = post.get("excerpt", {}).get("rendered", "")
                content_html = post.get("content", {}).get("rendered", "")

                title = BeautifulSoup(title_html, "html.parser").get_text(strip=True)
                excerpt = BeautifulSoup(excerpt_html, "html.parser").get_text(strip=True)
                content = BeautifulSoup(content_html, "html.parser").get_text(" ", strip=True)

                results.append({
                    "slug": post.get("slug", ""),
                    "title": title,
                    "url": post.get("link", ""),
                    "date": post.get("date", ""),
                    "excerpt": excerpt,
                    "content": content,
                })
            print(f"[ExitLag] WordPress API 获取到 {len(results)} 篇文章。")
            return results
        else:
            print(f"[ExitLag] WordPress API HTTP {resp.status_code}")
            if resp.status_code in (403, 429):
                report_scrape_block("exitlag_blog_api", url=api_url, status_code=resp.status_code)
            return None
    except Exception as e:
        print(f"[ExitLag] WordPress API 请求异常: {e}")
        return None


def _parse_exitlag_html(html: str) -> list:
    """解析 ExitLag 博客 HTML，提取文章列表。"""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_slugs = set()

    articles = soup.select("article.type-post")
    for article in articles:
        title_link = article.select_one(".entry-title a")
        if not title_link:
            title_link = article.select_one("a.absolute[href]")
        if not title_link:
            continue

        url = title_link.get("href", "")
        slug = url.rstrip("/").split("/")[-1] if url else ""
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        title = title_link.get_text(strip=True)

        time_el = article.select_one("time[datetime]")
        date_str = time_el.get("datetime", "") if time_el else ""

        excerpt_el = article.select_one(".entry-summary p")
        excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""

        results.append({
            "slug": slug,
            "title": title,
            "url": url,
            "date": date_str,
            "excerpt": excerpt,
            "content": excerpt,  # 列表页只有摘要
        })

    print(f"[ExitLag] HTML 解析获取到 {len(results)} 篇文章。")
    return results


def _fetch_exitlag_via_playwright() -> list | None:
    """Playwright + stealth 抓取 ExitLag 博客页面。"""
    try:
        from utils.playwright_client import pw_fetch
    except ImportError:
        print("[ExitLag] Playwright 未安装，跳过。")
        return None

    url = "https://www.exitlag.com/blog/"
    html, status = pw_fetch(url)
    if html is None or status != 200:
        if status == 403:
            report_scrape_block("exitlag_blog", url=url, status_code=403)
        return None

    return _parse_exitlag_html(html)


def _fetch_exitlag_via_requests() -> list | None:
    """普通 requests 兜底抓取。"""
    url = "https://www.exitlag.com/blog/"
    try:
        time.sleep(random.uniform(2.0, 4.0))
        resp = req_lib.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            return _parse_exitlag_html(resp.text)
        if resp.status_code in (403, 429):
            report_scrape_block("exitlag_blog", url=url, status_code=resp.status_code)
        return None
    except Exception as e:
        print(f"[ExitLag] requests 失败: {e}")
        return None


def fetch_exitlag_posts() -> list:
    """
    三层降级获取 ExitLag 博客文章。
    WordPress REST API → Playwright + stealth → requests
    """
    posts = _fetch_exitlag_via_wp_api()
    if posts is not None:
        return posts

    print("[ExitLag] WP API 不可用，尝试 Playwright...")
    posts = _fetch_exitlag_via_playwright()
    if posts is not None:
        return posts

    print("[ExitLag] Playwright 不可用，尝试 requests...")
    posts = _fetch_exitlag_via_requests()
    if posts is not None:
        return posts

    print("[ExitLag] 所有抓取方式均失败。")
    return []


# ==========================================
# LagoFast 博客抓取（Next.js）
# ==========================================

def _parse_lagofast_nextdata(html: str) -> list | None:
    """从 LagoFast 页面 HTML 中提取 __NEXT_DATA__ JSON 并解析文章列表。"""
    match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        print("[LagoFast] 未找到 __NEXT_DATA__ JSON")
        return None

    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        print("[LagoFast] __NEXT_DATA__ JSON 解析失败")
        return None

    articles_data = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("x", {})
        .get("articles", [])
    )

    results = []
    seen_slugs = set()

    for category in articles_data:
        blogs = category.get("blogs", [])
        for blog in blogs:
            slug = blog.get("article_identifies", "")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            results.append({
                "slug": slug,
                "title": blog.get("title", ""),
                "url": f"https://www.lagofast.com/en/blog/{slug}/",
                "date": blog.get("update_at", ""),
                "excerpt": blog.get("seo_description", ""),
                "content": blog.get("seo_description", ""),
            })

    print(f"[LagoFast] __NEXT_DATA__ 解析获取到 {len(results)} 篇文章。")
    return results if results else None


def _parse_lagofast_html_dom(html: str) -> list | None:
    """
    从 LagoFast HTML DOM 解析文章列表（__NEXT_DATA__ 不可用时的备选）。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_slugs = set()

    for link in soup.select('a[href*="/en/blog/"]'):
        href = link.get("href", "")
        # 只匹配文章链接（排除 /en/blog/ 自身）
        slug_match = re.search(r'/en/blog/([^/]+)/', href)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # 在 link 内部找标题和摘要
        article_el = link.select_one("article")
        if not article_el:
            continue

        divs = article_el.select("div")
        title = ""
        excerpt = ""
        date_str = ""

        for div in divs:
            classes = " ".join(div.get("class", []))
            text = div.get_text(strip=True)
            if not text:
                continue
            # 标题: truncate + text-white
            if "truncate" in classes and "text-white" in classes:
                title = text
            # 摘要: line-clamp-2
            elif "line-clamp-2" in classes:
                excerpt = text
            # 日期: text-[#FFFFFF4D]
            elif "FFFFFF4D" in classes:
                date_str = text.replace("Last Update:", "").strip()

        if title:
            full_url = f"https://www.lagofast.com{href}" if href.startswith("/") else href
            results.append({
                "slug": slug,
                "title": title,
                "url": full_url,
                "date": date_str,
                "excerpt": excerpt,
                "content": excerpt,
            })

    print(f"[LagoFast] HTML DOM 解析获取到 {len(results)} 篇文章。")
    return results if results else None


def _fetch_lagofast_via_requests() -> list | None:
    """requests 获取 LagoFast 博客页面，优先解析 __NEXT_DATA__ JSON。"""
    url = "https://www.lagofast.com/en/blog/"
    try:
        time.sleep(random.uniform(2.0, 4.0))
        resp = req_lib.get(url, headers=HEADERS, timeout=25)
        if resp.status_code == 200:
            # 优先尝试 __NEXT_DATA__
            posts = _parse_lagofast_nextdata(resp.text)
            if posts:
                return posts
            # 退而解析 DOM
            return _parse_lagofast_html_dom(resp.text)
        print(f"[LagoFast] requests HTTP {resp.status_code}")
        if resp.status_code in (403, 429):
            report_scrape_block("lagofast_blog", url=url, status_code=resp.status_code)
        return None
    except Exception as e:
        print(f"[LagoFast] requests 失败: {e}")
        return None


def _fetch_lagofast_via_playwright() -> list | None:
    """Playwright 获取 LagoFast 博客页面。"""
    try:
        from utils.playwright_client import pw_fetch
    except ImportError:
        print("[LagoFast] Playwright 未安装，跳过。")
        return None

    url = "https://www.lagofast.com/en/blog/"
    html, status = pw_fetch(url)
    if html is None or status != 200:
        if status == 403:
            report_scrape_block("lagofast_blog", url=url, status_code=403)
        return None

    posts = _parse_lagofast_nextdata(html)
    if posts:
        return posts
    return _parse_lagofast_html_dom(html)


def fetch_lagofast_posts() -> list:
    """
    双层降级获取 LagoFast 博客文章。
    requests + __NEXT_DATA__/DOM → Playwright
    """
    posts = _fetch_lagofast_via_requests()
    if posts is not None:
        return posts

    print("[LagoFast] requests 不可用，尝试 Playwright...")
    posts = _fetch_lagofast_via_playwright()
    if posts is not None:
        return posts

    print("[LagoFast] 所有抓取方式均失败。")
    return []


# ==========================================
# 新文章全文抓取（仅对新发现的文章执行）
# ==========================================

def _fetch_article_content(url: str) -> str:
    """
    抓取单篇博客文章的正文内容，用于 AI 摘要。
    仅在列表页摘要过短时调用，减少请求量。
    """
    try:
        time.sleep(random.uniform(2.0, 5.0))
        resp = req_lib.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试多种常见正文容器
        content_el = (
            soup.select_one("article .entry-content")        # WordPress
            or soup.select_one(".prose-content")              # ExitLag custom
            or soup.select_one("article")                     # 通用
            or soup.select_one('[class*="content"]')          # 模糊匹配
        )
        if content_el:
            return content_el.get_text(" ", strip=True)[:3000]
        return ""
    except Exception as e:
        print(f"[Blog] 正文抓取失败 {url}: {e}")
        return ""


# ==========================================
# 主逻辑
# ==========================================

COMPETITORS = {
    "ExitLag": fetch_exitlag_posts,
    "LagoFast": fetch_lagofast_posts,
}


def check_competitor_blogs() -> list:
    """
    检查所有竞品博客，返回新文章的 issue 列表。
    首次运行仅保存基线快照，不生成报警。

    返回值兼容 send_popo_alert() 的 issues_list 格式。
    """
    snapshot = load_snapshot()
    all_issues = []

    for name, fetch_fn in COMPETITORS.items():
        key = name.lower()
        print(f"\n{'─' * 40}")
        print(f"[{name}] 开始检查博客动态...")

        posts = fetch_fn()
        if not posts:
            print(f"[{name}] 未获取到任何文章。")
            continue

        # 首次运行：保存基线，不报警
        if key not in snapshot:
            snapshot[key] = [p["slug"] for p in posts if p["slug"]]
            print(f"[{name}] 首次运行，已保存 {len(snapshot[key])} 篇文章为基线，不生成报警。")
            continue

        seen_slugs = set(snapshot[key])
        new_posts = [p for p in posts if p["slug"] and p["slug"] not in seen_slugs]

        if not new_posts:
            print(f"[{name}] 无新文章。")
            continue

        print(f"[{name}] 发现 {len(new_posts)} 篇新文章，正在生成 AI 摘要...")

        for post in new_posts:
            # 如果列表页内容不够丰富，尝试抓取全文
            content = post.get("content", "") or post.get("excerpt", "")
            if len(content) < 200:
                print(f"[{name}] 摘要过短，抓取全文: {post['url']}")
                full_text = _fetch_article_content(post["url"])
                if full_text:
                    content = full_text

            ai_summary = _summarize_blog_post(name, post["title"], content)

            issue_text = (
                f"竞品博客新文章\n"
                f"    标题: {post['title']}\n"
                f"    发布时间: {post.get('date', '未知')}\n"
                f"    {ai_summary}"
            )

            all_issues.append({
                "game": name,
                "region": "Global",
                "country": "",
                "issue": issue_text,
                "alert_type": "competitor_radar",
                "source_name": f"{name} 官方博客",
                "source_url": post["url"],
            })

            # 记入快照
            seen_slugs.add(post["slug"])

        # 更新快照
        snapshot[key] = list(seen_slugs)

    save_snapshot(snapshot)
    print(f"\n[Blog] 共检测到 {len(all_issues)} 篇新博客文章。")
    return all_issues


# ==========================================
# 独立运行入口（调试用）
# ==========================================

if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL

    try:
        print("=" * 50)
        print("竞品博客动态监控 (测试运行)")
        print("=" * 50)
        issues = check_competitor_blogs()
        if issues:
            for issue in issues:
                print(f"\n[{issue['game']}] {issue['issue'][:200]}...")
            if POPO_WEBHOOK_URL:
                send_popo_alert(POPO_WEBHOOK_URL, issues)
        else:
            print("无新博客文章（或首次运行已保存基线）。")
    except Exception as e:
        print(f"[Blog] 顶层异常: {e}")
        import traceback
        traceback.print_exc()

    flush_scrape_block_alerts(POPO_WEBHOOK_URL if POPO_WEBHOOK_URL else None)

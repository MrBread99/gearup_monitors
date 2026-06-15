"""
IsTheServiceDown 平台故障检测客户端
==========================================
通过解析 istheservicedown.com 的 <noscript> 报告表格，
检测平台是否存在故障（报告量超过基线）。

替代 Reddit 搜索作为平台状态的社区信号来源。
页面数据为服务端渲染，不需要 JS 执行。
==========================================
"""

import requests
import time
import random
import re
from bs4 import BeautifulSoup
from utils.notifier import report_scrape_block

_BASE_URL = "https://istheservicedown.com/problems"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 请求间隔（秒），避免高频触发反爬
_last_request = 0
_MIN_INTERVAL = 2.0


def _throttle():
    global _last_request
    now = time.time()
    elapsed = now - _last_request
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed + random.uniform(0.5, 1.5))
    _last_request = time.time()


def check_service_status(slug: str) -> dict | None:
    """
    检查指定服务在 IsTheServiceDown 上的状态。

    参数:
        slug: 服务标识，如 'steam', 'battle-net', 'xbox-live'

    返回:
        {
            'slug': str,
            'status': 'ok' | 'outage' | 'unknown',
            'status_text': str,          # 页面原文，如 "No problems detected"
            'recent_reports': int,        # 最近 2 小时的报告总数
            'recent_baseline': int,       # 最近 2 小时的基线总数
            'peak_reports': int,          # 最近 2 小时单次最高报告数
            'source_url': str,
        }
        失败返回 None。
    """
    url = f"{_BASE_URL}/{slug}"
    _throttle()

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[ITSD] {slug} HTTP {resp.status_code}")
            report_scrape_block("itsd", url, resp.status_code)
            return None
    except Exception as e:
        print(f"[ITSD] {slug} 请求失败: {e}")
        report_scrape_block("itsd", url)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. 解析状态指示
    status = "unknown"
    status_text = ""

    # 状态栏: bg-status-green / bg-status-orange / bg-brand-red
    status_bar = soup.select_one(".bg-status-green, .bg-status-orange, .bg-brand-red")
    if status_bar:
        parent = status_bar.find_parent("div", class_="flex")
        if parent:
            p_tags = parent.select("p")
            if p_tags:
                status_text = p_tags[0].get_text(strip=True)

        classes = " ".join(status_bar.get("class", []))
        if "status-green" in classes:
            status = "ok"
        elif "status-orange" in classes or "brand-red" in classes:
            status = "outage"

    # 2. 解析 <noscript> 报告表格（24h 数据，每 20 分钟一条）
    recent_reports = 0
    recent_baseline = 0
    peak_reports = 0

    noscript = soup.find("noscript")
    if noscript:
        rows = noscript.select("tbody tr")
        # 取最近 6 条（= 最近 2 小时）
        recent_rows = rows[-6:] if len(rows) >= 6 else rows
        for row in recent_rows:
            cells = row.select("td")
            if len(cells) >= 3:
                try:
                    reports = int(cells[1].get_text(strip=True))
                    baseline = int(cells[2].get_text(strip=True))
                    recent_reports += reports
                    recent_baseline += baseline
                    if reports > peak_reports:
                        peak_reports = reports
                except ValueError:
                    pass

    # 如果表格数据显示报告量超过基线，覆盖状态
    if recent_reports > 0 and recent_reports > recent_baseline * 1.5:
        status = "outage"

    return {
        "slug": slug,
        "status": status,
        "status_text": status_text,
        "recent_reports": recent_reports,
        "recent_baseline": recent_baseline,
        "peak_reports": peak_reports,
        "source_url": url,
    }


def check_services_batch(slugs: list[str]) -> dict[str, dict | None]:
    """
    批量检查多个服务状态。
    返回 {slug: result_dict} 映射。
    """
    results = {}
    for slug in slugs:
        results[slug] = check_service_status(slug)
    return results

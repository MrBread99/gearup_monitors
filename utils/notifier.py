import requests
import json
import os
from datetime import datetime, timezone, timedelta

# 从环境变量中获取 POPO Webhook URL
POPO_WEBHOOK_URL = os.environ.get("POPO_WEBHOOK_URL")

# ==========================================
# 反爬拦截报警系统
# ==========================================
# 各数据源检测到被拦截时调用 report_scrape_block() 登记，
# 在脚本末尾统一调用 flush_scrape_block_alerts() 发送。
# 同一数据源在一次运行内只发一条合并消息，不刷屏。
# ==========================================

# 每次运行的拦截事件累积池
# 格式: { source_key: {'display_name': str, 'count': int, 'urls': [str], 'codes': set()} }
_scrape_block_registry: dict = {}

# 各数据源的静态应对建议
_SCRAPE_ADVICE = {
    'google_captcha': {
        'display_name': 'Google 搜索 (google.com)',
        'reason': 'Google 检测到自动化请求，触发 reCAPTCHA / CAPTCHA 验证，实际返回内容为空',
        'short_term': '已自动 fallback 到 DuckDuckGo，本次数据获取不受影响',
        'long_term': '建议接入 Google Custom Search JSON API（官方，免费 100 次/天），彻底消除 CAPTCHA 风险',
    },
    'bahamut': {
        'display_name': '巴哈姆特论坛 (gamer.com.tw)',
        'reason': '巴哈姆特返回非 200 状态，可能为 429 请求频率过高或 IP 封禁',
        'short_term': '本次已跳过该游戏的台湾区数据；可适当增大请求间隔（当前 10s timeout）',
        'long_term': '暂无官方 API，维持 HTML 爬取；若持续触发可考虑 User-Agent 轮换或添加 Cookie',
    },
    'dcinside_game': {
        'display_name': 'DC Inside（游戏网络监控）',
        'reason': 'DC Inside 返回非 200，可能为 Cloudflare 拦截或 IP 封禁',
        'short_term': '本次已跳过该游戏的韩国区数据',
        'long_term': '考虑接入 DC Inside 搜索功能或使用 Playwright 无头浏览器替代 requests',
    },
    'detector404': {
        'display_name': 'detector404.ru（俄罗斯版 Downdetector）',
        'reason': '请求频率触发 detector404.ru 频控（429），或 IP 被临时封禁',
        'short_term': '当前批量请求间已有 1-3s 随机延迟；可将延迟上调至 5-10s 进一步降低触发率',
        'long_term': '注册 detector404.ru 官方账号并获取 API Token，接入官方 REST API（数据质量更高、无频控风险）',
    },
    'vk_game': {
        'display_name': 'VK 移动版（游戏网络监控）',
        'reason': 'VK 移动版对未登录爬虫有严格频控，返回非 200',
        'short_term': '本次已跳过该游戏的 VK 数据，其他数据源（Reddit / detector404）不受影响',
        'long_term': '注册 VK 开发者账号并获取 Service Token，接入 VK API（官方，免费，无频控限制）',
    },
    'vk_brand': {
        'display_name': 'VK 移动版（品牌舆情监控）',
        'reason': 'VK 移动版对未登录爬虫有严格频控，返回非 200',
        'short_term': '本次已跳过 VK 品牌舆情数据，Otzovik 数据不受影响',
        'long_term': '注册 VK 开发者账号并获取 Service Token，接入 VK API（官方，免费）',
    },
    'otzovik': {
        'display_name': 'Otzovik（俄语产品评价）',
        'reason': 'Otzovik 返回非 200，可能有基础反爬或暂时不可用',
        'short_term': '本次已跳过 Otzovik 数据；可尝试增大请求间隔至 3-5s 或更换 User-Agent',
        'long_term': 'Otzovik 暂无官方 API，继续 HTML 爬取；若频繁拦截可考虑搜索引擎间接索引',
    },
    'cloudflare_pricing': {
        'display_name': '竞品定价页（Cloudflare 防护）',
        'reason': 'Cloudflare 规则更新，cloudscraper 指纹被识别，返回 HTTP 403',
        'short_term': '本次已跳过该地区定价数据，下次运行通常可自动恢复；可尝试 pip install -U cloudscraper 更新版本',
        'long_term': '考虑使用 Playwright + playwright-stealth 真实浏览器方案替代 cloudscraper',
    },
    'trustpilot': {
        'display_name': 'Trustpilot（品牌评分监控）',
        'reason': 'Trustpilot 启用了 Cloudflare 保护 + JS 渲染，requests 被拦截，返回非 200',
        'short_term': '本次无 Trustpilot 评分数据，快照未更新',
        'long_term': '申请 Trustpilot Business API（官方接口，数据最准确，无反爬风险）',
    },
    'naver_api_401': {
        'display_name': 'Naver Search Open API（认证失败）',
        'reason': 'API 返回 HTTP 401，Client ID 或 Client Secret 失效/配置错误',
        'short_term': '⚠️ 立即检查 GitHub Secrets 中 NAVER_CLIENT_ID 和 NAVER_CLIENT_SECRET 是否正确填写',
        'long_term': '如 Key 已过期，重新访问 https://developers.naver.com/apps 申请或重置应用凭证',
    },
    'naver_api_other': {
        'display_name': 'Naver Search Open API（请求异常）',
        'reason': 'API 返回非 200/401 状态，可能为配额超限（25,000次/天）或 Naver 服务波动',
        'short_term': '本次已跳过 Naver 数据，DC Inside 搜索数据不受影响',
        'long_term': 'Naver 免费配额 25,000次/天，日常使用通常不会超限；若持续出现请检查 Naver 开发者后台配额用量',
    },
}

def send_popo_alert(webhook_url, issues_list):
    """
    将问题列表格式化为纯文本，并发送至 NetEase POPO Webhook。
    支持按 alert_type 分组输出不同标题的报警。
    为了减少打扰，如果 issues_list 为空，直接静默退出。
    """
    if not issues_list:
        print("未检测到异常或情报，静默退出，不发送打扰信息。")
        return

    current_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    # 按 alert_type 分组
    ALERT_TITLES = {
        'game_monitor': '【全球监控商机雷达警报】',
        'new_game_release': '【新游上线预告】',
        'game_update': '【热游版本更新预告】',
        'game_calendar': '【新游上线/热游更新预告】',
        'platform_status': '【平台与通讯工具状态警报】',
        'brand_monitor': '【品牌舆情监控报告】',
        'competitor_radar': '【竞品情报警报】',
    }

    groups = {}
    for item in issues_list:
        alert_type = item.get('alert_type', 'game_monitor')
        if alert_type not in groups:
            groups[alert_type] = []
        groups[alert_type].append(item)

    # 构造极简纯文本格式
    plain_content = ""
    for alert_type, items in groups.items():
        title = ALERT_TITLES.get(alert_type, '【监控警报】')
        plain_content += f"{title}\n时间: {current_time}\n\n"

        for item in items:
            # 去掉 issue 中可能包含的粗体和红灯 emoji
            clean_issue = item['issue'].replace('**', '').replace('__', '')

            plain_content += f"[{item['game']}]\n"

            # 新游上线/热游更新不显示"地区: Global"（issue 内已有头部地区信息）
            if alert_type not in ('new_game_release', 'game_update'):
                region_display = f"{item['region']} ({item['country']})" if item.get('country') else item['region']
                plain_content += f"地区: {region_display}\n"

            plain_content += f"情报: {clean_issue}\n"

            if item.get('source_url'):
                plain_content += f"来源: {item['source_name']} ({item['source_url']})\n"
            else:
                plain_content += f"来源: {item['source_name']}\n"

            plain_content += "-" * 30 + "\n"

        plain_content += "\n"

    headers = {'Content-Type': 'application/json'}
    payload = {
        "message": plain_content
    }
    
    if not webhook_url:
        print("未配置 POPO_WEBHOOK_URL，控制台输出结果如下：\n")
        print(plain_content)
        return

    # 消息长度限制：超过 4000 字符自动分割发送
    MAX_LEN = 4000
    if len(plain_content) <= MAX_LEN:
        chunks = [plain_content]
    else:
        chunks = []
        lines = plain_content.split('\n')
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > MAX_LEN:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)

    headers = {'Content-Type': 'application/json'}

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"({i+1}/{len(chunks)})\n{chunk}"

        payload = {"message": chunk}

        # 重试 3 次，指数退避
        for attempt in range(3):
            try:
                response = requests.post(
                    webhook_url, headers=headers,
                    data=json.dumps(payload), timeout=10
                )
                print(f"POPO 接口返回 HTTP 状态码: {response.status_code}")
                response.raise_for_status()
                print(f"代码执行：成功发送请求至 POPO Webhook{f' (分片 {i+1}/{len(chunks)})' if len(chunks) > 1 else ''}。")
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    print(f"发送 POPO 警报失败 (第 {attempt+1} 次)，{wait} 秒后重试: {e}")
                    import time
                    time.sleep(wait)
                else:
                    print(f"发送 POPO 警报最终失败: {e}")


def report_scrape_block(source_key: str, url: str = '', status_code: int = None):
    """
    登记一次反爬拦截事件。同一 source_key 在一次运行内会被合并。
    在脚本末尾调用 flush_scrape_block_alerts() 统一发送。

    :param source_key: 数据源标识，对应 _SCRAPE_ADVICE 中的 key
    :param url:        被拦截的 URL（可选，便于排查）
    :param status_code: HTTP 状态码（可选）
    """
    if source_key not in _scrape_block_registry:
        _scrape_block_registry[source_key] = {
            'count': 0,
            'urls': [],
            'codes': set(),
        }
    entry = _scrape_block_registry[source_key]
    entry['count'] += 1
    if url and url not in entry['urls']:
        entry['urls'].append(url)
    if status_code is not None:
        entry['codes'].add(status_code)

    # 同时打印到控制台，方便 Actions 日志排查
    advice = _SCRAPE_ADVICE.get(source_key, {})
    display = advice.get('display_name', source_key)
    code_str = f" HTTP {status_code}" if status_code else ""
    print(f"[反爬拦截] {display}{code_str}: {url[:80] if url else '(无 URL)'} "
          f"（本次运行第 {entry['count']} 次，将在脚本结束时合并发送 POPO）")


def flush_scrape_block_alerts(webhook_url: str = None):
    """
    将本次运行中所有登记的反爬拦截事件格式化后发送 POPO，然后清空 registry。
    每个数据源合并为一条，多个数据源拼在同一条消息里发出。
    若没有任何拦截事件，静默退出。

    建议在每个监控脚本的 main() / if __name__ == '__main__' 末尾调用。
    """
    if not _scrape_block_registry:
        return  # 本次运行无拦截事件，静默退出

    effective_url = webhook_url or POPO_WEBHOOK_URL
    current_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    lines = [f"【监控系统警告 — 数据源被拦截】\n时间: {current_time} (UTC+8)\n"]

    for source_key, entry in _scrape_block_registry.items():
        advice = _SCRAPE_ADVICE.get(source_key, {})
        display_name = advice.get('display_name', source_key)
        reason      = advice.get('reason', '未知原因')
        short_term  = advice.get('short_term', '暂无建议')
        long_term   = advice.get('long_term', '暂无建议')

        # 根据实际 HTTP 状态码动态覆盖原因描述和建议
        # 404 = URL 失效/slug 不匹配（非反爬）；403/429 = 真正的反爬拦截
        actual_codes = entry.get('codes', set())
        all_404 = actual_codes and all(c == 404 for c in actual_codes)
        has_anti_scrape = any(c in (403, 429) for c in actual_codes)

        if all_404:
            reason = 'URL 返回 404（页面不存在），数据源的 URL slug 或板块 ID 可能已失效/变更'
            short_term = '本次已跳过该数据源；需排查并更新失效的 URL 路径或板块 ID'
            long_term = '定期验证数据源 URL 可达性，或改用官方 API 避免路径变更导致的数据盲区'
        elif has_anti_scrape and not all_404:
            pass  # 保持 _SCRAPE_ADVICE 中的原始反爬描述

        count = entry['count']
        codes = ', '.join(str(c) for c in sorted(entry['codes'])) if entry['codes'] else '未知'
        # 最多显示 2 个 URL，超出时显示省略
        url_list = entry['urls']
        if url_list:
            url_display = url_list[0][:100]
            if len(url_list) > 1:
                url_display += f'  （等共 {len(url_list)} 个 URL）'
        else:
            url_display = '（无记录）'

        block = (
            f"数据源: {display_name}\n"
            f"本次触发次数: {count} 次（已合并）\n"
            f"HTTP 状态码: {codes}\n"
            f"触发 URL 示例: {url_display}\n"
            f"\n"
            f"原因判断: {reason}\n"
            f"\n"
            f"应对建议:\n"
            f"  1. {short_term}\n"
            f"  2. {long_term}\n"
            f"{'─' * 35}\n"
        )
        lines.append(block)

    lines.append("如频繁出现此警告，请及时处理以免监控盲区扩大。")
    content = '\n'.join(lines)

    print(f"\n[反爬汇总] 本次运行共检测到 {len(_scrape_block_registry)} 个数据源被拦截，正在发送 POPO 警告...")

    if not effective_url:
        print("未配置 POPO_WEBHOOK_URL，反爬警告内容如下：\n")
        print(content)
        _scrape_block_registry.clear()
        return

    # 复用现有的分片+重试逻辑
    import time as _time
    MAX_LEN = 4000
    chunks = []
    if len(content) <= MAX_LEN:
        chunks = [content]
    else:
        current = ""
        for line in content.split('\n'):
            if len(current) + len(line) + 1 > MAX_LEN:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)

    headers = {'Content-Type': 'application/json'}
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"({i+1}/{len(chunks)})\n{chunk}"
        payload = {"message": chunk}
        for attempt in range(3):
            try:
                resp = requests.post(effective_url, headers=headers,
                                     data=json.dumps(payload), timeout=10)
                resp.raise_for_status()
                print(f"[反爬汇总] POPO 反爬警告发送成功{f' (分片 {i+1}/{len(chunks)})' if len(chunks) > 1 else ''}。")
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    print(f"[反爬汇总] 发送失败 (第 {attempt+1} 次)，{wait} 秒后重试: {e}")
                    _time.sleep(wait)
                else:
                    print(f"[反爬汇总] 发送最终失败: {e}")

    _scrape_block_registry.clear()

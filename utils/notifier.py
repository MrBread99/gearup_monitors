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

# ==========================================
# 内部崩溃感知系统
# ==========================================
# 监控脚本内部的 try/except 捕获到异常时调用 report_monitor_crash() 登记，
# 在脚本末尾统一调用 flush_monitor_crash_alerts() 发送。
# 解决"脚本内部崩溃但静默吞掉、无人感知"的问题。
# ==========================================

# 每次运行的崩溃事件累积池
# 格式: [{'step': str, 'error': str, 'traceback': str}]
_crash_registry: list = []


def report_monitor_crash(step_name: str, error: Exception):
    """
    登记一次监控步骤内部崩溃。
    在 try/except 的 except 块中调用，脚本末尾由 flush_monitor_crash_alerts() 统一发送。

    :param step_name: 崩溃的步骤名称，如 "detector404 批量检测"、"Trustpilot 舆情"
    :param error: 捕获到的异常对象
    """
    import traceback as tb
    tb_str = tb.format_exc()
    # 只保留最后 5 行 traceback，避免消息过长
    tb_lines = tb_str.strip().split('\n')
    short_tb = '\n'.join(tb_lines[-5:]) if len(tb_lines) > 5 else tb_str.strip()

    _crash_registry.append({
        'step': step_name,
        'error': str(error),
        'traceback': short_tb,
    })
    print(f"[内部崩溃] {step_name}: {error}")


def flush_monitor_crash_alerts(webhook_url=None):
    """
    将本次运行中所有登记的内部崩溃事件格式化后发送 POPO，然后清空 registry。
    若没有任何崩溃事件，静默退出。

    建议在每个入口脚本的 main() 末尾或 finally 块中调用。
    """
    if not _crash_registry:
        return

    effective_url = webhook_url or POPO_WEBHOOK_URL
    current_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"【监控系统警告 — 内部崩溃】\n"
        f"时间: {current_time} (UTC+8)\n"
        f"本次运行共 {len(_crash_registry)} 个步骤发生异常:\n"
    ]

    for i, crash in enumerate(_crash_registry, 1):
        block = (
            f"[{i}] {crash['step']}\n"
            f"    异常: {crash['error']}\n"
            f"    堆栈:\n"
        )
        for tb_line in crash['traceback'].split('\n'):
            block += f"      {tb_line}\n"
        block += f"{'─' * 35}\n"
        lines.append(block)

    lines.append(
        "以上步骤在本次运行中被 try/except 捕获后跳过，未影响其他步骤，但该步骤的监控数据本次缺失。\n"
        "请尽快排查修复，避免监控盲区持续扩大。"
    )
    content = '\n'.join(lines)

    print(f"\n[内部崩溃汇总] 本次运行共 {len(_crash_registry)} 个步骤崩溃，正在发送 POPO 警告...")

    if not effective_url:
        print("未配置 POPO_WEBHOOK_URL，崩溃警告内容如下：\n")
        print(content)
        _crash_registry.clear()
        return

    import time as _time
    headers = {'Content-Type': 'application/json'}

    # 分片发送（复用现有逻辑）
    MAX_LEN = 4000
    if len(content) <= MAX_LEN:
        chunks = [content]
    else:
        chunks = []
        current = ""
        for line in content.split('\n'):
            if len(current) + len(line) + 1 > MAX_LEN:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)

    for ci, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"({ci+1}/{len(chunks)})\n{chunk}"
        payload = {"message": chunk}
        for attempt in range(3):
            try:
                resp = requests.post(effective_url, headers=headers,
                                     data=json.dumps(payload), timeout=10)
                resp.raise_for_status()
                print(f"[内部崩溃] POPO 崩溃警告发送成功。")
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    print(f"[内部崩溃] 发送失败 (第 {attempt+1} 次)，{wait} 秒后重试: {e}")
                    _time.sleep(wait)
                else:
                    print(f"[内部崩溃] 发送最终失败: {e}")

    _crash_registry.clear()

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
    # 注：Otzovik 条目已移除 —— 原 search_otzovik() 已替换为 Google 俄语间接索引，
    #     不再直连 otzovik.com，不会再触发 report_scrape_block('otzovik')。
    'cloudflare_pricing': {
        'display_name': '竞品定价页（Cloudflare 防护）',
        'reason': 'Playwright + stealth 已自动重建 context 重试一次，且后续 fallback 仍未拿到页面，说明该 URL 当前被 Cloudflare 持续拦截',
        'short_term': '本次已跳过该地区定价数据；若仅 1-2 个 URL 偶发触发，通常属于正常波动，下次运行可自动恢复',
        'long_term': '若持续大面积 403，优先升级 Chromium / playwright-stealth 版本；仍无改善时再考虑代理 IP 轮换',
        'min_notify_count': 2,
    },
    'trustpilot': {
        'display_name': 'Trustpilot（品牌评分监控）',
        'reason': 'Playwright + stealth 等待 Cloudflare challenge 解除后仍未获取到页面内容，requests fallback 同样被拦截',
        'short_term': '本次无 Trustpilot 评分数据，快照未更新；少量运行失败属正常波动',
        'long_term': '若持续失败，考虑升级 Chromium 版本、调整 wait_selector，或申请 Trustpilot Business API',
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
    'dcinside_brand': {
        'display_name': 'DC Inside（品牌舆情搜索）',
        'reason': 'DC Inside 全站搜索接口返回非 200，可能为 Cloudflare 拦截、429 频控或接口路径变更',
        'short_term': '本次已跳过 DC Inside 品牌舆情数据，Naver 数据不受影响',
        'long_term': '暂无官方搜索 API；可增大请求间隔或与游戏监控 dcinside_game 合并使用 Playwright 方案',
    },
    'itsd': {
        'display_name': 'IsTheServiceDown（故障聚合监控）',
        'reason': 'IsTheServiceDown 返回非 200，可能为 CI 固定 IP 被限速（429）或网站暂时不可用',
        'short_term': '本次已跳过该游戏的 ITSD 故障聚合数据；等待下次运行自动重试',
        'long_term': '暂无官方 API；若频繁出现可考虑增加请求间隔或切换至备用故障聚合源',
    },
    'steam_news_api': {
        'display_name': 'Steam News API（热游更新监控）',
        'reason': 'Steam News API 返回非 200，本次无法获取该游戏的官方新闻更新',
        'short_term': '本次已跳过对应游戏的 Steam News 更新检测；等待下次运行自动重试',
        'long_term': '如持续出现，可检查 Steam API 可用性并增加备用更新源',
    },
    'steam_featured': {
        'display_name': 'Steam Featured Categories API（新游/Coming Soon）',
        'reason': 'Steam Featured Categories API 返回非 200，本次无法获取热门新游或即将发售列表',
        'short_term': '本次已跳过 Steam 热门新游或 Coming Soon 检测；等待下次运行自动重试',
        'long_term': '如持续出现，可考虑增加 Steam 页面解析兜底或拉长重试间隔',
    },
    'steam_appdetails': {
        'display_name': 'Steam AppDetails API（游戏详情）',
        'reason': 'Steam AppDetails API 返回非 200，本次无法补充游戏联机标签和发布日期',
        'short_term': '本次已跳过对应游戏的详情补充，不影响其他游戏继续扫描',
        'long_term': '如持续出现，可增加重试或缓存最近一次成功拉取的详情数据',
    },
    'official_patch_page': {
        'display_name': '官方 Patch Notes 页面',
        'reason': '游戏官方更新页返回非 200，本次无法确认最新补丁/赛季公告',
        'short_term': '本次已跳过对应官方页面检查；等待下次运行自动重试',
        'long_term': '如持续出现，可检查页面路径是否改版，或替换为更稳定的官方 API / RSS',
    },
    'hoyolab_api': {
        'display_name': 'HoyoLab 官方 API',
        'reason': 'HoyoLab API 返回非 200，本次无法获取米哈游系游戏官方更新公告',
        'short_term': '本次已跳过原神/崩铁/绝区零的 HoyoLab 更新检测；等待下次运行自动重试',
        'long_term': '如持续出现，可检查 HoyoLab API 路径是否变更，并考虑增加官网公告页兜底',
    },
    'reddit_game_calendar': {
        'display_name': 'Reddit（新游/热游日历监控）',
        'reason': 'Reddit subreddit listing 接口返回非 200，本次无法获取部分新游/热游预警帖子',
        'short_term': '本次已跳过对应 subreddit 的 listing 抓取；等待下次运行自动重试',
        'long_term': '如持续出现，可检查 Reddit API 凭证、限频情况，或为关键来源增加备用站点',
    },
    'reddit_game_calendar_missing_credentials': {
        'display_name': 'Reddit（新游/热游日历监控，缺少凭证）',
        'reason': 'GitHub Actions 未提供 REDDIT_CLIENT_ID 或 REDDIT_CLIENT_SECRET，当前只能匿名访问 Reddit，容易被 403 拒绝',
        'short_term': '请立即检查 GitHub Secrets 中 REDDIT_CLIENT_ID 和 REDDIT_CLIENT_SECRET 是否已配置且名称正确',
        'long_term': '保持 Reddit OAuth 凭证长期有效，并在关键 workflow 中统一复用共享客户端',
    },
    'reddit_game_calendar_token_failure': {
        'display_name': 'Reddit（新游/热游日历监控，OAuth 取 token 失败）',
        'reason': 'Reddit OAuth token 获取失败，可能是凭证失效、应用配置错误，或 Reddit token 接口临时异常',
        'short_term': '优先查看 Actions 日志中的 Reddit OAuth2 认证结果，并核对 GitHub Secrets 中的 Reddit 凭证',
        'long_term': '如凭证经常失效，建议重新创建 Reddit script 应用并更新仓库 Secrets',
    },
    'reddit_game_calendar_oauth_403': {
        'display_name': 'Reddit（新游/热游日历监控，OAuth 请求被拒）',
        'reason': '已成功切换到 oauth.reddit.com，但 listing 请求仍返回 403，说明不是匿名抓取问题，而是 Reddit 平台侧对当前请求/应用进行了拒绝',
        'short_term': '优先查看 Actions 日志中的 mode=oauth 与 token_state，确认是否所有请求都稳定带上 Bearer token',
        'long_term': '如持续出现，可检查 Reddit 应用权限、User-Agent 合规性，或为关键来源增加非 Reddit 备用源',
    },
    'reddit_game_calendar_anonymous_403': {
        'display_name': 'Reddit（新游/热游日历监控，匿名访问被拒）',
        'reason': '当前请求未走 OAuth，直接访问 Reddit listing 被 403 拒绝，通常意味着凭证未生效或 token 获取失败后退回到了匿名模式',
        'short_term': '优先检查 Actions 日志中是否出现 “OAuth2 认证成功”；若没有，请先修复 Reddit Secrets',
        'long_term': '避免依赖匿名访问 Reddit，在所有日历监控链路中统一强制使用 OAuth 模式',
    },
    'youtube_quota': {
        'display_name': 'YouTube Data API v3（配额耗尽）',
        'reason': 'YouTube API 返回 403 quotaExceeded，当日 10,000 单位免费配额已耗尽（search 操作每次消耗 100 单位）',
        'short_term': '本次已跳过剩余搜索词；配额将在 UTC 00:00 自动重置，下次运行恢复正常',
        'long_term': '当前 10 个搜索词 × 100 = 1,000 单位/次，每天跑 10 次会耗尽；可在 Google Cloud Console 申请提升配额，或减少搜索词数量',
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


def has_scrape_block_alerts() -> bool:
    """返回本次运行中是否登记过数据源异常。"""
    return bool(_scrape_block_registry)


def send_system_heartbeat(webhook_url: str, task_name: str, summary: str):
    """
    发送低噪音系统心跳，用于确认定时任务确实执行过。
    仅建议给每天 1 次的聚合任务使用，避免高频刷屏。
    """
    current_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    content = (
        f"【监控系统心跳】\n"
        f"时间: {current_time} (UTC+8)\n\n"
        f"任务: {task_name}\n"
        f"状态: 本次定时任务已正常执行\n"
        f"结果: {summary}\n"
    )

    if not webhook_url:
        print("未配置 POPO_WEBHOOK_URL，系统心跳内容如下：\n")
        print(content)
        return

    headers = {'Content-Type': 'application/json'}
    payload = {"message": content}

    import time as _time
    for attempt in range(3):
        try:
            response = requests.post(
                webhook_url, headers=headers,
                data=json.dumps(payload), timeout=10
            )
            response.raise_for_status()
            print(f"[系统心跳] {task_name} 心跳发送成功。")
            break
        except Exception as e:
            if attempt < 2:
                wait = 2 ** (attempt + 1)
                print(f"[系统心跳] 发送失败 (第 {attempt+1} 次)，{wait} 秒后重试: {e}")
                _time.sleep(wait)
            else:
                print(f"[系统心跳] 发送最终失败: {e}")


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
    print(f"[数据源异常] {display}{code_str}: {url[:80] if url else '(无 URL)'} "
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

    lines = [f"【数据源异常】{current_time} (UTC+8)\n"]

    for source_key, entry in _scrape_block_registry.items():
        advice = _SCRAPE_ADVICE.get(source_key, {})
        display_name = advice.get('display_name', source_key)
        reason      = advice.get('reason', '未知原因')
        short_term  = advice.get('short_term', '暂无建议')
        long_term   = advice.get('long_term', '暂无建议')
        min_notify_count = int(advice.get('min_notify_count', 1) or 1)

        # 根据实际 HTTP 状态码动态覆盖原因描述和建议
        # 仅对没有专属建议的数据源做泛化覆盖（有专属条目的优先用人工维护的描述）
        # 404         = URL 失效/slug 不匹配（非反爬）
        # 403/429/507 = 真正的反爬拦截
        # 5xx (≥500)  = 数据源服务端故障（与爬虫无关）
        has_custom_advice = source_key in _SCRAPE_ADVICE
        actual_codes = entry.get('codes', set())
        all_404 = actual_codes and all(c == 404 for c in actual_codes)
        has_anti_scrape = any(c in (403, 429, 507) for c in actual_codes)
        all_5xx = actual_codes and all(c >= 500 for c in actual_codes)
        has_5xx = any(c >= 500 for c in actual_codes)

        # 404 / 5xx 属于客观状态码语义，优先覆盖静态文案，避免把 500 误解释为 429/反爬。
        if all_404:
            reason = 'URL 返回 404（页面不存在），数据源的 URL slug 或板块 ID 可能已失效/变更'
            short_term = '本次已跳过该数据源；需排查并更新失效的 URL 路径或板块 ID'
            long_term = '定期验证数据源 URL 可达性，或改用官方 API 避免路径变更导致的数据盲区'
        elif all_5xx:
            codes_str = ', '.join(str(c) for c in sorted(actual_codes))
            reason = f'数据源服务端返回 {codes_str}，属于对方服务器临时故障，与爬虫频率或 IP 无关'
            short_term = '本次已跳过该数据源；此类错误通常自动恢复，等待下次运行即可'
            long_term = '若 5xx 持续出现（连续多次运行），可检查该数据源官网是否停服或迁移'
        elif has_5xx and not has_anti_scrape:
            # 混有 5xx 但无 403/429 —— 以 5xx 为主
            codes_str = ', '.join(str(c) for c in sorted(actual_codes))
            reason = f'数据源返回 {codes_str}，包含服务端故障（5xx），与反爬无关'
            short_term = '本次已跳过该数据源；等待下次运行自动重试'
            long_term = '若 5xx 持续出现，排查数据源官网可用性'
        elif has_custom_advice:
            pass  # 保持 _SCRAPE_ADVICE 中人工维护的专属描述
        elif has_anti_scrape:
            pass  # 保持 _SCRAPE_ADVICE 中的原始反爬描述

        count = entry['count']
        if count < min_notify_count:
            print(f"[数据源异常] {display_name} 本次仅触发 {count} 次，低于通知阈值 {min_notify_count}，仅保留日志不发 POPO。")
            continue

        codes = ', '.join(str(c) for c in sorted(entry['codes'])) if entry['codes'] else '未知'
        # URL 只显示域名部分，精简展示
        url_list = entry['urls']
        if url_list:
            from urllib.parse import urlparse
            domain = urlparse(url_list[0]).netloc or url_list[0][:40]
            url_display = f"{domain} 等{len(url_list)}个URL" if len(url_list) > 1 else domain
        else:
            url_display = ''

        url_part = f" | {url_display}" if url_display else ""
        block = (
            f"[{display_name}] {codes} ×{count}{url_part}\n"
            f"  原因: {reason}\n"
            f"  建议: {long_term}\n"
            f"{'─' * 20}\n"
        )
        lines.append(block)

    if len(lines) == 1:
        return

    content = '\n'.join(lines)

    print(f"\n[数据源异常汇总] 本次运行共检测到 {len(_scrape_block_registry)} 个数据源异常，正在发送 POPO 警告...")

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

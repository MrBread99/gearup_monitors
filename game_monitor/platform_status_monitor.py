import requests
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# 通讯与游戏平台全球连接状态监控
# ==========================================
# 监控目标:
# 1. Discord — 官方 Status API，分区域 Voice 服务器状态（含俄罗斯）
# 2. Telegram — 无官方 API，通过 Reddit/社区间接监控
# 3. Steam — steamstat.us API 获取 Steam CM 和 Store 状态
# 4. Epic Games — 官方 Status API，含 Fortnite/Rocket League 等
# 5. Battle.net — IsTheServiceDown 间接监控
#
# 重点关注：
# - Discord/Telegram 在俄罗斯的连接问题（加速器刚需）
# - Steam/Epic 在全球的连接故障（影响所有游戏）
# ==========================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/2.1'
}

# Discord Voice 服务器区域映射（关注的重点区域）
DISCORD_VOICE_REGIONS = {
    'ccgfj3l84lvt': 'Russia',
    'xggnf9hnngkt': 'Japan',
    'q0lbnfc59j35': 'Singapore',
    '0ysw0jy8hnsr': 'Hong Kong',
    'tl31gd6tc86r': 'India',
    'sg02vq1rbfrr': 'Brazil',
    'qk867vbbh84x': 'South Korea',
    'qbt7ryjc5tcd': 'Sydney',
    'b5v9r9bdppvm': 'South Africa',
    'fc8y53dfg85y': 'Rotterdam',
    'gqhmm9t47wcw': 'Atlanta',
    'nhlpbmmcffcl': 'US Central',
    'kdz8bp5dp08v': 'US East',
    'gmppldfdghcd': 'US South',
    '334vzyzzwlfs': 'US West',
}

# Discord 核心服务组件
DISCORD_CORE_COMPONENTS = {
    'rhznvxg4v7yh': 'API',
    'x7rnz0t7dpnp': 'Gateway',
    '354mn7xfxz1h': 'Push Notifications',
    '3y468xdr1st2': 'Search',
    'r3wq1zsx72bz': 'Media Proxy',
}


def check_discord_status():
    """
    检查 Discord 官方 Status API。
    重点关注：俄罗斯 Voice 服务器、全局 API/Gateway 状态、活跃事件。
    """
    issues = []
    url = "https://discordstatus.com/api/v2/summary.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[Discord] HTTP {response.status_code}")
            return issues

        data = response.json()
        components = {c['id']: c for c in data.get('components', [])}

        # 1. 检查 Voice 服务器区域状态
        degraded_regions = []
        for comp_id, region_name in DISCORD_VOICE_REGIONS.items():
            comp = components.get(comp_id)
            if comp and comp['status'] != 'operational':
                status = comp['status'].replace('_', ' ').title()
                degraded_regions.append(f"{region_name}: {status}")

        if degraded_regions:
            # 俄罗斯特殊标注
            russia_affected = any('Russia' in r for r in degraded_regions)
            prefix = "🚨 [俄罗斯受影响] " if russia_affected else ""
            issues.append({
                'game': 'Discord',
                'region': 'Global',
                'country': '',
                'issue': f"{prefix}⚡ Discord Voice 服务器异常: {', '.join(degraded_regions)}",
                'source_name': 'Discord Status API',
                'source_url': 'https://discordstatus.com/'
            })

        # 2. 检查核心服务状态
        degraded_core = []
        for comp_id, service_name in DISCORD_CORE_COMPONENTS.items():
            comp = components.get(comp_id)
            if comp and comp['status'] != 'operational':
                status = comp['status'].replace('_', ' ').title()
                degraded_core.append(f"{service_name}: {status}")

        if degraded_core:
            issues.append({
                'game': 'Discord',
                'region': 'Global',
                'country': '',
                'issue': f"⚡ Discord 核心服务异常: {', '.join(degraded_core)}",
                'source_name': 'Discord Status API',
                'source_url': 'https://discordstatus.com/'
            })

        # 3. 检查活跃事件 (incidents)
        incidents = data.get('incidents', [])
        for incident in incidents:
            if incident.get('status') not in ('resolved', 'postmortem'):
                impact = incident.get('impact', 'none')
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Discord',
                    'region': 'Global',
                    'country': '',
                    'issue': f"🔴 Discord 事件 [{impact}]: {name} (状态: {status})",
                    'source_name': 'Discord Status API',
                    'source_url': incident.get('shortlink', 'https://discordstatus.com/')
                })

    except Exception as e:
        print(f"[Discord] 检测失败: {e}")

    return issues


def check_telegram_russia():
    """
    通过 Reddit 搜索监控 Telegram 在俄罗斯/独联体的连接问题。
    Telegram 没有官方 Status API，社区报告是最佳间接信号。
    """
    issues = []
    queries = [
        "Telegram down Russia",
        "Telegram blocked Russia",
        "Telegram не работает",   # 俄语：Telegram 不工作
        "телеграм не работает",   # 俄语：telegram 不工作
    ]

    total_complaints = 0

    for query in queries:
        encoded = requests.utils.quote(query)
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={encoded}&sort=new&t=day&limit=25"
        )
        try:
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                children = data.get('data', {}).get('children', [])
                total_complaints += len(children)
            elif response.status_code == 429:
                break
        except Exception:
            pass

    if total_complaints >= 3:
        issues.append({
            'game': 'Telegram',
            'region': 'Russia / CIS',
            'country': 'Russia',
            'issue': f"🚨 Telegram 连接问题: 过去 24h 在 Reddit 发现 {total_complaints} 条相关讨论，疑似俄罗斯/CIS 区域封锁或干扰",
            'source_name': 'Reddit Search',
            'source_url': 'https://www.reddit.com/search/?q=telegram+down+russia&sort=new&t=day'
        })

    return issues


def check_steam_status():
    """
    通过 Steam 官方 Web API 和 steamstat.us 检查 Steam 平台全球状态。
    """
    issues = []

    # 方案 1: Steam Web API 检查 CM 服务器
    try:
        url = "https://api.steampowered.com/ICSGOServers_730/GetGameServersStatus/v1/?key=anonymous"
        # 退化方案：使用 steamstat.us 的非官方 API
        url = "https://crowbar.steamstat.us/gravity.json"
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # steamstat.us 返回各服务的状态
            services = data.get('services', data) if isinstance(data, dict) else {}

            degraded = []
            for service_name, service_data in services.items():
                if isinstance(service_data, dict):
                    status = service_data.get('status', 'normal')
                    if status not in ('normal', 'good', 'operational'):
                        title = service_data.get('title', service_name)
                        degraded.append(f"{title}: {status}")

            if degraded:
                issues.append({
                    'game': 'Steam',
                    'region': 'Global',
                    'country': '',
                    'issue': f"⚡ Steam 平台异常: {', '.join(degraded[:5])}",
                    'source_name': 'steamstat.us',
                    'source_url': 'https://steamstat.us/'
                })
    except Exception as e:
        print(f"[Steam] steamstat.us 检测失败: {e}")

    # 方案 2: Reddit 辅助检测
    try:
        url = (
            "https://www.reddit.com/r/Steam/search.json"
            "?q=steam+down+OR+steam+not+working+OR+cant+connect&restrict_sr=on&sort=new&t=day&limit=25"
        )
        response = requests.get(
            url,
            headers={'User-Agent': 'OSINT-Monitor/2.1'},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            if len(posts) >= 10:  # 10 条以上才报警（Steam 社区吐槽量大）
                issues.append({
                    'game': 'Steam',
                    'region': 'Global',
                    'country': '',
                    'issue': f"📊 Steam 社区异常讨论激增: 过去 24h 有 {len(posts)} 条连接问题帖子",
                    'source_name': 'r/Steam',
                    'source_url': 'https://www.reddit.com/r/Steam/search?q=steam+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_epic_platform_status():
    """
    检查 Epic Games 平台整体状态（不只是 Fortnite，而是 EGS 全平台）。
    """
    issues = []
    url = "https://status.epicgames.com/api/v2/summary.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return issues

        data = response.json()
        components = data.get('components', [])

        # 关注 Epic Games Store 和 Epic Online Services 的顶层状态
        egs_issues = []
        for comp in components:
            if comp.get('group', False):  # 只看顶层 group
                name = comp.get('name', '')
                status = comp.get('status', 'operational')
                if status != 'operational' and name in [
                    'Epic Games Store', 'Epic Online Services',
                    'Rocket League', 'Fall Guys'
                ]:
                    egs_issues.append(
                        f"{name}: {status.replace('_', ' ').title()}"
                    )

        if egs_issues:
            issues.append({
                'game': 'Epic Games',
                'region': 'Global',
                'country': '',
                'issue': f"⚡ Epic 平台异常: {', '.join(egs_issues)}",
                'source_name': 'Epic Status API',
                'source_url': 'https://status.epicgames.com/'
            })

        # 检查活跃事件
        incidents = data.get('incidents', [])
        for incident in incidents:
            if incident.get('status') not in ('resolved', 'postmortem'):
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Epic Games',
                    'region': 'Global',
                    'country': '',
                    'issue': f"🔴 Epic 事件: {name} (状态: {status})",
                    'source_name': 'Epic Status API',
                    'source_url': 'https://status.epicgames.com/'
                })

    except Exception as e:
        print(f"[Epic] 检测失败: {e}")

    return issues


def check_battlenet_status():
    """
    通过 Reddit 搜索间接监控 Battle.net 连接状态。
    Battle.net 没有公开的 Status API。
    """
    issues = []
    try:
        url = (
            "https://www.reddit.com/search.json"
            "?q=battle.net+down+OR+battlenet+down+OR+blizzard+servers+down&sort=new&t=day&limit=25"
        )
        response = requests.get(
            url,
            headers={'User-Agent': 'OSINT-Monitor/2.1'},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            if len(posts) >= 5:
                issues.append({
                    'game': 'Battle.net',
                    'region': 'Global',
                    'country': '',
                    'issue': f"📊 Battle.net 连接问题讨论激增: 过去 24h 有 {len(posts)} 条相关帖子",
                    'source_name': 'Reddit Search',
                    'source_url': 'https://www.reddit.com/search/?q=battle.net+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_all_platforms():
    """主检测函数：检查所有平台状态"""
    all_issues = []

    print("正在检测 Discord 全球状态...")
    all_issues.extend(check_discord_status())

    print("正在检测 Telegram 俄罗斯连接状态...")
    all_issues.extend(check_telegram_russia())

    print("正在检测 Steam 全球状态...")
    all_issues.extend(check_steam_status())

    print("正在检测 Epic Games 平台状态...")
    all_issues.extend(check_epic_platform_status())

    print("正在检测 Battle.net 状态...")
    all_issues.extend(check_battlenet_status())

    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Platform Status Monitor...")
    results = check_all_platforms()
    if results:
        for r in results:
            print(f"[{r['game']}] {r['issue']}")
        # 发送通知
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("所有平台运行正常。")

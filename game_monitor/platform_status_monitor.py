import requests
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get

# ==========================================
# 通讯与游戏平台全球连接状态监控
# ==========================================
# 事件 ID 去重：已报过的事件不再重复报警
# ==========================================

INCIDENT_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'platform_incidents_snapshot.json'
)


def _load_seen_incidents():
    if os.path.exists(INCIDENT_SNAPSHOT_FILE):
        try:
            with open(INCIDENT_SNAPSHOT_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_seen_incidents(seen):
    # 只保留最近 200 个，防止无限增长
    recent = list(seen)[-200:]
    with open(INCIDENT_SNAPSHOT_FILE, 'w') as f:
        json.dump(recent, f)


_seen_incidents = _load_seen_incidents()


def _is_new_incident(incident_id):
    """检查事件是否已报过，未报过则标记并返回 True"""
    if incident_id in _seen_incidents:
        return False
    _seen_incidents.add(incident_id)
    return True
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
            # 区域性问题 = 加速器可解决（尤其俄罗斯封锁）
            russia_affected = any('Russia' in r for r in degraded_regions)
            if russia_affected:
                prefix = "🟢 [加速器可解决] 🚨 [俄罗斯受影响] "
            else:
                prefix = "🟡 [待确认] "
            issues.append({
                'game': 'Discord',
                'region': 'Global',
                'country': '',
                'alert_type': 'game_monitor',
                'issue': f"{prefix}Discord Voice 服务器异常: {', '.join(degraded_regions)}",
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
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] Discord 核心服务异常（官方故障）: {', '.join(degraded_core)}",
                'source_name': 'Discord Status API',
                'source_url': 'https://discordstatus.com/'
            })

        # 3. 检查活跃事件 (incidents) — 去重
        incidents = data.get('incidents', [])
        for incident in incidents:
            if incident.get('status') not in ('resolved', 'postmortem'):
                inc_id = f"discord_{incident.get('id', '')}"
                if not _is_new_incident(inc_id):
                    continue
                impact = incident.get('impact', 'none')
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Discord',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Discord 事件 [{impact}]: {name} (状态: {status})",
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
            response = reddit_get(url)
            if response is None:
                continue
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
            'alert_type': 'game_monitor',
            'issue': f"🟢 [加速器可解决] Telegram 连接问题: 过去 24h 在 Reddit 发现 {total_complaints} 条相关讨论，疑似俄罗斯/CIS 区域封锁或干扰",
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
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Steam 平台异常（官方服务故障）: {', '.join(degraded[:5])}",
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
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            if len(posts) >= 10:  # 10 条以上才报警（Steam 社区吐槽量大）
                issues.append({
                    'game': 'Steam',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🟡 [待确认] Steam 社区异常讨论激增: 过去 24h 有 {len(posts)} 条连接问题帖子",
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
                'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Epic 平台异常（官方服务故障）: {', '.join(egs_issues)}",
                'source_name': 'Epic Status API',
                'source_url': 'https://status.epicgames.com/'
            })

        # 检查活跃事件 — 去重
        incidents = data.get('incidents', [])
        for incident in incidents:
            if incident.get('status') not in ('resolved', 'postmortem'):
                inc_id = f"epic_{incident.get('id', '')}"
                if not _is_new_incident(inc_id):
                    continue
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Epic Games',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Epic 事件: {name} (状态: {status})",
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
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            if len(posts) >= 5:
                issues.append({
                    'game': 'Battle.net',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🟡 [待确认] Battle.net 连接问题讨论激增: 过去 24h 有 {len(posts)} 条相关帖子",
                    'source_name': 'Reddit Search',
                    'source_url': 'https://www.reddit.com/search/?q=battle.net+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_faceit_status():
    """
    检查 FACEIT（CS2 第三方对战平台）状态。
    通过 incident.io Status API 检测活跃事件和维护。
    """
    issues = []
    url = "https://www.faceitstatus.com/api/v1/summary"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[FACEIT] HTTP {response.status_code}")
            return issues

        data = response.json()

        # 检查活跃事件 — 去重
        ongoing = data.get('ongoing_incidents', [])
        for incident in ongoing:
            name = incident.get('name', 'Unknown')
            inc_id = f"faceit_{incident.get('id', name)}"
            if not _is_new_incident(inc_id):
                continue
            issues.append({
                'game': 'FACEIT',
                'region': 'Global',
                'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] FACEIT 事件: {name}",
                'source_name': 'FACEIT Status',
                'source_url': 'https://www.faceitstatus.com/'
            })

        # 检查进行中的维护
        in_progress = data.get('in_progress_maintenances', [])
        for maint in in_progress:
            name = maint.get('name', 'Unknown')
            issues.append({
                'game': 'FACEIT',
                'region': 'Global',
                'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] FACEIT 维护中: {name}",
                'source_name': 'FACEIT Status',
                'source_url': 'https://www.faceitstatus.com/'
            })

        # Reddit 辅助检测
        reddit_url = (
            "https://www.reddit.com/r/FACEITcom/search.json"
            "?q=down+OR+servers+OR+not+working+OR+queue&restrict_sr=on&sort=new&t=day&limit=25"
        )
        try:
            reddit_resp = reddit_get(reddit_url)
            if reddit_resp is not None and reddit_resp.status_code == 200:
                posts = reddit_resp.json().get('data', {}).get('children', [])
                if len(posts) >= 5:
                    issues.append({
                        'game': 'FACEIT',
                        'region': 'Global',
                        'country': '',
                        'alert_type': 'game_monitor',
                        'issue': f"🟡 [待确认] FACEIT 社区异常讨论: 过去 24h r/FACEITcom 有 {len(posts)} 条服务问题帖子",
                        'source_name': 'r/FACEITcom',
                        'source_url': 'https://www.reddit.com/r/FACEITcom/'
                    })
        except Exception:
            pass

    except Exception as e:
        print(f"[FACEIT] 检测失败: {e}")

    return issues


def check_riot_status():
    """
    检查 Riot Games 服务状态（Valorant / LOL / TFT 等）。
    通过 Riot CDN Status API 分区域检测活跃事件和维护。
    """
    issues = []

    # Riot 各游戏各区域 Status API
    riot_endpoints = {
        'Valorant': {
            'AP': 'https://valorant.secure.dyn.riotcdn.net/channels/public/x/status/ap.json',
            'EU': 'https://valorant.secure.dyn.riotcdn.net/channels/public/x/status/eu.json',
            'NA': 'https://valorant.secure.dyn.riotcdn.net/channels/public/x/status/na.json',
            'KR': 'https://valorant.secure.dyn.riotcdn.net/channels/public/x/status/kr.json',
        },
        'League of Legends': {
            'JP': 'https://lol.secure.dyn.riotcdn.net/channels/public/x/status/jp.json',
            'KR': 'https://lol.secure.dyn.riotcdn.net/channels/public/x/status/kr.json',
            'NA': 'https://lol.secure.dyn.riotcdn.net/channels/public/x/status/na.json',
            'EUW': 'https://lol.secure.dyn.riotcdn.net/channels/public/x/status/euw.json',
            'SG': 'https://lol.secure.dyn.riotcdn.net/channels/public/x/status/sg.json',
        }
    }

    for game, regions in riot_endpoints.items():
        incidents_found = []
        maintenances_found = []

        for region, url in regions.items():
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code != 200:
                    continue

                data = response.json()

                for inc in data.get('incidents', []):
                    title = inc.get('titles', [{}])
                    title_text = title[0].get('content', 'Unknown') if title else 'Unknown'
                    incidents_found.append(f"{region}: {title_text}")

                for maint in data.get('maintenances', []):
                    title = maint.get('titles', [{}])
                    title_text = title[0].get('content', 'Unknown') if title else 'Unknown'
                    maintenances_found.append(f"{region}: {title_text}")

            except Exception as e:
                print(f"[Riot] {game} {region} 检测失败: {e}")

        if incidents_found:
            issues.append({
                'game': f'Riot ({game})',
                'region': 'Global',
                'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] {game} 事件: {'; '.join(incidents_found[:3])}",
                'source_name': 'Riot Status API',
                'source_url': 'https://status.riotgames.com/'
            })

        if maintenances_found:
            issues.append({
                'game': f'Riot ({game})',
                'region': 'Global',
                'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] {game} 维护: {'; '.join(maintenances_found[:3])}",
                'source_name': 'Riot Status API',
                'source_url': 'https://status.riotgames.com/'
            })

    return issues


def check_xbox_live_status():
    """
    通过 Reddit 间接检测 Xbox Live / PSN 状态。
    Xbox 和 PSN 的 Status 页面都是 JS 渲染，无公开 API。
    """
    issues = []

    platforms = {
        'Xbox Live': {
            'subreddit': 'xboxone',
            'query': 'xbox+live+down+OR+servers+down+OR+cant+connect',
            'threshold': 5,
        },
        'PSN': {
            'subreddit': 'PlayStation',
            'query': 'PSN+down+OR+servers+down+OR+cant+sign+in',
            'threshold': 5,
        }
    }

    for platform, config in platforms.items():
        try:
            url = (
                f"https://www.reddit.com/r/{config['subreddit']}/search.json"
                f"?q={config['query']}&restrict_sr=on&sort=new&t=day&limit=25"
            )
            response = reddit_get(url)
            if response is None:
                continue
            if response.status_code == 200:
                posts = response.json().get('data', {}).get('children', [])
                if len(posts) >= config['threshold']:
                    issues.append({
                        'game': platform,
                        'region': 'Global',
                        'country': '',
                        'alert_type': 'game_monitor',
                        'issue': f"🟡 [待确认] {platform} 连接问题讨论: 过去 24h 有 {len(posts)} 条相关帖子",
                        'source_name': f'r/{config["subreddit"]}',
                        'source_url': f'https://www.reddit.com/r/{config["subreddit"]}/'
                    })
        except Exception:
            pass

    return issues


def check_whatsapp_connectivity():
    """
    通过 Reddit 间接监控 WhatsApp 在中东/东南亚/俄罗斯的连接问题。
    重点关注 VoIP 限制地区（阿联酋、沙特等禁 WhatsApp 语音通话）和俄罗斯封锁风险。
    """
    issues = []

    queries = [
        "WhatsApp down",
        "WhatsApp blocked",
        "WhatsApp call blocked UAE",
        "WhatsApp call Saudi",
        "WhatsApp VPN",
        # 俄罗斯相关
        "WhatsApp Russia",
        "WhatsApp blocked Russia",
        "WhatsApp не работает",      # 俄语：WhatsApp 不工作
        "ватсап не работает",         # 俄语口语：ватсап 不工作
    ]

    total = 0
    for query in queries:
        try:
            encoded = requests.utils.quote(query)
            url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&t=day&limit=25"
            response = reddit_get(url)
            if response is None:
                continue
            if response.status_code == 200:
                total += len(response.json().get('data', {}).get('children', []))
            elif response.status_code == 429:
                break
        except Exception:
            pass

    if total >= 5:
        issues.append({
            'game': 'WhatsApp',
            'region': 'MENA / SEA',
            'country': '',
            'alert_type': 'game_monitor',
            'issue': f"🟢 [加速器可解决] WhatsApp 连接/封锁问题: 过去 24h 有 {total} 条相关讨论（中东 VoIP 限制/俄罗斯封锁或全球故障）",
            'source_name': 'Reddit Search',
            'source_url': 'https://www.reddit.com/search/?q=whatsapp+down&sort=new&t=day'
        })

    return issues


def check_ea_status():
    """
    通过 Reddit 间接监控 EA App / EA Online 状态。
    影响 Apex Legends, FIFA, Battlefield 等游戏。
    """
    issues = []
    try:
        url = (
            "https://www.reddit.com/search.json"
            "?q=EA+servers+down+OR+EA+app+down+OR+apex+servers+down&sort=new&t=day&limit=25"
        )
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            posts = response.json().get('data', {}).get('children', [])
            if len(posts) >= 5:
                issues.append({
                    'game': 'EA App',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🟡 [待确认] EA 服务器连接问题: 过去 24h 有 {len(posts)} 条相关讨论",
                    'source_name': 'Reddit Search',
                    'source_url': 'https://www.reddit.com/search/?q=EA+servers+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_ubisoft_status():
    """
    通过 Reddit 间接监控 Ubisoft Connect 状态。
    影响 Rainbow Six Siege, Assassin's Creed 联机等。
    """
    issues = []
    try:
        url = (
            "https://www.reddit.com/search.json"
            "?q=ubisoft+connect+down+OR+ubisoft+servers+down+OR+r6+servers+down&sort=new&t=day&limit=25"
        )
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            posts = response.json().get('data', {}).get('children', [])
            if len(posts) >= 5:
                issues.append({
                    'game': 'Ubisoft Connect',
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🟡 [待确认] Ubisoft 服务器连接问题: 过去 24h 有 {len(posts)} 条相关讨论",
                    'source_name': 'Reddit Search',
                    'source_url': 'https://www.reddit.com/search/?q=ubisoft+servers+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_garena_status():
    """
    通过 Reddit 间接监控 Garena 平台状态（东南亚游戏平台）。
    影响东南亚的 LOL、Free Fire 等游戏。
    """
    issues = []
    try:
        url = (
            "https://www.reddit.com/search.json"
            "?q=garena+down+OR+garena+server+OR+garena+lag&sort=new&t=day&limit=25"
        )
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            posts = response.json().get('data', {}).get('children', [])
            if len(posts) >= 3:  # Garena 讨论量小，阈值低
                issues.append({
                    'game': 'Garena',
                    'region': 'Southeast Asia',
                    'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🟡 [待确认] Garena 平台问题: 过去 24h 有 {len(posts)} 条相关讨论",
                    'source_name': 'Reddit Search',
                    'source_url': 'https://www.reddit.com/search/?q=garena+down&sort=new&t=day'
                })
    except Exception:
        pass

    return issues


def check_line_connectivity():
    """
    通过 Reddit 间接监控 Line 在日本/泰国/台湾的连接问题。
    """
    issues = []

    queries = [
        "Line app down",
        "LINE 繋がらない",   # 日语：LINE 连不上
        "LINE ใช้ไม่ได้",    # 泰语：LINE 用不了
    ]

    total = 0
    for query in queries:
        try:
            encoded = requests.utils.quote(query)
            url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&t=day&limit=25"
            response = reddit_get(url)
            if response is None:
                continue
            if response.status_code == 200:
                total += len(response.json().get('data', {}).get('children', []))
            elif response.status_code == 429:
                break
        except Exception:
            pass

    if total >= 3:
        issues.append({
            'game': 'LINE',
            'region': 'APAC',
            'country': '',
            'alert_type': 'game_monitor',
            'issue': f"🟢 [加速器可解决] LINE 连接问题: 过去 24h 有 {total} 条相关讨论（日本/泰国/台湾）",
            'source_name': 'Reddit Search',
            'source_url': 'https://www.reddit.com/search/?q=line+app+down&sort=new&t=day'
        })

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

    print("正在检测 FACEIT 状态...")
    all_issues.extend(check_faceit_status())

    print("正在检测 Riot Games 状态 (Valorant/LOL)...")
    all_issues.extend(check_riot_status())

    print("正在检测 Xbox Live / PSN 状态...")
    all_issues.extend(check_xbox_live_status())

    print("正在检测 WhatsApp 连接状态...")
    all_issues.extend(check_whatsapp_connectivity())

    print("正在检测 EA App 状态...")
    all_issues.extend(check_ea_status())

    print("正在检测 Ubisoft Connect 状态...")
    all_issues.extend(check_ubisoft_status())

    print("正在检测 Garena 平台状态...")
    all_issues.extend(check_garena_status())

    print("正在检测 LINE 连接状态...")
    all_issues.extend(check_line_connectivity())

    # detector404.ru 俄罗斯区平台故障检测（中等合并，高级别逐条）
    print("正在检测 detector404.ru 俄罗斯区平台状态...")
    import cis_osint
    all_issues.extend(cis_osint.check_detector404_batch(['Steam', 'Discord', 'Telegram', 'Epic Games']))

    # 保存事件去重快照
    _save_seen_incidents(_seen_incidents)

    # 处理报警：🔴 加速器无效合并去重，🟢🟡 正常输出
    from utils.alert_dedup import process_alerts
    all_issues = process_alerts(all_issues)

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
        # 处理报警：🔴 加速器无效合并去重，🟢🟡 正常输出
        from utils.alert_dedup import process_alerts
        results = process_alerts(results)
        for r in results:
            print(f"[{r['game']}] {r['issue']}")
        # 发送通知
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("所有平台运行正常。")

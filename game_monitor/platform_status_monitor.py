import requests
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import report_scrape_block, send_popo_alert, POPO_WEBHOOK_URL
from utils.istheservicedown_client import check_service_status

# ==========================================
# 通讯与游戏平台全球连接状态监控
# ==========================================
# 数据源：
# - 官方 Status API: Discord / Steam / Epic / FACEIT / Riot
# - IsTheServiceDown: Battle.net / Xbox Live / PSN / EA / Ubisoft /
#                     Garena / Telegram / WhatsApp / LINE
# - detector404.ru: 俄罗斯区平台状态 (via cis_osint.py)
#
# 事件 ID 去重：已报过的事件不再重复报警
# ==========================================

INCIDENT_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'platform_incidents_snapshot.json'
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}


# ==========================================
# 事件去重
# ==========================================

def _load_seen_incidents():
    if os.path.exists(INCIDENT_SNAPSHOT_FILE):
        try:
            with open(INCIDENT_SNAPSHOT_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_seen_incidents(seen):
    recent = list(seen)[-200:]
    with open(INCIDENT_SNAPSHOT_FILE, 'w') as f:
        json.dump(recent, f)


_seen_incidents = _load_seen_incidents()


def _is_new_incident(incident_id):
    if incident_id in _seen_incidents:
        return False
    _seen_incidents.add(incident_id)
    return True


# ==========================================
# Discord — 官方 Status API
# ==========================================

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

DISCORD_CORE_COMPONENTS = {
    'rhznvxg4v7yh': 'API',
    'x7rnz0t7dpnp': 'Gateway',
    '354mn7xfxz1h': 'Push Notifications',
    '3y468xdr1st2': 'Search',
    'r3wq1zsx72bz': 'Media Proxy',
}


def check_discord_status():
    """检查 Discord 官方 Status API。"""
    issues = []
    url = "https://discordstatus.com/api/v2/summary.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[Discord] HTTP {response.status_code}")
            return issues

        data = response.json()
        components = {c['id']: c for c in data.get('components', [])}

        # Voice 服务器区域状态
        degraded_regions = []
        for comp_id, region_name in DISCORD_VOICE_REGIONS.items():
            comp = components.get(comp_id)
            if comp and comp['status'] != 'operational':
                status = comp['status'].replace('_', ' ').title()
                degraded_regions.append(f"{region_name}: {status}")

        if degraded_regions:
            russia_affected = any('Russia' in r for r in degraded_regions)
            prefix = "🟢 [加速器可解决] 🚨 [俄罗斯受影响] " if russia_affected else "🟡 [待确认] "
            issues.append({
                'game': 'Discord', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"{prefix}Discord Voice 服务器异常: {', '.join(degraded_regions)}",
                'source_name': 'Discord Status API',
                'source_url': 'https://discordstatus.com/'
            })

        # 核心服务状态
        degraded_core = []
        for comp_id, service_name in DISCORD_CORE_COMPONENTS.items():
            comp = components.get(comp_id)
            if comp and comp['status'] != 'operational':
                status = comp['status'].replace('_', ' ').title()
                degraded_core.append(f"{service_name}: {status}")

        if degraded_core:
            issues.append({
                'game': 'Discord', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] Discord 核心服务异常（官方故障）: {', '.join(degraded_core)}",
                'source_name': 'Discord Status API',
                'source_url': 'https://discordstatus.com/'
            })

        # 活跃事件（去重）
        for incident in data.get('incidents', []):
            if incident.get('status') not in ('resolved', 'postmortem'):
                inc_id = f"discord_{incident.get('id', '')}"
                if not _is_new_incident(inc_id):
                    continue
                impact = incident.get('impact', 'none')
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Discord', 'region': 'Global', 'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Discord 事件 [{impact}]: {name} (状态: {status})",
                    'source_name': 'Discord Status API',
                    'source_url': incident.get('shortlink', 'https://discordstatus.com/')
                })

    except Exception as e:
        print(f"[Discord] 检测失败: {e}")

    return issues


# ==========================================
# Steam — steamstat.us API
# ==========================================

def check_steam_status():
    """通过 steamstat.us 检查 Steam 平台全球状态。"""
    issues = []
    try:
        url = "https://crowbar.steamstat.us/gravity.json"
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            data = response.json()
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
                    'game': 'Steam', 'region': 'Global', 'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Steam 平台异常（官方服务故障）: {', '.join(degraded[:5])}",
                    'source_name': 'steamstat.us',
                    'source_url': 'https://steamstat.us/'
                })
        else:
            print(f"[Steam] steamstat.us HTTP {response.status_code}")
            report_scrape_block('steam_status_api', url, response.status_code)
    except Exception as e:
        print(f"[Steam] steamstat.us 检测失败: {e}")
        report_scrape_block('steam_status_api', 'https://crowbar.steamstat.us/gravity.json')

    return issues


# ==========================================
# Epic Games — 官方 Status API
# ==========================================

def check_epic_platform_status():
    """检查 Epic Games 平台整体状态。"""
    issues = []
    url = "https://status.epicgames.com/api/v2/summary.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return issues

        data = response.json()

        egs_issues = []
        for comp in data.get('components', []):
            if comp.get('group', False):
                name = comp.get('name', '')
                status = comp.get('status', 'operational')
                if status != 'operational' and name in [
                    'Epic Games Store', 'Epic Online Services',
                    'Rocket League', 'Fall Guys'
                ]:
                    egs_issues.append(f"{name}: {status.replace('_', ' ').title()}")

        if egs_issues:
            issues.append({
                'game': 'Epic Games', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] Epic 平台异常（官方服务故障）: {', '.join(egs_issues)}",
                'source_name': 'Epic Status API',
                'source_url': 'https://status.epicgames.com/'
            })

        for incident in data.get('incidents', []):
            if incident.get('status') not in ('resolved', 'postmortem'):
                inc_id = f"epic_{incident.get('id', '')}"
                if not _is_new_incident(inc_id):
                    continue
                name = incident.get('name', '')
                status = incident.get('status', '')
                issues.append({
                    'game': 'Epic Games', 'region': 'Global', 'country': '',
                    'alert_type': 'game_monitor',
                    'issue': f"🔴 [加速器无效] Epic 事件: {name} (状态: {status})",
                    'source_name': 'Epic Status API',
                    'source_url': 'https://status.epicgames.com/'
                })

    except Exception as e:
        print(f"[Epic] 检测失败: {e}")

    return issues


# ==========================================
# FACEIT — 官方 Status API（不再使用 Reddit fallback）
# ==========================================

def check_faceit_status():
    """检查 FACEIT 状态（incident.io Status API）。"""
    issues = []
    url = "https://www.faceitstatus.com/api/v1/summary"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[FACEIT] HTTP {response.status_code}")
            return issues

        data = response.json()

        for incident in data.get('ongoing_incidents', []):
            name = incident.get('name', 'Unknown')
            inc_id = f"faceit_{incident.get('id', name)}"
            if not _is_new_incident(inc_id):
                continue
            issues.append({
                'game': 'FACEIT', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] FACEIT 事件: {name}",
                'source_name': 'FACEIT Status',
                'source_url': 'https://www.faceitstatus.com/'
            })

        for maint in data.get('in_progress_maintenances', []):
            name = maint.get('name', 'Unknown')
            issues.append({
                'game': 'FACEIT', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] FACEIT 维护中: {name}",
                'source_name': 'FACEIT Status',
                'source_url': 'https://www.faceitstatus.com/'
            })

    except Exception as e:
        print(f"[FACEIT] 检测失败: {e}")

    return issues


# ==========================================
# Riot Games — 官方 Status API
# ==========================================

def check_riot_status():
    """检查 Riot Games 服务状态（Valorant / LOL）。"""
    issues = []

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
                'game': f'Riot ({game})', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] {game} 事件: {'; '.join(incidents_found[:3])}",
                'source_name': 'Riot Status API',
                'source_url': 'https://status.riotgames.com/'
            })

        if maintenances_found:
            issues.append({
                'game': f'Riot ({game})', 'region': 'Global', 'country': '',
                'alert_type': 'game_monitor',
                'issue': f"🔴 [加速器无效] {game} 维护: {'; '.join(maintenances_found[:3])}",
                'source_name': 'Riot Status API',
                'source_url': 'https://status.riotgames.com/'
            })

    return issues


# ==========================================
# IsTheServiceDown 通用检测
# ==========================================
# 以下平台原来依赖 Reddit 搜索，现改为 IsTheServiceDown 社区报告数据。
# 数据来源：istheservicedown.com 的 <noscript> 报告表格（24h 报告量 + 基线）。
# ==========================================

# 平台配置：slug → (显示名, 区域, 国家, 报警标签, 报告阈值)
ITSD_PLATFORMS = {
    'battle-net': {
        'name': 'Battle.net',
        'region': 'Global',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 20,  # 最近 2h 报告总数阈值
    },
    'xbox-live': {
        'name': 'Xbox Live',
        'region': 'Global',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 20,
    },
    'playstation-network': {
        'name': 'PSN',
        'region': 'Global',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 20,
    },
    'ea': {
        'name': 'EA App',
        'region': 'Global',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 15,
    },
    'ubisoft': {
        'name': 'Ubisoft Connect',
        'region': 'Global',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 15,
    },
    'garena': {
        'name': 'Garena',
        'region': 'Southeast Asia',
        'country': '',
        'tag': '🟡 [待确认]',
        'threshold': 10,  # Garena 用户量小，阈值低
    },
    'telegram': {
        'name': 'Telegram',
        'region': 'Global / Russia',
        'country': '',
        'tag': '🟢 [加速器可解决]',
        'threshold': 30,
    },
    'whatsapp': {
        'name': 'WhatsApp',
        'region': 'MENA / SEA',
        'country': '',
        'tag': '🟢 [加速器可解决]',
        'threshold': 30,
    },
    'line': {
        'name': 'LINE',
        'region': 'APAC',
        'country': '',
        'tag': '🟢 [加速器可解决]',
        'threshold': 15,
    },
}


def _check_itsd_platform(slug: str, config: dict) -> list:
    """通过 IsTheServiceDown 检测单个平台状态。"""
    issues = []
    result = check_service_status(slug)
    if result is None:
        print(f"[{config['name']}] IsTheServiceDown 检测失败")
        return issues

    if result['status'] == 'outage' or result['recent_reports'] >= config['threshold']:
        reports = result['recent_reports']
        baseline = result['recent_baseline']
        peak = result['peak_reports']

        detail = f"最近 2h 报告 {reports} 次"
        if baseline > 0:
            detail += f"（基线 {baseline}）"
        if peak > 0:
            detail += f"，峰值 {peak}"

        issues.append({
            'game': config['name'],
            'region': config['region'],
            'country': config['country'],
            'alert_type': 'game_monitor',
            'issue': f"{config['tag']} {config['name']} 连接问题: {detail}",
            'source_name': 'IsTheServiceDown',
            'source_url': result['source_url'],
        })

    return issues


def check_itsd_platforms():
    """批量检测所有 ITSD 平台。"""
    all_issues = []
    for slug, config in ITSD_PLATFORMS.items():
        print(f"  正在检测 {config['name']}...")
        try:
            all_issues.extend(_check_itsd_platform(slug, config))
        except Exception as e:
            print(f"[{config['name']}] 检测异常: {e}")
    return all_issues


# ==========================================
# 主检测函数
# ==========================================

def check_all_platforms():
    """主检测函数：检查所有平台状态"""
    all_issues = []

    # 官方 Status API
    print("正在检测 Discord 全球状态...")
    all_issues.extend(check_discord_status())

    print("正在检测 Steam 全球状态...")
    all_issues.extend(check_steam_status())

    print("正在检测 Epic Games 平台状态...")
    all_issues.extend(check_epic_platform_status())

    print("正在检测 FACEIT 状态...")
    all_issues.extend(check_faceit_status())

    print("正在检测 Riot Games 状态 (Valorant/LOL)...")
    all_issues.extend(check_riot_status())

    # IsTheServiceDown 社区报告（替代 Reddit）
    print("正在通过 IsTheServiceDown 检测平台状态...")
    all_issues.extend(check_itsd_platforms())

    # detector404.ru 俄罗斯区平台故障检测
    print("正在检测 detector404.ru 俄罗斯区平台状态...")
    import cis_osint
    all_issues.extend(cis_osint.check_detector404_batch([
        'Steam', 'Discord', 'Telegram', 'Epic Games',
        'Battle.net', 'PlayStation', 'Xbox Live', 'FACEIT', 'Ubisoft Connect'
    ]))

    # 保存事件去重快照
    _save_seen_incidents(_seen_incidents)

    # 处理报警：🔴 加速器无效合并去重，🟢🟡 正常输出
    from utils.alert_dedup import process_alerts
    all_issues = process_alerts(all_issues)

    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Platform Status Monitor...")
    results = check_all_platforms()
    if results:
        from utils.alert_dedup import process_alerts
        results = process_alerts(results)
        for r in results:
            print(f"[{r['game']}] {r['issue']}")
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("所有平台运行正常。")

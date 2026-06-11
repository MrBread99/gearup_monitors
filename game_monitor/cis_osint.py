import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import random
import re
import os
import sys
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==========================================
# 独联体/俄语区 (CIS/Russia) 监控配置
# ==========================================

# 俄语本地化异常关键词
RU_KEYWORDS = ["ПИНГ", "ЛАГ", "ЛАГИ", "ПОТЕРЯ", "ПАКЕТОВ", "СЕРВЕРА ЛЕЖАТ", "ВЫЛЕТАЕТ", "РОСТЕЛЕКОМ", "ROSTELECOM"]

# VK.com 游戏社群 (Groups) 映射 — 从统一游戏注册表 (game_registry.py) 加载
from game_registry import get_vk_game_map
VK_GAME_MAP = get_vk_game_map()

# detector404.ru（俄罗斯版 Downdetector）游戏/平台 slug 映射
DETECTOR404_MAP = {
    # === 已追踪游戏（GAME_REGISTRY 中也有） ===
    'Valorant': 'valorant',
    'League of Legends': 'leagueoflegends',
    'APEX Legends': 'apex-legends',
    'CS2': 'cs2',
    'Fortnite': 'fortnite',
    'PUBG': 'pubg-battlegrounds',
    'Overwatch 2': 'overwatch2',
    'Rainbow Six Siege': 'rainbowsixsiege',
    'Dota 2': 'dota-2',
    'Call of Duty': 'codwz',
    'Escape from Tarkov': 'escapefromtarkov',
    'Dead by Daylight': 'deadbydaylight',
    'Rust': 'rust',
    'GTA Online': 'gtaonline',
    'Monster Hunter Wilds': 'monsterhunter',
    'Marvel Rivals': 'marvelrivals',
    'Rocket League': 'rocketleague',
    'Palworld': 'palworld',
    'Naraka Bladepoint': 'narakathegame',
    'EA FC': 'fc24',
    'Warframe': 'warframe',
    'Genshin Impact': 'genshinimpact',
    'Zenless Zone Zero': 'zenlesszonezero',
    'Roblox': 'roblox',
    'ARC Raiders': 'arcraiders',
    'Delta Force': 'deltaforce',
    'War Thunder': 'warthunder',
    'HELLDIVERS 2': 'helldivers2',
    'DayZ': 'dayz',
    'Hunt Showdown': 'hunt',
    'Final Fantasy XIV': 'finalfantasy',
    'Elden Ring Nightreign': 'eldenring',
    'STALCRAFT X': 'stalcraft',
    'World of Warcraft': 'world-of-warcraft',
    # === 新增：detector404 上有页面的俄区热门 PC 联机游戏 ===
    'Minecraft': 'minecraft',
    'Warface': 'warface',
    'Lineage 2': 'lineage2',
    'Battlefield 2042': 'battlefield2042',
    'Fallout 76': 'fallout76',
    'New World': 'newworld',
    'Dark and Darker': 'darkanddarker',
    'EVE Online': 'eveonline',
    'Forza Horizon 5': 'forza5',
    'Diablo III': 'diablo-iii',
    'Hearthstone': 'hearthstone',
    'Elder Scrolls Online': 'theelderscrolls',
    # === 平台 ===
    'Steam': 'steam',
    'Discord': 'discord',
    'Telegram': 'telegram',
    'Epic Games': 'epicgames',
    'Battle.net': 'battlenet',
    'PlayStation': 'playstation',
    'Xbox Live': 'xboxlive',
    'FACEIT': 'faceit',
    'Ubisoft Connect': 'ubisoft',
}

# 平台名称集合（用于区分游戏和平台，避免 monitor.py 与 platform_status_monitor.py 重复检测）
DETECTOR404_PLATFORMS = {
    'Steam', 'Discord', 'Telegram', 'Epic Games',
    'Battle.net', 'PlayStation', 'Xbox Live', 'FACEIT', 'Ubisoft Connect',
}


def get_detector404_game_only_names():
    """返回 DETECTOR404_MAP 中仅游戏条目（排除平台），供 monitor.py 使用。"""
    return [name for name in DETECTOR404_MAP if name not in DETECTOR404_PLATFORMS]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Mobile Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
}

HEADERS_WEB = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9'
}

DETECTOR404_BATCH_DELAY_RANGE = (4.0, 7.0)
DETECTOR404_429_RETRY_WAIT_RANGE = (18.0, 26.0)
DETECTOR404_BATCH_COOLDOWN_RANGE = (45.0, 75.0)
DETECTOR404_MAX_429_STREAK = 2
DETECTOR404_LEVEL_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'detector404_level_snapshot.json'
)

DETECTOR404_LEVEL_RANK = {
    'нет': 0,
    'мало': 1,
    'минимально': 1,
    'умеренно': 2,
    'много': 3,
    'критично': 4,
    'массово': 5,
}
DETECTOR404_MEDIUM_LEVEL = 'умеренно'


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _load_detector404_level_snapshot():
    if os.path.exists(DETECTOR404_LEVEL_SNAPSHOT_FILE):
        try:
            with open(DETECTOR404_LEVEL_SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_detector404_level_snapshot(snapshot):
    try:
        with open(DETECTOR404_LEVEL_SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CIS] detector404 等级快照保存失败: {e}")


def _rank_detector404_level(level):
    return DETECTOR404_LEVEL_RANK.get((level or '').lower(), -1)


def _record_detector404_level(game_name, complaint_level, complaint_level_zh):
    """
    记录 detector404 投诉等级，便于后续排查页面状态变化。
    报警是否发送由 check_detector404() 的等级判断决定。
    """
    level = (complaint_level or '').lower()
    current_rank = _rank_detector404_level(level)
    if current_rank < 0:
        return

    snapshot = _load_detector404_level_snapshot()
    previous = snapshot.get(game_name, {})
    previous_level = (previous.get('level') or '').lower()

    snapshot[game_name] = {
        'level': level,
        'level_zh': complaint_level_zh,
        'rank': current_rank,
        'last_seen_at': _now_iso(),
        'previous_level': previous_level,
    }
    _save_detector404_level_snapshot(snapshot)


def analyze_russian_text(text_list, threshold=2):
    """分析俄语文本列表，匹配故障关键词"""
    issue_count = 0
    matched_keywords = set()
    
    for text in text_list:
        upper_text = text.upper()
        for kw in RU_KEYWORDS:
            if kw in upper_text:
                issue_count += 1
                matched_keywords.add(kw)
                break
                
    return issue_count >= threshold, issue_count, list(matched_keywords)


def check_cis_vk(game_name):
    """
    抓取俄语区最大的社交网络 VK (Vkontakte) 的对应游戏群组的墙 (Wall)
    用于侦测俄罗斯及独联体国家的网络异常。
    """
    vk_group = VK_GAME_MAP.get(game_name)
    if not vk_group:
        return None
        
    url = f"https://m.vk.com/{vk_group}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            post_divs = soup.find_all('div', class_='pi_text')
            texts = [div.text for div in post_divs]
            
            is_down, count, matched = analyze_russian_text(texts, threshold=2)
            
            if is_down:
                return {
                    'game': game_name,
                    'region': 'CIS / Russia',
                    'country': 'Russia / Ukraine / KZ',
                    'issue': f"⭐⭐⭐ 绝佳营销时机 (独联体专区) - VK玩家在抱怨网络 (匹配词: {', '.join(matched)}, 共{count}篇)",
                    'source_name': 'VK.com (俄语社群)',
                    'source_url': url
                }
        else:
            print(f"[CIS] VK {game_name}: HTTP {response.status_code}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('vk_game', url=url, status_code=response.status_code)
            except Exception:
                pass
    except Exception as e:
        print(f"[CIS] 抓取 VK 俄语社区 ({game_name}) 失败: {e}")
        
    return None


def check_detector404(game_name, return_status=False, return_meta=False):
    """
    检查 detector404.ru（俄罗斯版 Downdetector）上的故障报告。
    提取：投诉量级、受影响区域 TOP5、故障类型占比。
    """
    slug = DETECTOR404_MAP.get(game_name)
    meta = {
        'game': game_name,
        'url': '',
        'status_code': None,
        'outcome': 'unknown',
        'parsed': False,
        'level': '',
        'level_zh': '',
        'error': '',
    }

    def finish(result=None, status_code=None):
        meta['status_code'] = status_code
        if return_meta:
            return result, status_code, meta
        if return_status:
            return result, status_code
        return result

    if not slug:
        meta['outcome'] = 'no_slug'
        return finish(None, None)

    url = f"https://detector404.ru/{slug}"
    meta['url'] = url

    try:
        response = requests.get(url, headers=HEADERS_WEB, timeout=15)
        if response.status_code == 429:
            retry_wait = random.uniform(*DETECTOR404_429_RETRY_WAIT_RANGE)
            print(
                f"[CIS] detector404 {game_name}: HTTP 429, "
                f"cooling down {retry_wait:.1f}s before one retry"
            )
            time.sleep(retry_wait)
            response = requests.get(url, headers=HEADERS_WEB, timeout=15)

        if response.status_code != 200:
            print(f"[CIS] detector404 {game_name}: HTTP {response.status_code}")
            meta['outcome'] = 'http_error'
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('detector404', url=url, status_code=response.status_code)
            except Exception:
                pass
            return finish(None, response.status_code)

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()

        # 提取投诉量级 — 页面中有 "Жалоб – умеренно/много/критично" 等描述
        # 翻译对照：нет=无, мало=少, минимально=极少, умеренно=中等, много=大量, критично=严重, массово=大规模
        LEVEL_TRANSLATE = {
            'нет': '无',
            'мало': '少量',
            'минимально': '极少',
            'умеренно': '⚠️ 中等（高于正常水平）',
            'много': '🔶 大量（明显异常）',
            'критично': '🔴 严重（大面积故障）',
            'массово': '🔴 大规模（全面爆发）',
        }

        complaint_level = None
        complaint_level_zh = None
        level_match = re.search(r'Жалоб\s*[–—-]\s*(\S+)', text)
        if level_match:
            complaint_level = level_match.group(1).lower()
            complaint_level_zh = LEVEL_TRANSLATE.get(complaint_level, complaint_level)

        meta['parsed'] = bool(complaint_level)
        meta['level'] = complaint_level or ''
        meta['level_zh'] = complaint_level_zh or ''

        if not complaint_level:
            meta['outcome'] = 'parse_failed'
            return finish(None, 200)

        _record_detector404_level(game_name, complaint_level, complaint_level_zh)

        # 低位只更新快照，不报警；中等及以上都进入报警逻辑。
        if complaint_level and complaint_level.lower() in ('нет', 'мало', 'минимально'):
            meta['outcome'] = 'low'
            return finish(None, 200)

        # 提取受影响区域 TOP，并翻译俄语地名
        REGION_TRANSLATE = {
            'Московская область': '莫斯科州',
            'Москва': '莫斯科',
            'Санкт-Петербург': '圣彼得堡',
            'Новосибирская область': '新西伯利亚州',
            'Свердловская область': '斯维尔德洛夫斯克州',
            'Краснодарский край': '克拉斯诺达尔边疆区',
            'Татарстан': '鞑靼斯坦',
            'Нижегородская область': '下诺夫哥罗德州',
            'Самарская область': '萨马拉州',
            'Челябинская область': '车里雅宾斯克州',
            'Ростовская область': '罗斯托夫州',
            'Волгоградская область': '伏尔加格勒州',
            'Тюменская область': '秋明州',
            'Приморский край': '滨海边疆区',
            'Хабаровский край': '哈巴罗夫斯克边疆区',
            'Магаданская область': '马加丹州',
            'Пермский край': '彼尔姆边疆区',
            'Воронежская область': '沃罗涅日州',
            'Иркутская область': '伊尔库茨克州',
            'Омская область': '鄂木斯克州',
        }

        regions = []
        region_links = soup.select('a[href*="-oblast"], a[href*="-kraj"], a[href*="-respublika"]')
        for link in region_links[:5]:
            region_text = link.get_text(strip=True)
            region_zh = REGION_TRANSLATE.get(region_text, region_text)
            # 提取百分比
            pct_match = re.search(r'(\d+)%', link.parent.get_text() if link.parent else '')
            if pct_match:
                regions.append(f"{region_zh} {pct_match.group(1)}%")
            elif region_zh:
                regions.append(region_zh)

        # 提取故障类型占比
        fault_types = []
        type_patterns = [
            (r'Общий сбой\s*(\d+)%', '全面故障'),
            (r'Сбой сайта\s*(\d+)%', '网站故障'),
            (r'Сбой мобильного\s*(\d+)%', '移动端故障'),
            (r'Сбой личного кабинета\s*(\d+)%', '账户故障'),
        ]
        for pattern, label in type_patterns:
            match = re.search(pattern, text)
            if match:
                fault_types.append(f"{label} {match.group(1)}%")

        # 根据投诉量级分级处理
        high_levels = ['много', 'критично', 'массово']  # 大量/严重/大规模

        is_high = complaint_level and any(lvl in complaint_level for lvl in high_levels)
        is_medium = complaint_level == DETECTOR404_MEDIUM_LEVEL

        if is_medium:
            issue_parts = [f"🟡 [待确认] 🇷🇺 俄罗斯区 detector404 中等投诉 (投诉量: {complaint_level_zh})"]
            if regions:
                issue_parts.append(f"受影响区域: {', '.join(regions[:5])}")
            if fault_types:
                issue_parts.append(f"故障类型: {', '.join(fault_types)}")

            result = {
                'game': game_name,
                'region': 'CIS / Russia',
                'country': 'Russia',
                'issue': '\n    '.join(issue_parts),
                'source_name': 'detector404.ru',
                'source_url': url
            }
            meta['outcome'] = 'alert'
            print(f"[detector404 ALERT] {game_name}: {complaint_level} / {complaint_level_zh}")
            return finish(result, 200)

        if is_high:
            # 高级别：详细报告（含区域和故障类型）
            issue_parts = [f"🇷🇺 俄罗斯区故障检测 (投诉量: {complaint_level_zh})"]
            if regions:
                issue_parts.append(f"受影响区域: {', '.join(regions[:5])}")
            if fault_types:
                issue_parts.append(f"故障类型: {', '.join(fault_types)}")

            result = {
                'game': game_name,
                'region': 'CIS / Russia',
                'country': 'Russia',
                'issue': '\n    '.join(issue_parts),
                'source_name': 'detector404.ru',
                'source_url': url
            }
            meta['outcome'] = 'alert'
            print(f"[detector404 ALERT] {game_name}: {complaint_level} / {complaint_level_zh}")
            return finish(result, 200)

        meta['outcome'] = 'unknown_level'
        print(f"[CIS] detector404 {game_name}: unknown complaint level '{complaint_level}'")

    except Exception as e:
        meta['outcome'] = 'exception'
        meta['error'] = str(e)
        print(f"[CIS] detector404 检测 {game_name} 失败: {e}")

    return finish(None, None)


def check_detector404_batch(game_names=None):
    """
    批量检测 detector404，报告中等/大量/严重/大规模级别。
    game_names: 指定要检测的名称列表；为 None 时遍历 DETECTOR404_MAP 中所有条目
               （含不在 GAME_REGISTRY 中的俄区热门游戏）。
    每次请求之间加入 4-7 秒随机延迟；若命中 429，会额外冷却后重试一次。
    若连续多个请求仍然 429，则提前结束本轮批量检测，避免继续触发频控。
    返回 issues 列表。
    """
    issues = []
    names = game_names if game_names is not None else list(DETECTOR404_MAP.keys())
    consecutive_429 = 0
    summary = {
        'checked': 0,
        'parsed': 0,
        'low': 0,
        'alert': 0,
        'parse_failed': 0,
        'http_error': 0,
        'exception': 0,
        'no_slug': 0,
        'unknown_level': 0,
        'ended_early': False,
        'status_counts': {},
        'alert_names': [],
        'parse_failed_names': [],
        'http_error_names': [],
        'exception_names': [],
        'unknown_level_names': [],
    }

    def remember_status(status_code):
        key = str(status_code) if status_code is not None else 'None'
        summary['status_counts'][key] = summary['status_counts'].get(key, 0) + 1

    def preview(names_list, limit=8):
        if not names_list:
            return ''
        visible = ', '.join(names_list[:limit])
        return visible + (' ...' if len(names_list) > limit else '')

    for i, name in enumerate(names):
        # 放慢批量抓取节奏，减少固定 CI IP 被频控的概率
        if i > 0:
            time.sleep(random.uniform(*DETECTOR404_BATCH_DELAY_RANGE))

        result, status_code, meta = check_detector404(name, return_status=True, return_meta=True)
        summary['checked'] += 1
        remember_status(status_code)

        if meta.get('parsed'):
            summary['parsed'] += 1

        outcome = meta.get('outcome', 'unknown')
        if outcome in summary and isinstance(summary[outcome], int):
            summary[outcome] += 1

        if outcome == 'alert':
            summary['alert_names'].append(name)
        elif outcome == 'parse_failed':
            summary['parse_failed_names'].append(name)
        elif outcome == 'http_error':
            summary['http_error_names'].append(f"{name}:{status_code}")
        elif outcome == 'exception':
            summary['exception_names'].append(f"{name}:{meta.get('error', '')[:80]}")
        elif outcome == 'unknown_level':
            summary['unknown_level_names'].append(f"{name}:{meta.get('level', '')}")

        if status_code == 429:
            consecutive_429 += 1
            if consecutive_429 >= DETECTOR404_MAX_429_STREAK:
                cooldown = random.uniform(*DETECTOR404_BATCH_COOLDOWN_RANGE)
                print(
                    f"[CIS] detector404 consecutive 429 streak reached {consecutive_429}; "
                    f"cooling down {cooldown:.1f}s and ending this batch early."
                )
                summary['ended_early'] = True
                time.sleep(cooldown)
                break
        else:
            consecutive_429 = 0

        if result:
            issues.append(result)

    print(
        "[detector404 SUMMARY] "
        f"checked={summary['checked']}/{len(names)}, "
        f"parsed={summary['parsed']}, "
        f"alerts={summary['alert']}, "
        f"low={summary['low']}, "
        f"parse_failed={summary['parse_failed']}, "
        f"http_error={summary['http_error']}, "
        f"exception={summary['exception']}, "
        f"unknown_level={summary['unknown_level']}, "
        f"ended_early={summary['ended_early']}, "
        f"statuses={summary['status_counts']}"
    )
    if summary['alert_names']:
        print(f"[detector404 SUMMARY] alert games: {preview(summary['alert_names'])}")
    if summary['parse_failed_names']:
        print(f"[detector404 SUMMARY] parse failed: {preview(summary['parse_failed_names'])}")
    if summary['http_error_names']:
        print(f"[detector404 SUMMARY] http errors: {preview(summary['http_error_names'])}")
    if summary['exception_names']:
        print(f"[detector404 SUMMARY] exceptions: {preview(summary['exception_names'])}")
    if summary['unknown_level_names']:
        print(f"[detector404 SUMMARY] unknown levels: {preview(summary['unknown_level_names'])}")

    failure_threshold = max(5, summary['checked'] // 2)
    should_report_parse_anomaly = (
        summary['checked'] > 0 and (
            summary['parsed'] == 0
            or summary['parse_failed'] >= failure_threshold
            or summary['exception'] >= failure_threshold
        )
    )
    if should_report_parse_anomaly:
        try:
            from utils.notifier import report_scrape_block
            report_scrape_block('detector404_parse', url='https://detector404.ru')
        except Exception:
            pass

    return issues


def check_cis_telegram_search(game_name):
    """
    备用方案：通过第三方 Telegram 搜索引擎。
    目前主依赖 VK + detector404。
    """
    pass


if __name__ == "__main__":
    print("Testing CIS OSINT...")
    res = check_cis_vk("Dota 2")
    print(f"VK: {res}")
    res2 = check_detector404("Steam")
    print(f"detector404 Steam: {res2}")
    res3 = check_detector404("Discord")
    print(f"detector404 Discord: {res3}")

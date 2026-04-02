import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import random
import re
import os
import sys

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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Mobile Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
}

HEADERS_WEB = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9'
}


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


def check_detector404(game_name):
    """
    检查 detector404.ru（俄罗斯版 Downdetector）上的故障报告。
    提取：投诉量级、受影响区域 TOP5、故障类型占比。
    """
    slug = DETECTOR404_MAP.get(game_name)
    if not slug:
        return None

    url = f"https://detector404.ru/{slug}"

    try:
        response = requests.get(url, headers=HEADERS_WEB, timeout=15)
        if response.status_code != 200:
            print(f"[CIS] detector404 {game_name}: HTTP {response.status_code}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('detector404', url=url, status_code=response.status_code)
            except Exception:
                pass
            return None

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

        # 只报大量/严重/大规模，过滤掉中等及以下
        if complaint_level and complaint_level.lower() in ('нет', 'мало', 'минимально', 'умеренно'):
            return None

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

        if is_high:
            # 高级别：详细报告（含区域和故障类型）
            issue_parts = [f"🇷🇺 俄罗斯区故障检测 (投诉量: {complaint_level_zh})"]
            if regions:
                issue_parts.append(f"受影响区域: {', '.join(regions[:5])}")
            if fault_types:
                issue_parts.append(f"故障类型: {', '.join(fault_types)}")

            return {
                'game': game_name,
                'region': 'CIS / Russia',
                'country': 'Russia',
                'issue': '\n    '.join(issue_parts),
                'source_name': 'detector404.ru',
                'source_url': url
            }

    except Exception as e:
        print(f"[CIS] detector404 检测 {game_name} 失败: {e}")

    return None


def check_detector404_batch(game_names=None):
    """
    批量检测 detector404，只报大量/严重/大规模级别。
    game_names: 指定要检测的名称列表；为 None 时遍历 DETECTOR404_MAP 中所有条目
               （含不在 GAME_REGISTRY 中的俄区热门游戏）。
    每次请求之间加入 1-3 秒随机延迟，避免批量请求触发封禁。
    返回 issues 列表。
    """
    issues = []
    names = game_names if game_names is not None else list(DETECTOR404_MAP.keys())

    for i, name in enumerate(names):
        # 随机延迟 1-3 秒，避免批量请求被 detector404.ru 封禁
        if i > 0:
            time.sleep(random.uniform(1.0, 3.0))

        result = check_detector404(name)
        if result:
            issues.append(result)

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

import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import re

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
    # 游戏
    'Valorant': 'valorant',
    'League of Legends': 'league-of-legends',
    'APEX Legends': 'apex-legends',
    'CS2': 'counter-strike-2',
    'Fortnite': 'fortnite',
    'PUBG': 'pubg',
    'Overwatch 2': 'overwatch',
    'Dota 2': 'dota-2',
    'Escape from Tarkov': 'escape-from-tarkov',
    'Path of Exile 2': 'path-of-exile',
    # 平台
    'Steam': 'steam',
    'Discord': 'discord',
    'Telegram': 'telegram',
    'Epic Games': 'epic-games',
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

        # 如果投诉量级为"无"或"少"，跳过
        if complaint_level and complaint_level.lower() in ('нет', 'мало', 'минимально'):
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
        high_levels = ['много', 'критично', 'массово']  # 大量/严重/大规模 → 详细报
        moderate_levels = ['умеренно']                    # 中等 → 简要汇总

        is_high = complaint_level and any(lvl in complaint_level for lvl in high_levels)
        is_moderate = complaint_level and any(lvl in complaint_level for lvl in moderate_levels)

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
                'detail_level': 'high',
                'source_name': 'detector404.ru',
                'source_url': url
            }
        elif is_moderate:
            # 中等级别：只返回基本信息，由调用方汇总
            return {
                'game': game_name,
                'region': 'CIS / Russia',
                'country': 'Russia',
                'issue': '',  # 占位，由 batch 函数填充
                'detail_level': 'moderate',
                'complaint_level_zh': complaint_level_zh,
                'source_name': 'detector404.ru',
                'source_url': url
            }

    except Exception as e:
        print(f"[CIS] detector404 检测 {game_name} 失败: {e}")

    return None


def check_detector404_batch(game_names):
    """
    批量检测 detector404，自动合并中等级别的报警。
    - 中等（умеренно）：合并成一条，只列游戏名
    - 大量/严重/大规模：逐条详细报告
    返回 issues 列表。
    """
    issues = []
    moderate_games = []

    for name in game_names:
        result = check_detector404(name)
        if not result:
            continue

        if result.get('detail_level') == 'high':
            # 高级别：直接加入
            issues.append(result)
        elif result.get('detail_level') == 'moderate':
            moderate_games.append(result.get('game', '?'))

    # 中等级别合并成一条
    if moderate_games:
        issues.append({
            'game': 'detector404.ru',
            'region': 'CIS / Russia',
            'country': 'Russia',
            'issue': f"🇷🇺 俄罗斯区投诉量中等的服务: {', '.join(moderate_games)}",
            'source_name': 'detector404.ru',
            'source_url': 'https://detector404.ru/'
        })

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

import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

# ==========================================
# 独联体/俄语区 (CIS/Russia) 监控配置
# ==========================================

# 俄语本地化异常关键词
# пинг = ping, лаги = lags, потеря = loss, пакет = packet, сервера = servers, лежат = down
RU_KEYWORDS = ["ПИНГ", "ЛАГ", "ЛАГИ", "ПОТЕРЯ", "ПАКЕТОВ", "СЕРВЕРА ЛЕЖАТ", "ВЫЛЕТАЕТ", "РОСТЕЛЕКОМ", "ROSTELECOM"]

# VK.com 游戏社群 (Groups) 映射
# 我们无需登录 API，可以直接通过 VK 的开放搜索页面抓取最新发帖
# (注：VK的反爬经常变化，这里使用免登录的移动版页面 m.vk.com 成功率更高)
VK_GAME_MAP = {
    'Valorant': 'valorant_ru',
    'League of Legends': 'leagueoflegends',
    'CS2': 'csgo', # 俄区大量玩家依然使用原群名
    'Dota 2': 'dota2',
    'PUBG': 'pubg',
    'APEX Legends': 'apexlegendsru'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Mobile Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
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
        
        # 如果返回 200，说明移动版页面访问成功
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 抓取页面上的发帖内容 (移动版 VK 的 post 文本通常在 pi_text 类的 div 里)
            post_divs = soup.find_all('div', class_='pi_text')
            texts = [div.text for div in post_divs]
            
            is_down, count, matched = analyze_russian_text(texts, threshold=2) # 俄语区专属墙，稍微提到 2 篇就报警
            
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

def check_cis_telegram_search(game_name):
    """
    备用或补充方案：通过 t.me 的网页版预览或者第三方 Telegram 搜索引擎
    由于 Telegram 官方防爬极其严格，这里作为一个扩展槽位留存，目前主依赖 VK。
    如果有必要，可以接入 tgstat.ru 的非官方搜索。
    """
    pass

if __name__ == "__main__":
    print("Testing CIS OSINT...")
    res = check_cis_vk("Dota 2")
    print(res)
    res2 = check_cis_vk("PUBG")
    print(res2)

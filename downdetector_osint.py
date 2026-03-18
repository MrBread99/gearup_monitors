import requests
import json
import time

# 很多时候，直接访问 Downdetector.com 会遭遇极强的 Cloudflare 403 拦截（如刚才的测试结果）
# 作为专业爬虫/自动化工具，我们应该寻找它暴露出的非官方 API 或 RSS feed。
# Downdetector 并没有开放稳定的 JSON API 给免费用户，所以最佳方案是采用一个聚合平台或者第三方检测。
# 由于我们目的是“监控激增”，其实我们可以借用 IsTheServiceDown 或者类似无 Cloudflare 强阻挡的备用网站。

# 为了解决 403，我们要么使用代理池，要么使用无需极高验证的 RSS 源 (例如某些地区站点的 RSS)
# 或者退而求其次，如果遇到 403，我们在报告中注明。

# 这里我提供一个备用方案：使用 istheservicedown.com 抓取，它同样也是一个聚合了大量玩家报错的网站，且反爬较弱。
ITSD_GAME_MAP = {
    'Valorant': 'valorant',
    'League of Legends': 'league-of-legends',
    'APEX Legends': 'apex-legends',
    'CS2': 'counter-strike',
    'Fortnite': 'fortnite',
    'PUBG': 'playerunknown-s-battlegrounds-pubg',
    'Overwatch 2': 'overwatch',
    'Rainbow Six Siege': 'tom-clancy-s-rainbow-six-siege',
    'Dota 2': 'dota-2',
    'Call of Duty': 'call-of-duty'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
}

def check_downdetector_global(game_name):
    """
    为了绕过 Downdetector 极强的 403 (Cloudflare) 防护，
    这里采用 IsTheServiceDown.com 的类似逻辑，它是欧美另外一个极大的玩家报错聚合站。
    """
    slug = ITSD_GAME_MAP.get(game_name)
    if not slug:
        return None
        
    url = f"https://istheservicedown.com/problems/{slug}"
    
    try:
        from bs4 import BeautifulSoup
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找页面上的状态文字
            # 例如: "No problems at ...", "Possible problems at ...", "Problems at ..."
            status_element = soup.find('div', class_='service-status-alert')
            
            if status_element:
                status_text = status_element.text.strip().lower()
                
                # 如果包含 problems 但没有 no，说明有异常
                if "problems" in status_text and "no problems" not in status_text:
                    return {
                        'game': game_name,
                        'region': 'Global (Outage Aggregator)',
                        'country': 'Multiple',
                        'issue': f"🔥 [热度飙升] 🚨 玩家报错聚合网侦测到大量网络问题！",
                        'source_name': 'IsTheServiceDown',
                        'source_url': url
                    }
                    
    except Exception as e:
        print(f"[Outage Aggregator] 检测 {game_name} 时发生异常: {e}")
        
    return None

if __name__ == "__main__":
    # 测试脚本
    print("Testing Downdetector OSINT...")
    res = check_downdetector_global("Valorant")
    print("Valorant:", res)
    res2 = check_downdetector_global("League of Legends")
    print("LOL:", res2)

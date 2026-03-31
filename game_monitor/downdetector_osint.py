import requests
import json
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 很多时候，直接访问 Downdetector.com 会遭遇极强的 Cloudflare 403 拦截（如刚才的测试结果）
# 作为专业爬虫/自动化工具，我们应该寻找它暴露出的非官方 API 或 RSS feed。
# Downdetector 并没有开放稳定的 JSON API 给免费用户，所以最佳方案是采用一个聚合平台或者第三方检测。
# 由于我们目的是“监控激增”，其实我们可以借用 IsTheServiceDown 或者类似无 Cloudflare 强阻挡的备用网站。

# 为了解决 403，我们要么使用代理池，要么使用无需极高验证的 RSS 源 (例如某些地区站点的 RSS)
# 或者退而求其次，如果遇到 403，我们在报告中注明。

# ITSD 游戏 slug 映射 — 从统一游戏注册表 (game_registry.py) 加载
from game_registry import get_itsd_game_map
ITSD_GAME_MAP = get_itsd_game_map()

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
        
        if response.status_code != 200:
            print(f"[Outage Aggregator] IsTheServiceDown {game_name}: HTTP {response.status_code}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('itsd', url=url, status_code=response.status_code)
            except Exception:
                pass
            return None

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 查找页面上的状态文字
            # 例如: "No problems at ...", "Possible problems at ...", "Problems at ..."
            status_element = soup.find('div', class_='service-status-alert')
            
            if status_element:
                status_text = status_element.text.strip().lower()
                
                # istheservicedown 的典型文案有:
                # "No problems at ..." (无问题)
                # "Possible problems at ..." (轻微波动/少数人报错)
                # "Problems at ..." (明确的大面积故障)
                # "Massive outage at ..." (大规模宕机，有时会用这个词)
                
                # 为了极致降低误报，要求页面不仅显示 "problems"，还必须出现 "outage" 或 "massive" 这种高强度词汇
                # 或者它页面上的状态栏颜色（如果能抓到的话）是最高级别。
                
                has_definite_problems = (
                    "problems" in status_text and 
                    "no problems" not in status_text and 
                    "possible problems" not in status_text
                )
                
                # istheservicedown 的典型文案有:
                # "Problems detected" - 此时意味着有故障，但有时可能也只是小故障
                # 我们通过检查页面上的图表数据，或者更严格的短语来过滤
                
                # 进一步提升门槛：只有当状态文案明确包含 "massive" 或 "outage" 时才报警
                # 或者要求状态栏带有 'alert-danger' 这种红色的 class
                is_severe_outage = False
                
                if status_element.has_attr('class') and 'alert-danger' in status_element['class']:
                    is_severe_outage = True
                    
                if "massive" in status_text or "outage" in status_text:
                    is_severe_outage = True
                
                if has_definite_problems and is_severe_outage:
                    return {
                        'game': game_name,
                        'region': 'Global',
                        'country': 'Multiple',
                        'issue': f"🔥 玩家报错聚合网确认发生大面积宕机/拥堵！(已应用极高阈值)",
                        'source_name': 'IsTheServiceDown',
                        'source_url': url
                    }
                    
    except Exception as e:
        print(f"[Outage Aggregator] 检测 {game_name} 时发生异常: {e}")
        
    return None

if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
    # 测试脚本
    print("Testing Downdetector OSINT...")
    res = check_downdetector_global("Valorant")
    print("Valorant:", res)
    res2 = check_downdetector_global("Call of Duty")
    print("COD:", res2)

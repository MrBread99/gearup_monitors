import requests
from bs4 import BeautifulSoup
import time
import urllib.parse
import os
import sys

# 确保 utils/ 可以被 import（无论从哪个目录运行）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==========================================
# 区域配置与本地化关键词库
# ==========================================
KEYWORDS = {
    "TW": ["斷線", "爆ping", "卡頓", "連不上", "進不去", "伺服器", "馬鈴薯"],
    # Yahoo JP 实时搜索已废弃（JS 渲染 SPA，requests 无法获取任何数据）
    "KR": ["섭터짐", "핑", "렉", "접속불가", "튕김", "서버 다운"]
}

# 伪装请求头，防止被社区简单的反爬虫拦截
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8,ja;q=0.7,ko;q=0.6'
}

def analyze_text_for_issues(text_list, region, threshold=5):
    """
    分析文本列表中包含关键词的频率，超过阈值则认为有异常。
    阈值提高到 5 (原 3)，并且要求匹配到至少 2 个不同关键词，
    减少单一常见词（如"サーバー"/"서버"）导致的误报。
    """
    issue_count = 0
    matched_keywords = set()
    
    for text in text_list:
        for kw in KEYWORDS[region]:
            if kw in text:
                issue_count += 1
                matched_keywords.add(kw)
                break # 一条帖子只算一次异常

    # 要求至少匹配到 2 个不同关键词，避免单一词误报
    is_down = issue_count >= threshold and len(matched_keywords) >= 2
    return is_down, issue_count, list(matched_keywords)

# ==========================================
# 1. 台湾: 巴哈姆特 (Bahamut) 爬虫
# ==========================================
def check_taiwan_bahamut(game_name, bsn_id):
    """
    爬取巴哈姆特指定游戏哈啦板的第一页标题
    :param bsn_id: 游戏的巴哈板号 (例如：Valorant 是 37714)
    """
    url = f"https://forum.gamer.com.tw/B.php?bsn={bsn_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[TW] Bahamut {game_name}: HTTP {response.status_code}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('bahamut', url=url, status_code=response.status_code)
            except Exception:
                pass
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取帖子标题
        titles = [a.text for a in soup.select('.b-list__main__title')]
        
        is_down, count, matched = analyze_text_for_issues(titles, "TW")
        if is_down:
            return {
                "game": game_name,
                "region": "APAC",
                "country": "Taiwan",
                "issue": f"巴哈姆特玩家集中反馈异常 (匹配词: {', '.join(matched)}, 贴数: {count})",
                "source_name": "Bahamut",
                "source_url": url
            }
    except Exception as e:
        print(f"[TW] Failed to scrape Bahamut for {game_name}: {e}")
    return None

# ==========================================
# 注意：日本 Yahoo 实时搜索已废弃
# Yahoo JP 为 JS 渲染 SPA，requests 无法获取任何实际数据，
# 该数据源已删除，待后续接入 Twitter/X API 替代。
# ==========================================

# ==========================================
# 2. 韩国: DC Inside 爬虫
# ==========================================
def check_korea_dcinside(game_name, gallery_id, gallery_type='major'):
    """
    爬取韩国 DC Inside 指定游戏版块的最新帖子
    :param gallery_id: 画廊ID (例如：Valorant 是 valorant)
    :param gallery_type: 'major' (正规画廊) 或 'minor' (마이너画廊)
    """
    if not gallery_id:
        return None
    if gallery_type == 'minor':
        url = f"https://gall.dcinside.com/mgallery/board/lists/?id={gallery_id}"
    else:
        url = f"https://gall.dcinside.com/board/lists/?id={gallery_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[KR] DC Inside {game_name}: HTTP {response.status_code}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('dcinside_game', url=url, status_code=response.status_code)
            except Exception:
                pass
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取帖子标题
        titles = [a.text for a in soup.select('tr.us-post .gall_tit a')]
        
        is_down, count, matched = analyze_text_for_issues(titles, "KR")
        if is_down:
            return {
                "game": game_name,
                "region": "APAC",
                "country": "South Korea",
                "issue": f"DC Inside 玩家集中反馈异常 (匹配词: {', '.join(matched)}, 贴数: {count})",
                "source_name": "DC Inside",
                "source_url": url
            }
    except Exception as e:
        print(f"[KR] Failed to scrape DC Inside for {game_name}: {e}")
    return None

if __name__ == "__main__":
    # 测试用例：模拟运行监控
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    
    issues = []
    
    # 假设我们监控无畏契约 (Valorant)
    print("正在扫描亚太核心地区玩家社区...")
    
    # 测试巴哈姆特 (无畏契约版块 ID: 37714)
    tw_issue = check_taiwan_bahamut("Valorant", "37714")
    if tw_issue: issues.append(tw_issue)
        
    # Yahoo JP 已废弃（JS 渲染 SPA），已删除测试用例
        
    # 测试韩国 DC Inside
    kr_issue = check_korea_dcinside("Valorant", "valorant")
    if kr_issue: issues.append(kr_issue)
        
    if issues:
        print(f"🚨 发现 {len(issues)} 个区域的网络预警！")
        for i in issues:
            print(i)
    else:
        print("✅ 亚太地区社区目前情绪稳定，未发现大面积网络报错。")

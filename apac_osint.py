import requests
from bs4 import BeautifulSoup
import time
import urllib.parse

# ==========================================
# 区域配置与本地化关键词库
# ==========================================
KEYWORDS = {
    "TW": ["斷線", "爆ping", "卡頓", "連不上", "進不去", "伺服器", "馬鈴薯"],
    "JP": ["鯖落ち", "ラグい", "繋がらない", "落ちた", "通信エラー", "マッチしない"],
    "KR": ["섭터짐", "핑", "렉", "접속불가", "튕김", "서버 다운"]
}

# 伪装请求头，防止被社区简单的反爬虫拦截
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8,ja;q=0.7,ko;q=0.6'
}

def analyze_text_for_issues(text_list, region, threshold=3):
    """分析文本列表中包含关键词的频率，超过阈值则认为有异常"""
    issue_count = 0
    matched_keywords = set()
    
    for text in text_list:
        for kw in KEYWORDS[region]:
            if kw in text:
                issue_count += 1
                matched_keywords.add(kw)
                break # 一条帖子只算一次异常

    is_down = issue_count >= threshold
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
# 2. 日本: Yahoo 实时搜索 (抓取 Twitter 趋势)
# ==========================================
def check_japan_yahoo_realtime(game_name):
    """
    爬取日本 Yahoo 实时搜索，监控游戏名+鯖落ち相关的推文频率
    """
    # 搜索词: 游戏名 + 常见崩溃词
    search_query = f"{game_name} 鯖落ち OR {game_name} ラグ"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://search.yahoo.co.jp/realtime/search?p={encoded_query}"
    
    try:
        # 添加一个代理支持或者更复杂的Header以防被断开连接，同时降低超时时间
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取推文文本 (注：Yahoo DOM 结构常变，此处为通用 class 占位，需根据实际情况微调)
        tweets = [div.text for div in soup.select('.Tweet_body__text')] 
        
        is_down, count, matched = analyze_text_for_issues(tweets, "JP", threshold=5) # Twitter 数据量大，阈值调高
        if is_down:
            return {
                "game": game_name,
                "region": "APAC",
                "country": "Japan",
                "issue": f"日本 X(Twitter) 涌现大量网络故障反馈 (匹配词: {', '.join(matched)}, 样本数: {count})",
                "source_name": "Yahoo Realtime (Twitter)",
                "source_url": url
            }
    except requests.exceptions.ConnectionError:
        print(f"[JP] Failed to scrape Yahoo Realtime for {game_name}: Connection Reset/Aborted. May require VPN or proxy.")
    except Exception as e:
        print(f"[JP] Failed to scrape Yahoo Realtime for {game_name}: {e}")
    return None

# ==========================================
# 3. 韩国: DC Inside 爬虫
# ==========================================
def check_korea_dcinside(game_name, gallery_id):
    """
    爬取韩国 DC Inside 指定游戏版块的最新帖子
    :param gallery_id: 画廊ID (例如：Valorant 是 valorant)
    """
    url = f"https://gall.dcinside.com/board/lists/?id={gallery_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
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
    sys.stdout.reconfigure(encoding='utf-8')
    
    issues = []
    
    # 假设我们监控无畏契约 (Valorant)
    print("正在扫描亚太核心地区玩家社区...")
    
    # 测试巴哈姆特 (无畏契约版块 ID: 37714)
    tw_issue = check_taiwan_bahamut("Valorant", "37714")
    if tw_issue: issues.append(tw_issue)
        
    # 测试日本 Yahoo 实时
    jp_issue = check_japan_yahoo_realtime("Valorant")
    if jp_issue: issues.append(jp_issue)
        
    # 测试韩国 DC Inside
    kr_issue = check_korea_dcinside("Valorant", "valorant")
    if kr_issue: issues.append(kr_issue)
        
    if issues:
        print(f"🚨 发现 {len(issues)} 个区域的网络预警！")
        for i in issues:
            print(i)
    else:
        print("✅ 亚太地区社区目前情绪稳定，未发现大面积网络报错。")

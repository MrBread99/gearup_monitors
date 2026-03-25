import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.google_client import google_search
from utils.sentiment_summarizer import summarize_sentiment

# ==========================================
# 台湾区品牌舆情监控（巴哈姆特 + PTT）
# ==========================================
# 监控台湾玩家对 GearUP Booster 及竞品加速器的讨论。
# ==========================================

# 搜索关键词
SEARCH_BRANDS = {
    'GearUP': ['GearUP', 'GearUP Booster', '網易加速器'],
    'ExitLag': ['ExitLag'],
    'LagoFast': ['LagoFast'],
}

# 加速器相关繁体中文关键词
BOOSTER_KEYWORDS_TW = [
    "加速器", "VPN", "降ping", "遊戲加速", "網路優化",
    "連線品質", "網路加速"
]

NEGATIVE_TW = ["爛", "垃圾", "騙錢", "沒用", "浪費", "退費", "差評", "難用", "不推"]
POSITIVE_TW = ["推薦", "好用", "穩定", "神器", "值得", "讚", "不錯", "便宜"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8'
}  # Retained for search_bahamut


def search_bahamut(query):
    """搜索巴哈姆特全站"""
    encoded = urllib.parse.quote(query)
    url = f"https://forum.gamer.com.tw/search.php?q={encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.search-result__item, .b-list__main__title'):
            title = item.get_text(strip=True)
            link_tag = item.find('a') if item.name != 'a' else item
            link = link_tag.get('href', '') if link_tag else ''
            if title:
                results.append({
                    'title': title,
                    'url': f"https://forum.gamer.com.tw{link}" if link.startswith('/') else link,
                    'source': 'Bahamut'
                })

        return results[:20]
    except Exception as e:
        print(f"[TW] 搜索巴哈姆特 '{query}' 失败: {e}")
        return []


def search_ptt(query):
    """搜索 PTT Web 版（通过 Google site:ptt.cc 间接搜索）"""
    raw = google_search(query, site='ptt.cc')
    return [{'title': r['title'], 'url': r['url'], 'source': 'PTT'} for r in raw]


def analyze_sentiment_tw(posts):
    """分析繁体中文帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        title = post.get('title', '')
        neg = sum(1 for kw in NEGATIVE_TW if kw in title)
        pos = sum(1 for kw in POSITIVE_TW if kw in title)

        if neg > pos:
            post['sentiment'] = 'negative'
            negative.append(post)
        elif pos > neg:
            post['sentiment'] = 'positive'
            positive.append(post)
        else:
            post['sentiment'] = 'neutral'
            neutral.append(post)

    return negative, positive, neutral


def check_taiwan_brand():
    """主检测函数：台湾区品牌舆情"""
    issues = []
    all_posts = []

    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索巴哈姆特: '{q}'...")
            all_posts.extend(search_bahamut(q))
            print(f"  - 正在搜索 PTT: '{q}'...")
            all_posts.extend(search_ptt(q))

    if not all_posts:
        return issues

    # 去重
    seen = set()
    unique = []
    for p in all_posts:
        key = p['title'][:30]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    negative, positive, neutral = analyze_sentiment_tw(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"负面 {len(negative)} 篇")
    if positive: parts.append(f"正面 {len(positive)} 篇")
    if neutral: parts.append(f"中性 {len(neutral)} 篇")

    issue_desc = f"🇹🇼 台湾区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

    if negative:
        top = negative[0]
        issue_desc += f"\n    ⚠️ 负面帖: \"{top['title'][:50]}\" ({top['source']})"

    # AI 舆情总结
    ai_summary = summarize_sentiment('GearUP Booster', 'Taiwan', negative, positive, neutral)
    if ai_summary:
        issue_desc += f"\n    {ai_summary.replace(chr(10), chr(10) + '    ')}"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'APAC',
        'country': 'Taiwan',
        'issue': issue_desc,
        'source_name': 'Bahamut / PTT',
        'source_url': 'https://forum.gamer.com.tw/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Taiwan Brand Monitor...")
    results = check_taiwan_brand()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无结果")

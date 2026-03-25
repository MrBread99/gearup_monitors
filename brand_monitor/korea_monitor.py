import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# 韩国区品牌舆情监控（DC Inside + Naver）
# ==========================================
# 监控韩国玩家对 GearUP Booster 及竞品加速器的讨论。
# ==========================================

SEARCH_BRANDS = {
    'GearUP': ['GearUP', 'GearUP Booster', '기어업 부스터'],
    'ExitLag': ['ExitLag', '엑싯랙'],
    'LagoFast': ['LagoFast'],
}

NEGATIVE_KR = ["쓰레기", "사기", "환불", "별로", "나쁜", "안됨", "느림", "효과없음"]
POSITIVE_KR = ["추천", "좋음", "최고", "효과있음", "빠름", "안정", "핑감소"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8'
}


def search_naver_blog(query):
    """通过 Naver 搜索博客和论坛帖子"""
    encoded = urllib.parse.quote(query)
    url = f"https://search.naver.com/search.naver?where=article&query={encoded}&sm=tab_opt&sort=1"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.total_tit, .api_txt_lines.total_tit'):
            title = item.get_text(strip=True)
            link = item.get('href', '')
            if title:
                results.append({
                    'title': title,
                    'url': link,
                    'source': 'Naver'
                })

        return results[:15]
    except Exception as e:
        print(f"[KR] 搜索 Naver '{query}' 失败: {e}")
        return []


def search_dcinside_search(query):
    """搜索 DC Inside 全站"""
    encoded = urllib.parse.quote(query)
    url = f"https://search.dcinside.com/combine/q/{encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.result_tit a, .tit_txt'):
            title = item.get_text(strip=True)
            link = item.get('href', '')
            if title:
                results.append({
                    'title': title,
                    'url': link if link.startswith('http') else f"https://search.dcinside.com{link}",
                    'source': 'DC Inside'
                })

        return results[:15]
    except Exception as e:
        print(f"[KR] 搜索 DC Inside '{query}' 失败: {e}")
        return []


def analyze_sentiment_kr(posts):
    """分析韩语帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        title = post.get('title', '')
        neg = sum(1 for kw in NEGATIVE_KR if kw in title)
        pos = sum(1 for kw in POSITIVE_KR if kw in title)

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


def check_korea_brand():
    """主检测函数：韩国区品牌舆情"""
    issues = []
    all_posts = []

    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 Naver: '{q}'...")
            all_posts.extend(search_naver_blog(q))
            print(f"  - 正在搜索 DC Inside: '{q}'...")
            all_posts.extend(search_dcinside_search(q))

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

    negative, positive, neutral = analyze_sentiment_kr(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"부정 {len(negative)} 건")
    if positive: parts.append(f"긍정 {len(positive)} 건")
    if neutral: parts.append(f"중립 {len(neutral)} 건")

    issue_desc = f"🇰🇷 韩国区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

    if negative:
        top = negative[0]
        issue_desc += f"\n    ⚠️ 负面帖: \"{top['title'][:50]}\" ({top['source']})"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'APAC',
        'country': 'South Korea',
        'issue': issue_desc,
        'source_name': 'Naver / DC Inside',
        'source_url': 'https://search.naver.com/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Korea Brand Monitor...")
    results = check_korea_brand()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无结果")

import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# 日本品牌舆情监控
# ==========================================
# 覆盖渠道：
# 1. 5ch（旧2ch）：日本最大匿名论坛，通过 Google site search 间接搜索
# 2. Google 日语搜索：覆盖 4Gamer、GameWith、Price.com 等日本本土媒体和评价网站
# 3. Reddit 日本相关 subreddit
# ==========================================

SEARCH_BRANDS = {
    'GearUP': ['GearUP Booster', 'GearUP ゲームブースター', 'ゲームブースター GearUP'],
    'ExitLag': ['ExitLag', 'ExitLag 評判'],
    'LagoFast': ['LagoFast'],
}

# 加速器相关日语搜索词
BOOSTER_KEYWORDS_JP = [
    "ゲーム VPN おすすめ",
    "ゲーム 加速器 おすすめ",
    "ping下げる ツール",
    "ゲームブースター 比較",
    "ラグ解消 ソフト",
]

# Reddit 日本相关 subreddit
JP_SUBREDDITS = [
    'japan',
    'japanlife',
    'japangaming',
    'PCgaming',  # 日本玩家也在此活跃
]

# 日语情感关键词
JP_NEGATIVE = [
    "詐欺", "ゴミ", "最悪", "微妙", "ダメ", "使えない", "意味ない",
    "ウイルス", "効果なし", "金の無駄", "インストールするな", "やめとけ",
    "改悪", "不安定", "重い", "遅い", "解約", "返金",
]
JP_POSITIVE = [
    "おすすめ", "神", "最高", "良い", "便利", "安定", "効果あり",
    "快適", "使いやすい", "コスパ", "軽い", "速い", "改善",
    "ラグ解消", "ping下がった", "買い",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8'
}


def search_5ch_via_google(query):
    """通过 Google site:5ch.net 搜索 5ch 论坛内容"""
    encoded = urllib.parse.quote(f"site:5ch.net {query}")
    url = f"https://www.google.com/search?q={encoded}&tbs=qdr:m&num=10"

    results = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        for h3 in soup.select('h3'):
            title = h3.get_text(strip=True)
            parent_a = h3.find_parent('a')
            link = parent_a.get('href', '') if parent_a else ''
            if title and '5ch' in link:
                results.append({
                    'title': title,
                    'url': link,
                    'source': '5ch'
                })

        return results[:10]
    except Exception as e:
        print(f"[JP] 搜索 5ch '{query}' 失败: {e}")
        return []


def search_google_japan(query):
    """Google 日语搜索（覆盖 4Gamer, GameWith, Price.com 等）"""
    encoded = urllib.parse.quote(query)
    url = (
        f"https://www.google.co.jp/search?q={encoded}"
        f"&lr=lang_ja&tbs=qdr:m&num=10"
    )

    results = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            # fallback to google.com
            url = f"https://www.google.com/search?q={encoded}&lr=lang_ja&tbs=qdr:m&num=10"
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                return []

        soup = BeautifulSoup(response.text, 'html.parser')
        for h3 in soup.select('h3'):
            title = h3.get_text(strip=True)
            parent_a = h3.find_parent('a')
            link = parent_a.get('href', '') if parent_a else ''
            if title and link:
                results.append({
                    'title': title,
                    'url': link,
                    'source': 'Google JP'
                })

        return results[:10]
    except Exception as e:
        print(f"[JP] Google JP 搜索 '{query}' 失败: {e}")
        return []


def search_reddit_japan(keyword):
    """搜索日本相关 subreddit"""
    posts = []
    encoded = requests.utils.quote(keyword)

    for sub in JP_SUBREDDITS:
        url = (
            f"https://www.reddit.com/r/{sub}/search.json"
            f"?q={encoded}&restrict_sr=on&sort=new&t=month&limit=25"
        )
        try:
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                children = data.get('data', {}).get('children', [])
                for child in children:
                    post = child.get('data', {})
                    posts.append({
                        'title': post.get('title', ''),
                        'text': post.get('selftext', ''),
                        'subreddit': post.get('subreddit', ''),
                        'score': post.get('ups', 0),
                        'comments': post.get('num_comments', 0),
                        'url': f"https://www.reddit.com{post.get('permalink', '')}",
                        'source': f'r/{sub}'
                    })
            elif response.status_code == 429:
                break
        except Exception as e:
            print(f"[JP] r/{sub} 搜索 '{keyword}' 失败: {e}")

    return posts


def analyze_sentiment_jp(posts):
    """分析日语帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        content = post.get('title', '') + ' ' + post.get('text', '')

        neg = sum(1 for kw in JP_NEGATIVE if kw in content)
        pos = sum(1 for kw in JP_POSITIVE if kw in content)

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


def check_japan_brand():
    """主检测函数：日本品牌舆情"""
    issues = []
    all_posts = []

    # 1. 5ch 搜索（通过 Google）
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 5ch: '{q}'...")
            all_posts.extend(search_5ch_via_google(q))

    # 2. Google 日语搜索
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 Google JP: '{q}'...")
            all_posts.extend(search_google_japan(q))

    # 加速器通用搜索词
    for kw in BOOSTER_KEYWORDS_JP:
        print(f"  - 正在搜索 Google JP: '{kw}'...")
        all_posts.extend(search_google_japan(kw))

    # 3. Reddit 日本 subreddit
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 Reddit JP: '{q}'...")
            all_posts.extend(search_reddit_japan(q))

    if not all_posts:
        return issues

    # 去重
    seen = set()
    unique = []
    for p in all_posts:
        key = p.get('title', '')[:30] + p.get('source', '')
        if key not in seen:
            seen.add(key)
            unique.append(p)

    negative, positive, neutral = analyze_sentiment_jp(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"ネガティブ {len(negative)}")
    if positive: parts.append(f"ポジティブ {len(positive)}")
    if neutral: parts.append(f"中立 {len(neutral)}")

    issue_desc = f"🇯🇵 日本区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

    # 按来源统计
    source_counts = {}
    for p in unique:
        src = p.get('source', 'Unknown')
        source_counts[src] = source_counts.get(src, 0) + 1
    source_summary = ', '.join(f"{k}: {v}" for k, v in source_counts.items())
    issue_desc += f"\n    📍 来源分布: {source_summary}"

    if negative:
        top = negative[0]
        issue_desc += f"\n    ⚠️ 负面帖: \"{top['title'][:50]}\" ({top.get('source', '')})"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'APAC',
        'country': 'Japan',
        'issue': issue_desc,
        'source_name': '5ch / Google JP / Reddit JP',
        'source_url': 'https://www.google.co.jp/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Japan Brand Monitor...")
    results = check_japan_brand()
    if results:
        for r in results:
            print(r['issue'])
    else:
        print("無日本区相関討論。")

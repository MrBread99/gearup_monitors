import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# 中东/阿拉伯语区品牌舆情监控
# ==========================================
# 覆盖渠道：
# 1. Reddit 中东相关 subreddit（r/saudiarabia, r/UAE, r/egypt 等）
# 2. Google 阿拉伯语搜索（间接覆盖阿拉伯论坛和博客）
# 3. Reddit 全站阿拉伯语关键词搜索
# ==========================================

# 监控品牌的阿拉伯语搜索词
SEARCH_BRANDS = {
    'GearUP': ['GearUP Booster', 'مسرع العاب GearUP', 'جير اب'],
    'ExitLag': ['ExitLag', 'اكزت لاق'],
    'LagoFast': ['LagoFast'],
}

# 中东相关 Reddit 子版块（搜索加速器/VPN 话题）
MIDEAST_SUBREDDITS = [
    'saudiarabia',
    'UAE',
    'egypt',
    'jordan',
    'kuwait',
    'bahrain',
    'qatar',
    'oman',
    'iraq',
    'lebanon',
]

# 加速器相关搜索关键词（在中东 subreddit 中搜索）
GAMING_KEYWORDS_EN = [
    "game booster", "VPN gaming", "reduce ping", "lag fix",
    "game accelerator", "ping booster"
]

# 阿拉伯语情感关键词
AR_NEGATIVE = [
    "نصب", "احتيال", "سيء", "ما ينفع", "ما يشتغل", "خرب",
    "ضعيف", "فلوس ضايعة", "لا تشتري", "نصابين", "غالي",
    "مشكلة", "سرقة", "فيروس"
]
AR_POSITIVE = [
    "ممتاز", "أفضل", "رهيب", "يستاهل", "أنصح", "حلو",
    "شغال", "نزل البنق", "خفض البنق", "مستقر", "سريع",
    "يشتغل", "زين", "قوي"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ar,en-US;q=0.9'
}


def search_reddit_mideast_subs(keyword, hours_window=24):
    """搜索中东相关 subreddit 中的加速器讨论"""
    posts = []
    encoded = requests.utils.quote(keyword)

    for sub in MIDEAST_SUBREDDITS:
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
                break  # 被限流则停止
        except Exception as e:
            print(f"[MidEast] r/{sub} 搜索 '{keyword}' 失败: {e}")

    return posts


def search_reddit_arabic(query, hours_window=24):
    """Reddit 全站搜索阿拉伯语关键词"""
    posts = []
    encoded = requests.utils.quote(query)
    url = (
        f"https://www.reddit.com/search.json"
        f"?q={encoded}&sort=new&t=month&limit=50"
    )

    try:
        response = requests.get(
            url,
            headers={'User-Agent': 'OSINT-Monitor/2.1'},
            timeout=15
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
                    'source': 'Reddit AR'
                })
    except Exception as e:
        print(f"[MidEast] Reddit 阿拉伯语搜索 '{query}' 失败: {e}")

    return posts


def search_google_arabic(query):
    """通过 Google 搜索阿拉伯语论坛和博客内容"""
    encoded = urllib.parse.quote(query)
    url = (
        f"https://www.google.com/search?q={encoded}"
        f"&lr=lang_ar&tbs=qdr:m&num=10"  # 阿拉伯语、最近一个月
    )

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
            if title and link:
                results.append({
                    'title': title,
                    'url': link,
                    'source': 'Google AR'
                })

        return results[:10]
    except Exception as e:
        print(f"[MidEast] Google 阿拉伯语搜索 '{query}' 失败: {e}")
        return []


def analyze_sentiment_ar(posts):
    """分析阿拉伯语帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        content = post.get('title', '') + ' ' + post.get('text', '')

        neg = sum(1 for kw in AR_NEGATIVE if kw in content)
        pos = sum(1 for kw in AR_POSITIVE if kw in content)

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


def check_mideast_brand():
    """主检测函数：中东区品牌舆情"""
    issues = []
    all_posts = []

    # 1. 在中东 subreddit 搜索英文加速器关键词
    for kw in GAMING_KEYWORDS_EN:
        print(f"  - 正在搜索中东 subreddit: '{kw}'...")
        all_posts.extend(search_reddit_mideast_subs(kw))

    # 2. Reddit 全站搜索阿拉伯语品牌词
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            if any('\u0600' <= c <= '\u06FF' for c in q):  # 阿拉伯语字符
                print(f"  - 正在搜索 Reddit 阿拉伯语: '{q}'...")
                all_posts.extend(search_reddit_arabic(q))

    # 3. Google 阿拉伯语搜索
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 Google 阿拉伯语: '{q}'...")
            all_posts.extend(search_google_arabic(q))

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

    negative, positive, neutral = analyze_sentiment_ar(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"سلبي {len(negative)}")
    if positive: parts.append(f"إيجابي {len(positive)}")
    if neutral: parts.append(f"محايد {len(neutral)}")

    issue_desc = f"🇸🇦 中东区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

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
        'region': 'MENA',
        'country': 'Middle East',
        'issue': issue_desc,
        'source_name': 'Reddit MENA / Google AR',
        'source_url': 'https://www.reddit.com/r/saudiarabia/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Middle East Brand Monitor...")
    results = check_mideast_brand()
    if results:
        for r in results:
            print(r['issue'])
    else:
        print("无中东区相关讨论。")

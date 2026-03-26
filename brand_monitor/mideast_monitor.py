import requests
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get
from utils.google_client import google_search
from utils.sentiment_summarizer import summarize_sentiment

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
            response = reddit_get(url)
            if response is None:
                continue
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
        response = reddit_get(url)
        if response is None:
            return posts
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
    raw = google_search(query, lang_code='ar')
    return [{'title': r['title'], 'url': r['url'], 'source': 'Google AR'} for r in raw]


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
    if negative: parts.append(f"负面 {len(negative)} 篇")
    if positive: parts.append(f"正面 {len(positive)} 篇")
    if neutral: parts.append(f"中性 {len(neutral)} 篇")

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

    # AI 舆情总结
    ai_summary = summarize_sentiment('GearUP Booster', 'Middle East', negative, positive, neutral)
    if ai_summary:
        issue_desc += f"\n    {ai_summary.replace(chr(10), chr(10) + '    ')}"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'MENA',
        'country': 'Middle East',
        'alert_type': 'brand_monitor',
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
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无中东区相关讨论。")

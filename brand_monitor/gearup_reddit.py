import requests
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get

# ==========================================
# GearUP Booster Reddit 全站舆情监控
# ==========================================
# 由于 r/GearUPBooster 已被封禁，本模块通过 Reddit 全站搜索
# 抓取所有提到 GearUP Booster 的帖子和讨论，进行舆情分析。
# ==========================================

# 搜索关键词组合
SEARCH_QUERIES = [
    "GearUP Booster",
    "GearUP game booster",
]

# 情感分析关键词
NEGATIVE_KEYWORDS = [
    "SCAM", "VIRUS", "MALWARE", "FAKE", "TERRIBLE", "WORST", "TRASH",
    "GARBAGE", "USELESS", "DOESN'T WORK", "DOESNT WORK", "DON'T BUY",
    "DONT BUY", "WASTE", "REFUND", "UNINSTALL", "SPYWARE", "BLOATWARE",
    "SLOW", "WORSE", "BAD", "HORRIBLE", "AWFUL",
    # 中文负面
    "骗子", "垃圾", "骗钱", "没用", "卸载", "差评", "坑", "恶心",
]

POSITIVE_KEYWORDS = [
    "GREAT", "AMAZING", "AWESOME", "LOVE", "BEST", "RECOMMEND",
    "WORKS WELL", "HELPED", "IMPROVED", "GOOD", "EXCELLENT",
    "FANTASTIC", "PERFECT", "LEGIT",
    # 中文正面
    "好用", "推荐", "不错", "牛", "降低延迟",
]



def search_reddit_global(query, hours_window=24):
    """
    通过 Reddit 全站搜索 API 搜索包含指定关键词的帖子。
    使用 t=day 获取最近 24 小时的结果（舆情监控比故障监控时间窗口更长）。
    """
    posts = []
    encoded_query = requests.utils.quote(query)
    url = (
        f"https://www.reddit.com/search.json"
        f"?q={encoded_query}&sort=new&t=day&limit=100"
    )

    try:
        response = reddit_get(url)
        if response is None:
            return posts
        if response.status_code == 200:
            data = response.json()
            children = data.get('data', {}).get('children', [])
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_window)

            for child in children:
                post = child.get('data', {})
                post_time = datetime.fromtimestamp(
                    post.get('created_utc', 0), timezone.utc
                )
                if post_time > cutoff:
                    posts.append({
                        'title': post.get('title', ''),
                        'text': post.get('selftext', ''),
                        'subreddit': post.get('subreddit', ''),
                        'score': post.get('ups', 0),
                        'comments': post.get('num_comments', 0),
                        'url': f"https://www.reddit.com{post.get('permalink', '')}",
                        'created': post_time.strftime('%Y-%m-%d %H:%M'),
                        'author': post.get('author', ''),
                    })
        elif response.status_code == 429:
            print("[GearUP Reddit] 被限流，稍后重试")
        else:
            print(f"[GearUP Reddit] HTTP {response.status_code}")
    except Exception as e:
        print(f"[GearUP Reddit] 搜索 '{query}' 时出错: {e}")

    return posts


def analyze_sentiment(posts):
    """
    对帖子进行简单的情感分析，返回分类结果。
    """
    negative_posts = []
    positive_posts = []
    neutral_posts = []

    for post in posts:
        content = (post['title'] + ' ' + post['text']).upper()

        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content)
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content)

        if neg_count > pos_count:
            post['sentiment'] = 'negative'
            post['matched_keywords'] = [kw for kw in NEGATIVE_KEYWORDS if kw in content]
            negative_posts.append(post)
        elif pos_count > neg_count:
            post['sentiment'] = 'positive'
            post['matched_keywords'] = [kw for kw in POSITIVE_KEYWORDS if kw in content]
            positive_posts.append(post)
        else:
            post['sentiment'] = 'neutral'
            post['matched_keywords'] = []
            neutral_posts.append(post)

    return negative_posts, positive_posts, neutral_posts


def check_gearup_reddit(hours_window=24):
    """
    主检测函数：搜索 Reddit 全站，汇总 GearUP Booster 相关舆情。
    """
    issues = []
    all_posts = []

    for query in SEARCH_QUERIES:
        print(f"  - 正在搜索 Reddit: '{query}'...")
        results = search_reddit_global(query, hours_window)
        all_posts.extend(results)

    # 去重（同一帖子可能被多个关键词搜到）
    seen_urls = set()
    unique_posts = []
    for post in all_posts:
        if post['url'] not in seen_urls:
            seen_urls.add(post['url'])
            unique_posts.append(post)

    if not unique_posts:
        return issues

    # 情感分析
    negative, positive, neutral = analyze_sentiment(unique_posts)

    total = len(unique_posts)
    summary_parts = []

    if negative:
        summary_parts.append(f"负面 {len(negative)} 篇")
    if positive:
        summary_parts.append(f"正面 {len(positive)} 篇")
    if neutral:
        summary_parts.append(f"中性 {len(neutral)} 篇")

    summary = f"过去{hours_window}h 共 {total} 篇提及 ({', '.join(summary_parts)})"

    # 高热度帖子（score > 10 或评论 > 5）
    hot_posts = [p for p in unique_posts if p['score'] > 10 or p['comments'] > 5]

    # 拼接报警
    issue_desc = f"📊 GearUP Booster Reddit 舆情: {summary}"

    if negative:
        top_neg = sorted(negative, key=lambda x: x['score'], reverse=True)[0]
        issue_desc += f"\n    ⚠️ 最热负面帖: \"{top_neg['title'][:60]}\" (r/{top_neg['subreddit']}, ↑{top_neg['score']})"

    if hot_posts:
        top_hot = sorted(hot_posts, key=lambda x: x['score'], reverse=True)[0]
        issue_desc += f"\n    🔥 最热帖子: \"{top_hot['title'][:60]}\" (r/{top_hot['subreddit']}, ↑{top_hot['score']})"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'Global',
        'country': '',
        'issue': issue_desc,
        'source_name': 'Reddit Global Search',
        'source_url': 'https://www.reddit.com/search/?q=GearUP+Booster&sort=new&t=day'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing GearUP Reddit Monitor...")
    results = check_gearup_reddit()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("过去 24 小时无 GearUP 相关讨论。")

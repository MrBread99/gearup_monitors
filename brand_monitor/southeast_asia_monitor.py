import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get
from utils.google_client import google_search

# ==========================================
# 东南亚品牌舆情监控
# ==========================================
# 覆盖渠道：
# 1. 越南: Tinhte.vn（越南最大科技论坛）+ Google 越南语搜索
# 2. 菲律宾: Reddit r/Philippines, r/PHGamers + Google 菲律宾语搜索
# 3. 印尼: Google 印尼语搜索（覆盖 Kaskus 等本土论坛）+ Reddit r/indonesia
# 4. 泰国: Reddit r/Thailand + Google 泰语搜索
# 5. Reddit 东南亚游戏社区
# ==========================================

SEARCH_BRANDS = {
    'GearUP': ['GearUP Booster'],
    'ExitLag': ['ExitLag'],
    'LagoFast': ['LagoFast'],
}

# 东南亚 Reddit 子版块
SEA_SUBREDDITS = [
    'Philippines', 'PHGamers',
    'indonesia', 'IndoGaming',
    'Thailand',
    'vietnam', 'VietNam',
    'Malaysia', 'MalaysianGamers',
    'singapore',
]

# 各语言情感关键词
VI_NEGATIVE = ["LỪA ĐẢO", "DỞ", "TỆ", "KHÔNG NÊN MUA", "PHÍ TIỀN", "RÁC", "VÔ DỤNG"]
VI_POSITIVE = ["HAY", "TỐT", "ĐÁNG MUA", "GIẢM PING", "MƯỢT", "ỔN ĐỊNH", "KHUYÊN DÙNG"]

TL_NEGATIVE = ["PANGIT", "BASURA", "HUWAG BILHIN", "SCAM", "WALANG KWENTA", "SAYANG PERA"]
TL_POSITIVE = ["MAGANDA", "SULIT", "GANDA", "WORTH IT", "OKAY NAMAN", "GOODS"]

ID_NEGATIVE = ["PENIPUAN", "JELEK", "SAMPAH", "JANGAN BELI", "BUANG UANG", "GAK GUNA", "ZONK"]
ID_POSITIVE = ["BAGUS", "MANTAP", "RECOMMENDED", "WORTH IT", "LANCAR", "KEREN", "SMOOTH"]

TH_NEGATIVE = ["ห่วย", "แย่", "โกง", "ไม่ดี", "เสียเงิน", "ไร้ประโยชน์"]
TH_POSITIVE = ["ดี", "เยี่ยม", "แนะนำ", "คุ้ม", "ลดปิง", "เร็ว", "สุดยอด"]

ALL_NEGATIVE = VI_NEGATIVE + TL_NEGATIVE + ID_NEGATIVE + TH_NEGATIVE + [
    "SCAM", "TRASH", "GARBAGE", "WORST", "TERRIBLE", "USELESS"
]
ALL_POSITIVE = VI_POSITIVE + TL_POSITIVE + ID_POSITIVE + TH_POSITIVE + [
    "GREAT", "AMAZING", "RECOMMEND", "BEST", "WORKS"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
}  # Retained for search_tinhte


def search_reddit_sea(keyword):
    """搜索东南亚相关 subreddit"""
    posts = []
    encoded = requests.utils.quote(keyword)

    for sub in SEA_SUBREDDITS:
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
                break
        except Exception as e:
            print(f"[SEA] r/{sub} 搜索 '{keyword}' 失败: {e}")

    return posts


def search_tinhte(query):
    """搜索 Tinhte.vn（越南最大科技论坛）"""
    encoded = urllib.parse.quote(query)
    url = f"https://tinhte.vn/search/?q={encoded}&o=date"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('h3.contentRow-title a, .listBlock.main h3 a'):
            title = item.get_text(strip=True)
            link = item.get('href', '')
            if title:
                results.append({
                    'title': title,
                    'url': f"https://tinhte.vn{link}" if link.startswith('/') else link,
                    'source': 'Tinhte.vn'
                })

        return results[:15]
    except Exception as e:
        print(f"[SEA] 搜索 Tinhte '{query}' 失败: {e}")
        return []


def search_google_local(query, lang_code):
    """通过 Google 搜索本地语言内容"""
    raw = google_search(query, lang_code=lang_code)
    return [{'title': r['title'], 'url': r['url'], 'source': f'Google ({lang_code})'} for r in raw]


def analyze_sentiment_sea(posts):
    """分析东南亚多语言帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        content = (post.get('title', '') + ' ' + post.get('text', '')).upper()

        neg = sum(1 for kw in ALL_NEGATIVE if kw in content)
        pos = sum(1 for kw in ALL_POSITIVE if kw in content)

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


def check_sea_brand():
    """主检测函数：东南亚品牌舆情"""
    issues = []
    all_posts = []

    # 1. Reddit 东南亚 subreddit 搜索
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索东南亚 subreddit: '{q}'...")
            all_posts.extend(search_reddit_sea(q))

    # 2. Tinhte.vn 越南论坛
    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 Tinhte.vn: '{q}'...")
            all_posts.extend(search_tinhte(q))

    # 3. Google 各语言搜索
    sea_searches = [
        ('GearUP Booster đánh giá', 'vi'),        # 越南语
        ('giảm ping game GearUP', 'vi'),
        ('GearUP Booster review tagalog', 'tl'),   # 菲律宾语
        ('GearUP Booster review indonesia', 'id'),  # 印尼语
        ('game booster kurangi lag', 'id'),
        ('GearUP Booster รีวิว', 'th'),             # 泰语
    ]

    for query, lang in sea_searches:
        print(f"  - 正在搜索 Google ({lang}): '{query}'...")
        all_posts.extend(search_google_local(query, lang))

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

    negative, positive, neutral = analyze_sentiment_sea(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"负面 {len(negative)}")
    if positive: parts.append(f"正面 {len(positive)}")
    if neutral: parts.append(f"中性 {len(neutral)}")

    issue_desc = f"🌏 东南亚加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

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
        'region': 'Southeast Asia',
        'country': '',
        'issue': issue_desc,
        'source_name': 'SEA Communities',
        'source_url': 'https://tinhte.vn/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Southeast Asia Brand Monitor...")
    results = check_sea_brand()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无东南亚区相关讨论。")

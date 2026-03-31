import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL
from utils.sentiment_summarizer import summarize_sentiment

# ==========================================
# 韩国区品牌舆情监控（DC Inside + Naver Search Open API）
# ==========================================
# 监控韩国玩家对 GearUP Booster 及竞品加速器的讨论。
#
# Naver Search Open API（官方，免费）:
#   申请地址: https://developers.naver.com/apps/#/register
#   需在 GitHub Secrets 中配置:
#     NAVER_CLIENT_ID  — 应用 Client ID
#     NAVER_CLIENT_SECRET — 应用 Client Secret
#   未配置时自动跳过 Naver 搜索（不会崩溃）。
# ==========================================

SEARCH_BRANDS = {
    'GearUP': ['GearUP', 'GearUP Booster', '기어업 부스터'],
    'ExitLag': ['ExitLag', '엑싯랙'],
    'LagoFast': ['LagoFast'],
}

NEGATIVE_KR = ["쓰레기", "사기", "환불", "별로", "나쁜", "안됨", "느림", "효과없음"]
POSITIVE_KR = ["추천", "좋음", "최고", "효과있음", "빠름", "안정", "핑감소"]

# Naver Search Open API 认证（从环境变量读取）
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8'
}


def search_naver_blog(query):
    """
    通过 Naver Search Open API 搜索博客和咖啡帖。
    官方 API 端点: https://openapi.naver.com/v1/search/blog.json
    需配置 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 环境变量。
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print(f"[KR] Naver API 未配置（缺少 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET），跳过 Naver 搜索")
        return []

    results = []
    # 同时搜索博客 (blog) 和咖啡帖 (cafearticle)
    for search_type in ('blog', 'cafearticle'):
        url = 'https://openapi.naver.com/v1/search/{}.json'.format(search_type)
        params = {
            'query': query,
            'display': 10,
            'sort': 'date',   # 最新优先
        }
        api_headers = {
            'X-Naver-Client-Id': NAVER_CLIENT_ID,
            'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
        }
        try:
            response = requests.get(url, params=params, headers=api_headers, timeout=15)
            if response.status_code == 401:
                print(f"[KR] Naver API 认证失败（{search_type}），请检查 NAVER_CLIENT_ID/SECRET")
                try:
                    from utils.notifier import report_scrape_block
                    report_scrape_block('naver_api_401', url=url, status_code=401)
                except Exception:
                    pass
                break
            if response.status_code != 200:
                print(f"[KR] Naver API ({search_type}) HTTP {response.status_code}: {query}")
                try:
                    from utils.notifier import report_scrape_block
                    report_scrape_block('naver_api_other', url=url, status_code=response.status_code)
                except Exception:
                    pass
                continue

            data = response.json()
            for item in data.get('items', []):
                # 移除 HTML 标签（API 返回带 <b> 标签的标题）
                from html.parser import HTMLParser

                class _Stripper(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.fed = []
                    def handle_data(self, data):
                        self.fed.append(data)
                    def get_data(self):
                        return ''.join(self.fed)

                s = _Stripper()
                s.feed(item.get('title', ''))
                clean_title = s.get_data()

                results.append({
                    'title': clean_title,
                    'url': item.get('link', item.get('bloggername', '')),
                    'source': f'Naver ({search_type})'
                })
        except Exception as e:
            print(f"[KR] 搜索 Naver ({search_type}) '{query}' 失败: {e}")

    return results[:20]


def search_dcinside_search(query):
    """搜索 DC Inside 全站"""
    encoded = urllib.parse.quote(query)
    url = f"https://search.dcinside.com/combine/q/{encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[KR] DC Inside 品牌搜索 HTTP {response.status_code}: {query}")
            try:
                from utils.notifier import report_scrape_block
                report_scrape_block('dcinside_brand', url=url, status_code=response.status_code)
            except Exception:
                pass
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.result_tit a, .tit_txt'):
            title = item.get_text(strip=True)
            link = item.get('href', '')
            if title:
                results.append({
                    'title': title,
                    'url': str(link) if str(link).startswith('http') else f"https://search.dcinside.com{link}",
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
    if negative: parts.append(f"负面 {len(negative)} 篇")
    if positive: parts.append(f"正面 {len(positive)} 篇")
    if neutral: parts.append(f"中性 {len(neutral)} 篇")

    issue_desc = f"🇰🇷 韩国区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

    if negative:
        top = negative[0]
        issue_desc += f"\n    ⚠️ 负面帖: \"{top['title'][:50]}\" ({top['source']})"

    # AI 舆情总结
    ai_summary = summarize_sentiment('GearUP Booster', 'South Korea', negative, positive, neutral)
    if ai_summary:
        issue_desc += f"\n    {ai_summary.replace(chr(10), chr(10) + '    ')}"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'APAC',
        'country': 'South Korea',
        'alert_type': 'brand_monitor',
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
            flush_scrape_block_alerts(POPO_WEBHOOK_URL)
    else:
        print("无结果")

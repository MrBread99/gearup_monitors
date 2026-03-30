import requests
from bs4 import BeautifulSoup
import os
import sys
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.sentiment_summarizer import summarize_sentiment

# ==========================================
# 俄语区品牌舆情监控（VK + Otzovik）
# ==========================================
# 监控俄罗斯和独联体玩家对 GearUP Booster 及竞品加速器的讨论和评价。
# Otzovik (otzovik.com) 是俄罗斯最大的产品评价网站。
# ==========================================

SEARCH_BRANDS = {
    'GearUP': ['GearUP Booster'],
    'ExitLag': ['ExitLag'],
    'LagoFast': ['LagoFast'],
}

RU_NEGATIVE = [
    "МУСОР", "ОБМАН", "РАЗВОД", "НЕ РАБОТАЕТ", "ХУЖЕ", "ВОЗВРАТ",
    "ДЕНЬГИ", "СКАМ", "ВИРУС", "БЕСПОЛЕЗНО", "ПЛОХО"
]
RU_POSITIVE = [
    "РЕКОМЕНДУЮ", "ХОРОШО", "ОТЛИЧНО", "РАБОТАЕТ", "ЛУЧШИЙ",
    "СТАБИЛЬНО", "ПОМОГЛО", "СНИЖАЕТ ПИНГ"
]

HEADERS_VK = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/81.0.4044.138 Mobile Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9'
}

HEADERS_WEB = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8'
}


def search_vk(query):
    """
    搜索 VK 移动版（免登录）。
    注意：VK 移动版搜索结果页不提供单帖固定 URL，
    每条帖子的 url 统一指向搜索结果页（不同查询词），
    去重通过帖子文本内容（title[:30]）实现。
    """
    encoded = urllib.parse.quote(query)
    search_url = f"https://m.vk.com/search?c%5Bq%5D={encoded}&c%5Bsection%5D=auto"

    try:
        response = requests.get(search_url, headers=HEADERS_VK, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for i, post in enumerate(soup.find_all('div', class_='pi_text')):
            text = post.get_text(strip=True)
            if text and len(text) > 20:
                results.append({
                    'title': text[:150],
                    # 用 query+index 组成唯一 anchor，避免所有条目 URL 完全相同
                    'url': f"{search_url}#result-{i}",
                    'source': 'VK'
                })

        return results[:15]
    except Exception as e:
        print(f"[RU] 搜索 VK '{query}' 失败: {e}")
        return []


def search_otzovik(query):
    """搜索 Otzovik 产品评价"""
    encoded = urllib.parse.quote(query)
    url = f"https://otzovik.com/search/?search_text={encoded}"

    try:
        response = requests.get(url, headers=HEADERS_WEB, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.product-name a, .review-title'):
            title = item.get_text(strip=True)
            link = item.get('href', '')
            if title:
                results.append({
                    'title': title,
                    'url': f"https://otzovik.com{link}" if str(link).startswith('/') else str(link),
                    'source': 'Otzovik'
                })

        return results[:15]
    except Exception as e:
        print(f"[RU] 搜索 Otzovik '{query}' 失败: {e}")
        return []


def analyze_sentiment_ru(posts):
    """分析俄语帖子情感"""
    negative = []
    positive = []
    neutral = []

    for post in posts:
        text = post.get('title', '').upper()
        neg = sum(1 for kw in RU_NEGATIVE if kw in text)
        pos = sum(1 for kw in RU_POSITIVE if kw in text)

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


def check_russia_brand():
    """主检测函数：俄语区品牌舆情"""
    issues = []
    all_posts = []

    for brand, queries in SEARCH_BRANDS.items():
        for q in queries:
            print(f"  - 正在搜索 VK: '{q}'...")
            all_posts.extend(search_vk(q))
            print(f"  - 正在搜索 Otzovik: '{q}'...")
            all_posts.extend(search_otzovik(q))

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

    negative, positive, neutral = analyze_sentiment_ru(unique)

    total = len(unique)
    parts = []
    if negative: parts.append(f"负面 {len(negative)} 篇")
    if positive: parts.append(f"正面 {len(positive)} 篇")
    if neutral: parts.append(f"中性 {len(neutral)} 篇")

    issue_desc = f"🇷🇺 俄语区加速器舆情: 共 {total} 篇讨论 ({', '.join(parts)})"

    if negative:
        top = negative[0]
        issue_desc += f"\n    ⚠️ 负面: \"{top['title'][:50]}\" ({top['source']})"

    # AI 舆情总结
    ai_summary = summarize_sentiment('GearUP Booster', 'Russia/CIS', negative, positive, neutral)
    if ai_summary:
        issue_desc += f"\n    {ai_summary.replace(chr(10), chr(10) + '    ')}"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'CIS / Russia',
        'country': 'Russia',
        'alert_type': 'brand_monitor',
        'issue': issue_desc,
        'source_name': 'VK / Otzovik',
        'source_url': 'https://otzovik.com/'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Russia Brand Monitor...")
    results = check_russia_brand()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无结果")

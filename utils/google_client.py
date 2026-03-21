import requests
from bs4 import BeautifulSoup
import time
import random

# ==========================================
# Google 搜索共享客户端
# ==========================================
# 为所有需要 Google 搜索的模块提供统一的请求方法，
# 内置延迟（5-8 秒随机间隔）防止触发 CAPTCHA。
# ==========================================

_last_google_request = 0
_MIN_INTERVAL = 5.0  # 最少间隔 5 秒
_MAX_INTERVAL = 8.0  # 最多间隔 8 秒

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
}


def google_search(query, lang_code=None, site=None, max_results=10):
    """
    统一的 Google 搜索方法，内置限流和延迟。

    :param query: 搜索关键词
    :param lang_code: 语言限制 (如 'ja', 'ko', 'ar', 'vi', 'id', 'th')
    :param site: 限定站点 (如 '5ch.net', 'ptt.cc')
    :param max_results: 最多返回结果数
    :return: [{'title': str, 'url': str}] 列表
    """
    global _last_google_request

    # 限流：随机延迟 5-8 秒
    now = time.time()
    elapsed = now - _last_google_request
    if elapsed < _MIN_INTERVAL:
        delay = random.uniform(_MIN_INTERVAL, _MAX_INTERVAL) - elapsed
        time.sleep(delay)
    _last_google_request = time.time()

    # 构建搜索 URL
    import urllib.parse
    search_query = query
    if site:
        search_query = f"site:{site} {query}"

    encoded = urllib.parse.quote(search_query)
    url = f"https://www.google.com/search?q={encoded}&num={max_results}"

    if lang_code:
        url += f"&lr=lang_{lang_code}"
        url += "&tbs=qdr:m"  # 最近一个月

    # 设置语言偏好
    headers = HEADERS.copy()
    lang_accept_map = {
        'ja': 'ja-JP,ja;q=0.9',
        'ko': 'ko-KR,ko;q=0.9',
        'ar': 'ar,en-US;q=0.9',
        'vi': 'vi-VN,vi;q=0.9',
        'id': 'id-ID,id;q=0.9',
        'th': 'th-TH,th;q=0.9',
        'tl': 'fil-PH,fil;q=0.9',
        'zh-TW': 'zh-TW,zh;q=0.9',
    }
    if lang_code and lang_code in lang_accept_map:
        headers['Accept-Language'] = lang_accept_map[lang_code]

    results = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[Google] 搜索失败 HTTP {response.status_code}: {query[:50]}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        for h3 in soup.select('h3'):
            title = h3.get_text(strip=True)
            parent_a = h3.find_parent('a')
            link = parent_a.get('href', '') if parent_a else ''
            if title and link:
                # 过滤 site 限定
                if site and site not in link:
                    continue
                results.append({
                    'title': title,
                    'url': link,
                })

        return results[:max_results]

    except Exception as e:
        print(f"[Google] 搜索异常: {e}")
        return []

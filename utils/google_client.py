import requests
from bs4 import BeautifulSoup
import time
import random
import urllib.parse

# ==========================================
# 搜索引擎共享客户端
# ==========================================
# Google 优先，失败时自动 fallback 到 DuckDuckGo。
# DuckDuckGo 的 HTML 版无反爬，CI 环境下更可靠。
# ==========================================

_last_request = 0
_MIN_INTERVAL = 3.0
_MAX_INTERVAL = 5.0

GOOGLE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

DDG_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}

LANG_ACCEPT_MAP = {
    'ja': 'ja-JP,ja;q=0.9',
    'ko': 'ko-KR,ko;q=0.9',
    'ar': 'ar,en-US;q=0.9',
    'vi': 'vi-VN,vi;q=0.9',
    'id': 'id-ID,id;q=0.9',
    'th': 'th-TH,th;q=0.9',
    'tl': 'fil-PH,fil;q=0.9',
    'zh-TW': 'zh-TW,zh;q=0.9',
}

# DuckDuckGo 地区代码映射
DDG_REGION_MAP = {
    'ja': 'jp-jp',
    'ko': 'kr-kr',
    'ar': 'xa-ar',
    'vi': 'vn-vi',
    'id': 'id-id',
    'th': 'th-th',
    'tl': 'ph-en',
    'zh-TW': 'tw-tzh',
}


def _throttle():
    global _last_request
    now = time.time()
    elapsed = now - _last_request
    if elapsed < _MIN_INTERVAL:
        delay = random.uniform(_MIN_INTERVAL, _MAX_INTERVAL) - elapsed
        time.sleep(delay)
    _last_request = time.time()


def _search_google(query, lang_code=None, site=None, max_results=10):
    """Google 搜索"""
    search_query = f"site:{site} {query}" if site else query
    encoded = urllib.parse.quote(search_query)
    url = f"https://www.google.com/search?q={encoded}&num={max_results}"

    if lang_code:
        url += f"&lr=lang_{lang_code}&tbs=qdr:m"

    headers = GOOGLE_HEADERS.copy()
    if lang_code and lang_code in LANG_ACCEPT_MAP:
        headers['Accept-Language'] = LANG_ACCEPT_MAP[lang_code]

    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        return None  # 返回 None 表示失败，触发 fallback

    soup = BeautifulSoup(response.text, 'html.parser')

    # 检测 CAPTCHA（文本检测 + noscript 标签检测，覆盖 JS 渲染的 CAPTCHA 页面）
    text_lower = response.text.lower()
    if (
        'captcha' in text_lower
        or 'unusual traffic' in text_lower
        or 'g-recaptcha' in text_lower          # JS 渲染的 reCAPTCHA 挑战
        or 'sorry/index' in response.url        # Google CAPTCHA 重定向页
        or len(soup.select('noscript')) > 2     # JS 渲染验证页通常有多个 noscript 块
    ):
        return None

    results = []
    for h3 in soup.select('h3'):
        title = h3.get_text(strip=True)
        parent_a = h3.find_parent('a')
        link = parent_a.get('href', '') if parent_a else ''
        if title and link:
            if site and site not in link:
                continue
            results.append({'title': title, 'url': link})

    return results[:max_results] if results else None


def _search_duckduckgo(query, lang_code=None, site=None, max_results=10):
    """DuckDuckGo HTML 搜索（fallback，无反爬）"""
    search_query = f"site:{site} {query}" if site else query
    encoded = urllib.parse.quote(search_query)

    params = f"q={encoded}"
    if lang_code and lang_code in DDG_REGION_MAP:
        params += f"&kl={DDG_REGION_MAP[lang_code]}"

    url = f"https://html.duckduckgo.com/html/?{params}"

    response = requests.get(url, headers=DDG_HEADERS, timeout=15)
    if response.status_code != 200:
        print(f"[DuckDuckGo] 搜索失败 HTTP {response.status_code}: {query[:50]}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    results = []

    for result in soup.select('.result__a'):
        title = result.get_text(strip=True)
        link = result.get('href', '')
        if title and link:
            if site and site not in link:
                continue
            results.append({'title': title, 'url': link})

    return results[:max_results]


def google_search(query, lang_code=None, site=None, max_results=10):
    """
    统一的搜索方法。Google 优先，失败时自动 fallback 到 DuckDuckGo。
    """
    _throttle()

    # 先试 Google
    try:
        results = _search_google(query, lang_code, site, max_results)
        if results is not None and len(results) > 0:
            return results
    except Exception as e:
        print(f"[Google] 搜索异常: {e}")

    # Google 失败，fallback DuckDuckGo
    _throttle()
    try:
        print(f"[Search] Google 失败，fallback 到 DuckDuckGo: {query[:50]}")
        return _search_duckduckgo(query, lang_code, site, max_results)
    except Exception as e:
        print(f"[DuckDuckGo] 搜索异常: {e}")
        return []

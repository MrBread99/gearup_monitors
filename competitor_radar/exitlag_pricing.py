import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import re
import time
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL

# ==========================================
# 竞品多地区定价监控
# ==========================================
# 定时抓取竞品官网各语言/地区版本的定价页面，
# 与上次记录做比对，发现价格或套餐结构变动时发送报警。
#
# 当前监控竞品:
# 1. ExitLag — /en/pricing, /zh/pricing, /kr/pricing 等
# 2. LagoFast — /en/, /ko/, /ja/ 等（定价信息在首页或子页面）
#
# 抓取优先级：Playwright + stealth > cloudscraper > requests
# ==========================================

# 竞品配置
COMPETITORS = {
    'ExitLag': {
        'regions': {
            'en': 'English (Global)',
            'zh-tw': '繁體中文 (Taiwan/HK)',
            'jp': '日本語 (Japan)',
            'ko': '한국어 (Korea)',
            'pt': 'Português (Brazil)',
            'ru': 'Русский (Russia/CIS)',
            'es': 'Español (LATAM)',
            'ar': 'العربية (Middle East)',
            'de': 'Deutsch (Germany)',
        },
        'url_template': 'https://www.exitlag.com/{region}/pricing',
    },
    'LagoFast': {
        'regions': {
            'en': 'English (Global)',
            'zh-tw': '繁體中文 (Taiwan/HK)',
            'ja': '日本語 (Japan)',
            'ko': '한국어 (Korea)',
            'pt-br': 'Português (Brazil)',
            'th': 'ไทย (Thailand)',
            'vi': 'Tiếng Việt (Vietnam)',
            'id': 'Indonesia',
            'ar': 'العربية (Middle East)',
            'tr': 'Türkçe (Turkey)',
        },
        'url_template': 'https://www.lagofast.com/{region}/',
    },
}

# 兼容旧配置
REGIONS = COMPETITORS['ExitLag']['regions']

# 套餐名与玩家数的映射
PLAN_TIERS = ['Solo', 'Duo', 'Squad']

# 上次定价快照的存储路径
SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exitlag_pricing_snapshot.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}


# ==========================================
# Playwright 浏览器会话管理（单例复用）
# ==========================================
_pw_browser = None
_pw_context = None
_pw_page = None
_pw_available = None  # None = 未检测, True/False = 已确认


def _ensure_playwright():
    """
    懒初始化 Playwright 浏览器（整个进程生命周期只启动一次）。
    返回 page 对象；不可用时返回 None。
    """
    global _pw_browser, _pw_context, _pw_page, _pw_available

    if _pw_available is False:
        return None
    if _pw_page is not None:
        return _pw_page

    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _pw_browser = pw.chromium.launch(headless=True)
        _pw_context = _pw_browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
        )

        # 尝试应用 playwright-stealth 隐身补丁
        try:
            from playwright_stealth import stealth_sync
            _pw_page = _pw_context.new_page()
            stealth_sync(_pw_page)
        except ImportError:
            print("[Pricing] playwright-stealth 未安装，使用原生 Playwright")
            _pw_page = _pw_context.new_page()

        _pw_available = True
        print("[Pricing] Playwright 浏览器已启动")
        return _pw_page

    except Exception as e:
        print(f"[Pricing] Playwright 不可用，将使用 fallback: {e}")
        _pw_available = False
        return None


def _close_playwright():
    """关闭 Playwright 浏览器（进程结束时调用）。"""
    global _pw_browser, _pw_context, _pw_page, _pw_available
    try:
        if _pw_page:
            _pw_page.close()
        if _pw_context:
            _pw_context.close()
        if _pw_browser:
            _pw_browser.close()
    except Exception:
        pass
    _pw_browser = _pw_context = _pw_page = None
    _pw_available = None


def _fetch_with_playwright(url):
    """
    用 Playwright 真实浏览器访问 URL，等待页面加载完成后返回 HTML。
    成功返回 (html_text, status_code)，失败返回 (None, 0)。
    """
    page = _ensure_playwright()
    if page is None:
        return None, 0

    try:
        # 每次请求前随机延迟 2-4 秒，模拟人类浏览间隔
        time.sleep(random.uniform(2.0, 4.0))
        response = page.goto(url, wait_until='networkidle', timeout=30000)
        status = response.status if response else 0

        if status == 200:
            html = page.content()
            return html, 200
        else:
            return None, status
    except Exception as e:
        print(f"[Pricing] Playwright 访问 {url} 失败: {e}")
        return None, 0


# ==========================================
# cloudscraper 会话（单例复用）
# ==========================================
_cs_session = None
_cs_available = None


def _get_cloudscraper_session():
    """获取或创建 cloudscraper 会话（复用同一 TLS 指纹）。"""
    global _cs_session, _cs_available
    if _cs_available is False:
        return None
    if _cs_session is not None:
        return _cs_session
    try:
        import cloudscraper
        _cs_session = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        _cs_available = True
        return _cs_session
    except ImportError:
        _cs_available = False
        return None
    except Exception as e:
        print(f"[Pricing] cloudscraper 初始化失败: {e}")
        _cs_available = False
        return None


def fetch_pricing_for_region(region_code, competitor_name='ExitLag'):
    """
    抓取指定竞品指定地区的定价页面，解析出价格和折扣信息。
    优先级：Playwright + stealth > cloudscraper (会话复用) > requests
    """
    config = COMPETITORS.get(competitor_name, {})
    url_template = config.get('url_template', '')
    url = url_template.replace('{region}', region_code)

    html_text = None
    status_code = 0

    # === Tier 1: Playwright（真实浏览器，最可靠） ===
    html_text, status_code = _fetch_with_playwright(url)

    # === Tier 2: cloudscraper（会话复用） ===
    if html_text is None and status_code != 403:
        scraper = _get_cloudscraper_session()
        if scraper:
            try:
                time.sleep(random.uniform(2.0, 5.0))
                response = scraper.get(url, timeout=20)
                status_code = response.status_code
                if status_code == 200:
                    html_text = response.text
            except Exception as e:
                print(f"[{competitor_name}] cloudscraper {region_code} 失败: {e}")

    # === Tier 3: 普通 requests（最后兜底） ===
    if html_text is None and status_code != 403:
        try:
            time.sleep(random.uniform(1.0, 3.0))
            response = requests.get(url, headers=HEADERS, timeout=15)
            status_code = response.status_code
            if status_code == 200:
                html_text = response.text
        except Exception as e:
            print(f"[{competitor_name}] requests {region_code} 失败: {e}")

    # === 结果处理 ===
    if status_code == 403:
        try:
            from utils.notifier import report_scrape_block
            report_scrape_block('cloudflare_pricing', url=url, status_code=403)
        except Exception:
            pass
        return None

    if html_text is None:
        if status_code:
            print(f"[{competitor_name}] {region_code}: HTTP {status_code}")
        return None

    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        text = soup.get_text()

        # 提取所有价格数字 (格式: US$X.XX 或 R$X.XX 或 ¥XXX 等)
        prices = re.findall(r'(?:US\$|R\$|€|¥|₩|£|\$)\s*[\d,]+\.?\d*', text)

        # 提取所有折扣百分比
        discounts = re.findall(r'(\d+)%\s*(?:OFF|off|Save|save|discount)', text, re.IGNORECASE)

        # 用价格+折扣的 hash 做变动检测（而非整个页面 hash，避免动态内容误报）
        pricing_fingerprint = str(sorted(prices)) + '|' + str(sorted(discounts))

        pricing_data = {
            'prices_raw': prices,
            'discounts': discounts,
            'pricing_hash': str(hash(pricing_fingerprint)),
        }

        return pricing_data

    except Exception as e:
        print(f"[{competitor_name}] 解析 {region_code} 定价失败: {e}")
        return None


def load_snapshot():
    """加载上次保存的定价快照"""
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_snapshot(data):
    """保存当前定价快照"""
    with open(SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_competitor_pricing(competitor_name):
    """
    通用竞品定价检测：抓取指定竞品所有地区定价，与上次快照比对，返回变动报警。
    """
    issues = []
    config = COMPETITORS.get(competitor_name, {})
    regions = config.get('regions', {})

    old_snapshot = load_snapshot()
    # 每个竞品在快照中用独立的 key
    competitor_key = competitor_name.lower().replace(' ', '_')
    old_competitor_data = old_snapshot.get(competitor_key, {})
    new_competitor_data = {}

    for region_code, region_name in regions.items():
        print(f"  - 正在抓取 {competitor_name} {region_name} 定价...")
        pricing = fetch_pricing_for_region(region_code, competitor_name)

        if not pricing:
            continue

        new_competitor_data[region_code] = pricing

        # 与旧快照比对 — 直接比对价格和折扣列表（不依赖 hash key 名称）
        old_pricing = old_competitor_data.get(region_code)
        if old_pricing:
            old_prices = set(old_pricing.get('prices_raw', []))
            new_prices = set(pricing.get('prices_raw', []))
            old_discounts = set(old_pricing.get('discounts', []))
            new_discounts = set(pricing.get('discounts', []))

            # 只有价格或折扣真正变化时才报警
            if old_prices != new_prices or old_discounts != new_discounts:
                added_prices = new_prices - old_prices
                removed_prices = old_prices - new_prices

                changes = []
                if added_prices:
                    changes.append(f"新增价格: {', '.join(added_prices)}")
                if removed_prices:
                    changes.append(f"移除价格: {', '.join(removed_prices)}")
                if old_discounts != new_discounts:
                    changes.append(f"折扣变动: {', '.join(old_discounts)} -> {', '.join(new_discounts)}")

                if not changes:
                    changes.append("价格结构有微调")

                url = config.get('url_template', '').replace('{region}', region_code)
                issues.append({
                    'game': competitor_name,
                    'region': region_name,
                    'country': '',
                    'issue': f"⚡ 竞品定价变动检测: {'; '.join(changes)}",
                    'alert_type': 'competitor_radar',
                    'source_name': f'{competitor_name} Pricing Page',
                    'source_url': url
                })

    # 首次运行
    if not old_competitor_data and new_competitor_data:
        print(f"[{competitor_name}] 首次运行，已保存定价基线快照。")

    # 更新快照（保留其他竞品的快照数据）
    if new_competitor_data:
        old_snapshot[competitor_key] = new_competitor_data
        save_snapshot(old_snapshot)

    return issues


def check_exitlag_pricing():
    """兼容旧接口"""
    return check_competitor_pricing('ExitLag')


def check_all_competitor_pricing():
    """检查所有竞品的定价变动，完成后关闭浏览器。"""
    all_issues = []
    try:
        for competitor_name in COMPETITORS:
            all_issues.extend(check_competitor_pricing(competitor_name))
    finally:
        _close_playwright()
    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    try:
        print("Testing Competitor Pricing Monitor...")
        results = check_all_competitor_pricing()
        if results:
            for r in results:
                print(f"[{r['game']} - {r['region']}] {r['issue']}")
            if POPO_WEBHOOK_URL:
                send_popo_alert(POPO_WEBHOOK_URL, results)
                flush_scrape_block_alerts(POPO_WEBHOOK_URL)
        else:
            print("无定价变动（或首次运行已保存基线）。")
    except Exception as e:
        print(f"[Pricing] 顶层异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _close_playwright()

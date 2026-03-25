import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# 竞品多地区定价监控
# ==========================================
# 定时抓取竞品官网各语言/地区版本的定价页面，
# 与上次记录做比对，发现价格或套餐结构变动时发送报警。
#
# 当前监控竞品:
# 1. ExitLag — /en/pricing, /zh/pricing, /kr/pricing 等
# 2. LagoFast — /en/, /ko/, /ja/ 等（定价信息在首页或子页面）
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


def fetch_pricing_for_region(region_code, competitor_name='ExitLag'):
    """
    抓取指定竞品指定地区的定价页面，解析出价格和折扣信息。
    支持 Cloudflare 绕过（cloudscraper 优先，fallback 到 requests）。
    """
    config = COMPETITORS.get(competitor_name, {})
    url_template = config.get('url_template', '')
    url = url_template.replace('{region}', region_code)

    # 尝试用 cloudscraper 绕过 Cloudflare（如果安装了）
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        response = scraper.get(url, timeout=20)
    except ImportError:
        # cloudscraper 未安装，用普通 requests
        import time
        time.sleep(1)  # 简单延迟降低被拦概率
        response = requests.get(url, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"[{competitor_name}] cloudscraper {region_code} 失败: {e}")
        response = requests.get(url, headers=HEADERS, timeout=15)
    
    try:
        if response.status_code == 403:
            # Cloudflare 拦截，静默跳过（不刷日志）
            return None
        elif response.status_code != 200:
            print(f"[{competitor_name}] {region_code}: HTTP {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
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
        print(f"[{competitor_name}] 抓取 {region_code} 定价失败: {e}")
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
    """检查所有竞品的定价变动"""
    all_issues = []
    for competitor_name in COMPETITORS:
        all_issues.extend(check_competitor_pricing(competitor_name))
    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Competitor Pricing Monitor...")
    results = check_all_competitor_pricing()
    if results:
        for r in results:
            print(f"[{r['game']} - {r['region']}] {r['issue']}")
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无定价变动（或首次运行已保存基线）。")

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# ExitLag 多地区定价监控
# ==========================================
# 定时抓取 ExitLag 官网各语言/地区版本的定价页面，
# 与上次记录做比对，发现价格或套餐结构变动时发送报警。
#
# ExitLag 支持的地区页面:
#   /en (英文), /kr (韩语), /zh (繁中), /jp (日语),
#   /ar (阿拉伯), /de (德语), /pt (葡语), /ru (俄语), /es (西语)
# ==========================================

# 监控的地区列表
REGIONS = {
    'en': 'English (Global)',
    'zh': '繁體中文 (Taiwan/HK)',
    'jp': '日本語 (Japan)',
    'kr': '한국어 (Korea)',
    'pt': 'Português (Brazil)',
    'ru': 'Русский (Russia/CIS)',
    'es': 'Español (LATAM)',
    'ar': 'العربية (Middle East)',
    'de': 'Deutsch (Germany)',
}

# 套餐名与玩家数的映射
PLAN_TIERS = ['Solo', 'Duo', 'Squad']

# 上次定价快照的存储路径
SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exitlag_pricing_snapshot.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}


def fetch_pricing_for_region(region_code):
    """
    抓取指定地区的 ExitLag 定价页面，解析出所有套餐的价格信息。
    返回格式: {
        'Solo': {'monthly': '$7.50', 'quarterly': '$6.25', 'annual': '$4.48'},
        'Duo': {...},
        'Squad': {...}
    }
    """
    url = f"https://www.exitlag.com/{region_code}/pricing"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[ExitLag] {region_code}: HTTP {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        
        # 提取所有价格数字 (格式: US$X.XX 或 R$X.XX 等)
        prices = re.findall(r'(?:US\$|R\$|€|¥|₩|£)\s*[\d,]+\.?\d*', text)
        
        # 提取所有折扣百分比
        discounts = re.findall(r'(\d+)%\s*OFF', text)
        
        # 构建结构化数据
        pricing_data = {
            'prices_raw': prices,
            'discounts': discounts,
            'page_text_hash': str(hash(text)),  # 用于快速检测页面是否有变化
        }
        
        return pricing_data
        
    except Exception as e:
        print(f"[ExitLag] 抓取 {region_code} 定价失败: {e}")
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


def check_exitlag_pricing():
    """
    主检测函数：抓取所有地区定价，与上次快照比对，返回变动报警列表。
    """
    issues = []
    old_snapshot = load_snapshot()
    new_snapshot = {}
    
    for region_code, region_name in REGIONS.items():
        print(f"  - 正在抓取 ExitLag {region_name} 定价...")
        pricing = fetch_pricing_for_region(region_code)
        
        if not pricing:
            continue
        
        new_snapshot[region_code] = pricing
        
        # 与旧快照比对
        old_pricing = old_snapshot.get(region_code)
        if old_pricing:
            # 通过页面内容 hash 快速判断是否有变化
            if old_pricing.get('page_text_hash') != pricing.get('page_text_hash'):
                # 页面有变化，进一步比对价格
                old_prices = set(old_pricing.get('prices_raw', []))
                new_prices = set(pricing.get('prices_raw', []))
                
                added_prices = new_prices - old_prices
                removed_prices = old_prices - new_prices
                
                old_discounts = set(old_pricing.get('discounts', []))
                new_discounts = set(pricing.get('discounts', []))
                
                changes = []
                if added_prices:
                    changes.append(f"新增价格: {', '.join(added_prices)}")
                if removed_prices:
                    changes.append(f"移除价格: {', '.join(removed_prices)}")
                if old_discounts != new_discounts:
                    changes.append(f"折扣变动: {', '.join(old_discounts)} -> {', '.join(new_discounts)}")
                
                if not changes:
                    changes.append("页面内容有变化（可能是套餐结构/文案调整）")
                
                issues.append({
                    'game': 'ExitLag',
                    'region': region_name,
                    'country': '',
                    'issue': f"⚡ 竞品定价变动检测: {'; '.join(changes)}",
                    'source_name': 'ExitLag Pricing Page',
                    'source_url': f'https://www.exitlag.com/{region_code}/pricing'
                })
    
    # 首次运行，无旧快照，不报警，只保存基线
    if not old_snapshot and new_snapshot:
        print("[ExitLag] 首次运行，已保存定价基线快照，下次运行时将检测变动。")
    
    # 保存新快照
    if new_snapshot:
        save_snapshot(new_snapshot)
    
    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    
    print("Testing ExitLag Pricing Monitor...")
    results = check_exitlag_pricing()
    if results:
        for r in results:
            print(f"[{r['region']}] {r['issue']}")
    else:
        print("无定价变动（或首次运行已保存基线）。")

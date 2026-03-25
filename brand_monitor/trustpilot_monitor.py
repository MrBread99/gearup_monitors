import requests
from bs4 import BeautifulSoup
import os
import sys
import re
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# Trustpilot 品牌评价监控
# ==========================================
# 监控 GearUP 和主要竞品在 Trustpilot 上的评分、评论数量和近期评论情感。
# 通过对比历史快照检测评分变动。
# ==========================================

# 监控的品牌列表（slug -> 显示名）
BRANDS = {
    'gearupbooster.com': 'GearUP Booster',
    'exitlag.com': 'ExitLag',
    'lagofast.com': 'LagoFast',
    'www.noping.com': 'NoPing',
    'hone.gg': 'Hone.gg',
    'wtfast.com': 'wtfast',
}

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'trustpilot_snapshot.json'
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
}


def fetch_trustpilot_data(slug):
    """
    抓取 Trustpilot 品牌页面，提取评分和评论数。
    """
    url = f"https://www.trustpilot.com/review/{slug}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[Trustpilot] {slug}: HTTP {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()

        # 提取评分 (格式如 "4.8" 或 "3.3")
        score = None
        score_match = re.search(r'TrustScore\s+[\d.]+\s+out\s+of\s+5', text)
        if score_match:
            num = re.search(r'[\d.]+', score_match.group())
            if num:
                score = float(num.group())

        # 提取评论总数
        review_count = None
        count_match = re.search(r'([\d,]+)\s+reviews', text)
        if count_match:
            review_count = int(count_match.group(1).replace(',', ''))

        # 提取星级分布
        star_dist = {}
        for star in [5, 4, 3, 2, 1]:
            pct_match = re.search(
                rf'{star}-star\s+(\d+)%', text
            )
            if pct_match:
                star_dist[str(star)] = int(pct_match.group(1))

        # 提取最近评论的简要信息
        recent_reviews = []
        review_cards = soup.select('[data-review-content]') or soup.select('.styles_reviewContent__0Q2Tg')
        # 退化方案：直接找评分星级图片附近的文本
        for card in review_cards[:5]:
            review_text = card.get_text(strip=True)[:200]
            if review_text:
                recent_reviews.append(review_text)

        return {
            'score': score,
            'review_count': review_count,
            'star_distribution': star_dist,
            'recent_reviews_sample': recent_reviews,
            'fetched_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
        }

    except Exception as e:
        print(f"[Trustpilot] 抓取 {slug} 失败: {e}")
        return None


def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_snapshot(data):
    with open(SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_trustpilot():
    """
    主检测函数：抓取所有品牌的 Trustpilot 数据，与上次快照对比，返回变动报警。
    """
    issues = []
    old_snapshot = load_snapshot()
    new_snapshot = {}

    for slug, brand_name in BRANDS.items():
        print(f"  - 正在抓取 Trustpilot: {brand_name}...")
        data = fetch_trustpilot_data(slug)

        if not data:
            continue

        new_snapshot[slug] = data

        old_data = old_snapshot.get(slug)
        if old_data:
            changes = []

            # 评分变动
            old_score = old_data.get('score')
            new_score = data.get('score')
            if old_score and new_score and old_score != new_score:
                direction = "↑" if new_score > old_score else "↓"
                changes.append(f"评分 {old_score} -> {new_score} {direction}")

            # 评论数变动
            old_count = old_data.get('review_count', 0)
            new_count = data.get('review_count', 0)
            if old_count and new_count:
                diff = new_count - old_count
                if diff > 0:
                    changes.append(f"新增 {diff} 条评论 (总计 {new_count})")

            # 1 星评论占比变动（负面舆情指标）
            old_1star = old_data.get('star_distribution', {}).get('1', 0)
            new_1star = data.get('star_distribution', {}).get('1', 0)
            if new_1star > old_1star + 2:
                changes.append(f"1星差评占比上升: {old_1star}% -> {new_1star}%")

            if changes:
                is_self = (slug == 'gearupbooster.com')
                prefix = "📊 品牌舆情" if is_self else "📊 竞品动态"
                issues.append({
                    'game': brand_name,
                    'region': 'Global',
                    'country': '',
                    'alert_type': 'brand_monitor',
                    'issue': f"{prefix}: {'; '.join(changes)}",
                    'source_name': 'Trustpilot',
                    'source_url': f'https://www.trustpilot.com/review/{slug}'
                })

    # 首次运行
    if not old_snapshot and new_snapshot:
        print("[Trustpilot] 首次运行，已保存评分基线快照。")
        # 生成一条总览报告
        summary_parts = []
        for slug, brand_name in BRANDS.items():
            d = new_snapshot.get(slug)
            if d and d.get('score'):
                summary_parts.append(f"{brand_name}: {d['score']} ({d.get('review_count', '?')}条)")
        if summary_parts:
            issues.append({
                'game': 'Trustpilot',
                'region': 'Global',
                'country': '',
                'alert_type': 'brand_monitor',
                'issue': f"📊 Trustpilot 基线快照: {' | '.join(summary_parts)}",
                'source_name': 'Trustpilot',
                'source_url': 'https://www.trustpilot.com/'
            })

    if new_snapshot:
        save_snapshot(new_snapshot)

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Trustpilot Monitor...")
    results = check_trustpilot()
    if results:
        for r in results:
            print(f"[{r['game']}] {r['issue']}")
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("无结果")

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get

# ==========================================
# 俄罗斯大型活动日历 & 网络管控预警
# ==========================================
# 基于观察规律：俄罗斯在举办大型国际活动期间倾向于加强网络管控，
# 导致 VPN/加速器需求飙升。
#
# 监控策略：
# 1. 硬编码已知的年度周期性活动（BRICS/SCO/SPIEF/EEF 等）
# 2. Reddit/TASS 搜索即将在俄罗斯举办的国际会议/峰会
# 3. Roskomnadzor（俄联邦通信监管局）封锁动态
# 4. AI 综合分析活动对网络管控的影响程度
# ==========================================

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/3.0'
}

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'russia_events_snapshot.json'
)

# ==========================================
# 1. 已知的俄罗斯年度大型活动（每年固定时间）
# ==========================================
KNOWN_ANNUAL_EVENTS = [
    {
        'name': 'SPIEF (St. Petersburg International Economic Forum)',
        'name_zh': '圣彼得堡国际经济论坛',
        'month': 6, 'day_start': 5, 'day_end': 8,
        'risk_level': 'high',
        'description': '俄罗斯最大的经济论坛，普京出席，国际关注度极高',
    },
    {
        'name': 'EEF (Eastern Economic Forum)',
        'name_zh': '东方经济论坛（符拉迪沃斯托克）',
        'month': 9, 'day_start': 3, 'day_end': 6,
        'risk_level': 'high',
        'description': '远东经济论坛，中日韩领导人参会，网络管控通常加强',
    },
    {
        'name': 'BRICS Summit (if hosted in Russia)',
        'name_zh': 'BRICS 金砖峰会（俄罗斯轮值年）',
        'month': 10, 'day_start': 22, 'day_end': 24,
        'risk_level': 'critical',
        'description': '金砖峰会俄罗斯轮值主席国年份举办，2024年在喀山举办时网络管控显著加强',
    },
    {
        'name': 'SCO Summit (if hosted in Russia)',
        'name_zh': '上合组织峰会（俄罗斯轮值年）',
        'month': 7, 'day_start': 3, 'day_end': 4,
        'risk_level': 'high',
        'description': '上合组织峰会，安全级别极高',
    },
    {
        'name': 'Victory Day (May 9)',
        'name_zh': '胜利日（5月9日）',
        'month': 5, 'day_start': 8, 'day_end': 10,
        'risk_level': 'medium',
        'description': '俄罗斯最重要的国家纪念日，阅兵式期间网络监控加强',
    },
    {
        'name': 'Russian Presidential Inauguration',
        'name_zh': '总统就职典礼',
        'month': 5, 'day_start': 7, 'day_end': 7,
        'risk_level': 'high',
        'description': '总统就职典礼年份（如2024年），安全级别极高',
    },
    {
        'name': 'Russia Day (June 12)',
        'name_zh': '俄罗斯日（6月12日）',
        'month': 6, 'day_start': 11, 'day_end': 13,
        'risk_level': 'low',
        'description': '国庆节，通常有大规模庆祝活动',
    },
    {
        'name': 'Kazan Digital Forum',
        'name_zh': '喀山数字论坛',
        'month': 4, 'day_start': 18, 'day_end': 20,
        'risk_level': 'medium',
        'description': '数字技术论坛，IT 相关，可能伴随网络演习',
    },
]

RISK_LABELS = {
    'critical': '🔴 极高风险',
    'high': '🟠 高风险',
    'medium': '🟡 中等风险',
    'low': '🟢 低风险',
}


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


def check_known_events():
    """
    检查已知的年度大型活动，提前 14 天预警。
    """
    issues = []
    now = datetime.now(timezone.utc)
    year = now.year

    snapshot = load_snapshot()
    alerted_events = set(snapshot.get('alerted_events', []))

    for event in KNOWN_ANNUAL_EVENTS:
        try:
            event_start = datetime(year, event['month'], event['day_start'], tzinfo=timezone.utc)
            event_end = datetime(year, event['month'], event['day_end'], 23, 59, tzinfo=timezone.utc)
        except ValueError:
            continue

        days_until = (event_start - now).days
        event_key = f"{event['name']}_{year}"

        # 提前 14 天预警，且未报过
        if 0 <= days_until <= 14 and event_key not in alerted_events:
            risk = RISK_LABELS.get(event['risk_level'], '未知')

            if days_until == 0:
                timing = "今天开始"
            elif days_until == 1:
                timing = "明天开始"
            else:
                timing = f"{days_until} 天后开始"

            issue_text = f"📅 [俄罗斯活动预警] {event['name_zh']} ({timing})"
            issue_text += f"\n    网络管控风险: {risk}"
            issue_text += f"\n    时间: {event_start.strftime('%m月%d日')} - {event_end.strftime('%m月%d日')}"
            issue_text += f"\n    说明: {event['description']}"
            issue_text += f"\n    建议: 提前准备俄罗斯区加速节点扩容和营销推送"

            issues.append({
                'game': '俄罗斯网络管控预警',
                'region': 'CIS / Russia',
                'country': 'Russia',
                'issue': issue_text,
                'alert_type': 'game_monitor',
                'source_name': 'Russia Event Calendar',
                'source_url': ''
            })

            alerted_events.add(event_key)

        # 活动进行中（已过 start 但未过 end），如果是高风险+未报过"进行中"
        elif days_until < 0 and (now <= event_end):
            ongoing_key = f"{event_key}_ongoing"
            if ongoing_key not in alerted_events and event['risk_level'] in ('critical', 'high'):
                risk = RISK_LABELS.get(event['risk_level'], '未知')
                issue_text = f"🚨 [俄罗斯活动进行中] {event['name_zh']} 正在举办"
                issue_text += f"\n    网络管控风险: {risk}"
                issue_text += f"\n    预计结束: {event_end.strftime('%m月%d日')}"
                issue_text += f"\n    建议: 密切关注 detector404.ru 和 VK 社区的俄罗斯区故障报告"

                issues.append({
                    'game': '俄罗斯网络管控预警',
                    'region': 'CIS / Russia',
                    'country': 'Russia',
                    'issue': issue_text,
                    'alert_type': 'game_monitor',
                    'source_name': 'Russia Event Calendar',
                    'source_url': ''
                })

                alerted_events.add(ongoing_key)

    snapshot['alerted_events'] = list(alerted_events)[-100:]
    save_snapshot(snapshot)

    return issues


def check_reddit_russia_events():
    """
    通过 Reddit 搜索即将在俄罗斯举办的非固定活动（临时峰会、外交访问等）。
    """
    issues = []

    queries = [
        "Russia summit 2026",
        "Russia conference 2026",
        "Russia hosting international",
        "Putin summit",
        "Roskomnadzor VPN block",
        "Russia internet crackdown",
        "Russia VPN ban",
    ]

    relevant_posts = []

    for query in queries:
        encoded = requests.utils.quote(query)
        url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&t=week&limit=10"

        response = reddit_get(url)
        if not response or response.status_code != 200:
            continue

        try:
            posts = response.json().get('data', {}).get('children', [])
            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)

                # 只看有一定热度的帖子
                if score < 50:
                    continue

                title_upper = title.upper()
                is_russia_event = any(kw in title_upper for kw in [
                    'RUSSIA', 'MOSCOW', 'KREMLIN', 'PUTIN',
                    'ROSKOMNADZOR', 'RUSSIAN'
                ])
                is_relevant = any(kw in title_upper for kw in [
                    'SUMMIT', 'CONFERENCE', 'FORUM', 'MEETING',
                    'VPN', 'BLOCK', 'BAN', 'CRACKDOWN', 'INTERNET',
                    'CENSORSHIP', 'RESTRICT'
                ])

                if is_russia_event and is_relevant:
                    relevant_posts.append({
                        'title': title,
                        'score': score,
                        'url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
        except Exception:
            pass

    if not relevant_posts:
        return issues

    # 去重
    seen = set()
    unique = []
    for p in relevant_posts:
        key = p['title'][:40]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # 用 AI 分析对网络管控的影响
    if qwen_client and unique:
        titles = '\n'.join(f"- {p['title']} (↑{p['score']})" for p in unique[:5])
        prompt = f"""你是一个俄罗斯网络管控分析专家。以下是近期关于俄罗斯的新闻标题，请判断这些事件是否可能导致俄罗斯加强网络管控（如封锁 VPN/代理/加速器），从而带来加速器需求上升。

新闻标题:
{titles}

请用纯文本输出一行（禁止 Markdown），格式:
风险等级(高/中/低/无) - 一句话分析(30字以内)"""

        try:
            response = qwen_client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {"role": "system", "content": "你是俄罗斯网络管控分析专家，输出简洁一行。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=100
            )
            ai_analysis = str(response.choices[0].message.content).strip().split('\n')[0]
        except Exception:
            ai_analysis = "AI 分析不可用"
    else:
        ai_analysis = ""

    # 只在 AI 判断为中或高风险时报警
    if ai_analysis and '无' not in ai_analysis and '低' not in ai_analysis:
        top_post = unique[0]
        issue_text = f"📡 [俄罗斯网络管控动态] 检测到 {len(unique)} 条相关新闻"
        issue_text += f"\n    最热新闻: {top_post['title'][:60]} (↑{top_post['score']})"
        if ai_analysis:
            issue_text += f"\n    AI 风险评估: {ai_analysis}"
        issue_text += f"\n    建议: 关注俄罗斯区加速器使用量变化"

        issues.append({
            'game': '俄罗斯网络管控预警',
            'region': 'CIS / Russia',
            'country': 'Russia',
            'issue': issue_text,
            'alert_type': 'game_monitor',
            'source_name': 'Reddit / AI Analysis',
            'source_url': top_post['url']
        })

    return issues


def check_russia_events():
    """主检测函数"""
    all_issues = []

    print("正在检测俄罗斯已知大型活动日历...")
    all_issues.extend(check_known_events())

    print("正在检测俄罗斯网络管控动态 (Reddit)...")
    all_issues.extend(check_reddit_russia_events())

    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Russia Event Monitor...")
    results = check_russia_events()
    if results:
        for r in results:
            print(r['issue'])
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("近期无俄罗斯大型活动或网络管控动态。")

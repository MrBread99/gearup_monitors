import json
import os
import hashlib

# ==========================================
# 加速器无效（🔴）报警去重与合并
# ==========================================
# - 🔴 加速器无效的报警：合并成一条摘要 + 跨运行去重（报过不再报）
# - 🟢 加速器可解决的报警：每次都报，不去重
# - 🟡 待确认的报警：每次都报，不去重
# ==========================================

INEFFECTIVE_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'game_monitor', 'ineffective_alerts_snapshot.json'
)


def _load_seen_ineffective():
    path = os.path.normpath(INEFFECTIVE_SNAPSHOT_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_seen_ineffective(seen):
    path = os.path.normpath(INEFFECTIVE_SNAPSHOT_FILE)
    # 只保留最近 300 条，防止无限增长
    recent = list(seen)[-300:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(recent, f)


def _issue_hash(issue):
    """生成报警的唯一标识（基于游戏名+来源+问题前50字符）"""
    key = f"{issue.get('game', '')}|{issue.get('source_name', '')}|{issue.get('issue', '')[:50]}"
    return hashlib.md5(key.encode()).hexdigest()


def process_alerts(issues):
    """
    对报警列表进行处理：
    1. 🔴 加速器无效的报警：去重（报过不再报）+ 合并成一条摘要
    2. 🟢/🟡 其他报警：原样保留
    
    返回处理后的 issues 列表。
    """
    seen = _load_seen_ineffective()

    effective_issues = []       # 🟢🟡 正常输出
    ineffective_items = []      # 🔴 待合并

    for issue in issues:
        issue_text = issue.get('issue', '')

        if '🔴 [加速器无效]' in issue_text:
            # 去重：检查是否已报过
            h = _issue_hash(issue)
            if h in seen:
                continue  # 已报过，跳过
            seen.add(h)
            ineffective_items.append(issue)
        else:
            # 🟢 和 🟡 正常输出，不去重
            effective_issues.append(issue)

    # 合并 🔴 报警为一条摘要
    if ineffective_items:
        game_list = []
        for item in ineffective_items:
            game = item.get('game', '?')
            # 从 issue 文本中提取简短原因
            text = item.get('issue', '').replace('🔴 [加速器无效] ', '')
            # 截取到换行符前的第一行
            first_line = text.split('\n')[0][:80]
            game_list.append(f"{game}: {first_line}")

        summary = f"🔴 [加速器无效] 以下 {len(ineffective_items)} 项为官方维护/宕机，加速器无法解决:\n"
        summary += '\n'.join(f"    - {g}" for g in game_list)

        merged_issue = {
            'game': '汇总',
            'region': 'Global',
            'country': '',
            'issue': summary,
            'source_name': '多来源',
            'source_url': '',
        }
        # 复制第一条的 alert_type（如有）
        if ineffective_items[0].get('alert_type'):
            merged_issue['alert_type'] = ineffective_items[0]['alert_type']

        effective_issues.append(merged_issue)

    # 保存去重快照
    _save_seen_ineffective(seen)

    return effective_issues

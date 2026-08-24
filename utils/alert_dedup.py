import json
import os
from datetime import datetime, timezone, timedelta

# ==========================================
# 报警分级去重与合并
# ==========================================
# 等级定义：
# - L3 最高等级：🔴 加速器无效 / detector404 严重·大规模投诉
#   → 每次都报（持续故障保持可见）；🔴 多条合并为一条摘要
# - L2 🟢 加速器可解决 / 🔶 detector404 大量投诉
# - L1 🟡 待确认 及其他
#   → L2/L1 同一（游戏+渠道）24h 内只报一次；等级升级（如 🟡→🟢）时再报一次
# ==========================================

ALERT_LEVELS_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'game_monitor', 'alert_levels_snapshot.json'
)

DEDUP_WINDOW = timedelta(hours=24)


def _load_alert_levels():
    path = os.path.normpath(ALERT_LEVELS_SNAPSHOT_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def _save_alert_levels(seen):
    path = os.path.normpath(ALERT_LEVELS_SNAPSHOT_FILE)
    # 只保留最近 300 条，防止无限增长
    if len(seen) > 300:
        seen = dict(list(seen.items())[-300:])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False)


def _alert_level(issue):
    """报警等级：3=最高（🔴），2=🟢/🔶，1=🟡及其他。"""
    text = issue.get('issue', '')
    if '🔴' in text:
        return 3
    if '🟢' in text or '🔶' in text:
        return 2
    return 1


def _issue_key(issue):
    """去重键：同一游戏同一渠道的报警 24h 内只报一次。"""
    return f"{issue.get('game', '')}|{issue.get('source_name', '')}"


def _parse_ts(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def process_alerts(issues):
    """
    1. L3 最高等级报警：每次都报；🔴 多条合并为一条摘要
    2. L2/L1 报警：同一（游戏+渠道）24h 内只报一次，等级升级时再报一次

    返回处理后的 issues 列表。
    """
    seen = _load_alert_levels()
    now = datetime.now(timezone.utc)

    output = []
    critical_items = []  # 🔴 待合并

    for issue in issues:
        text = issue.get('issue', '')
        level = _alert_level(issue)

        if level == 3:
            if '🔴 [加速器无效]' in text:
                critical_items.append(issue)
            else:
                # 无「加速器无效」前缀的最高等级（如 detector404 严重/大规模投诉）：
                # 直接放行每次都报，不参与「加速器无效」合并（避免文案语义失真）
                output.append(issue)
            continue

        key = _issue_key(issue)
        entry = seen.get(key)
        if entry:
            last_ts = _parse_ts(entry.get('ts', ''))
            last_level = entry.get('level', 0)
            recent = last_ts and (now - last_ts) < DEDUP_WINDOW
            if recent and level <= last_level:
                continue  # 24h 内已报过且未升级，跳过

        seen[key] = {'level': level, 'ts': now.isoformat(timespec='seconds')}
        output.append(issue)

    # 🔴 合并为一条摘要（最高等级，每次都报，不去重）
    if critical_items:
        if len(critical_items) == 1:
            output.append(critical_items[0])
        else:
            game_list = []
            for item in critical_items:
                game = item.get('game', '?')
                region = item.get('region', '')
                country = item.get('country', '')
                location = f" [{country}]" if country else (f" [{region}]" if region and region != 'Global' else '')

                # 从 issue 文本中提取简短原因（去掉标签前缀）
                text = item.get('issue', '').replace('🔴 [加速器无效] ', '')
                first_line = text.split('\n')[0][:80]
                game_list.append(f"{game}{location}: {first_line}")

            summary = f"🔴 [加速器无效] 以下 {len(critical_items)} 项为官方维护/宕机，加速器无法解决:\n"
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
            if critical_items[0].get('alert_type'):
                merged_issue['alert_type'] = critical_items[0]['alert_type']
            output.append(merged_issue)

    _save_alert_levels(seen)
    return output
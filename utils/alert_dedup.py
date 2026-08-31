import json
import os
from datetime import datetime, timezone, timedelta

# ==========================================
# 报警分级去重与合并
# ==========================================
# 等级定义：
# - 「🔴 加速器无效」：官方宕机/维护类问题，不推送
# - 其他 L3：detector404 严重·大规模投诉 → 每次都报（持续故障保持可见）
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
    1. 过滤所有「🔴 [加速器无效]」报警
    2. 其余 L3 报警：每次都报
    3. L2/L1 报警：同一（游戏+渠道）24h 内只报一次，等级升级时再报一次

    返回处理后的 issues 列表。
    """
    seen = _load_alert_levels()
    now = datetime.now(timezone.utc)

    output = []

    for issue in issues:
        text = issue.get('issue', '')

        # 官方宕机/维护类问题无法通过加速器解决，按产品策略不推送。
        if '🔴 [加速器无效]' in text:
            continue

        level = _alert_level(issue)

        if level == 3:
            # 无「加速器无效」前缀的最高等级（如 detector404 严重/大规模投诉）：
            # 直接放行每次都报。
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

    _save_alert_levels(seen)
    return output

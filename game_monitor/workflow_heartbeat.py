import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import POPO_WEBHOOK_URL, send_system_heartbeat


SNAPSHOT_FILE = os.environ.get(
    "MONITOR_WORKFLOW_HEARTBEAT_SNAPSHOT",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "monitor_workflow_heartbeat_snapshot.json",
    ),
)


def _load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_snapshot(snapshot: dict) -> None:
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _today_bj() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def should_send_heartbeat() -> bool:
    snapshot = _load_snapshot()
    today = _today_bj()
    if snapshot.get("last_success_heartbeat_date") == today:
        return False
    snapshot["last_success_heartbeat_date"] = today
    snapshot["last_success_heartbeat_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save_snapshot(snapshot)
    return True


def main() -> None:
    outcomes = {
        "monitor.py": os.environ.get("GAME_MONITOR_OUTCOME", ""),
        "russia_event_monitor.py": os.environ.get("RUSSIA_EVENT_OUTCOME", ""),
        "game_calendar_monitor.py": os.environ.get("GAME_CALENDAR_OUTCOME", ""),
    }

    failed = {name: outcome for name, outcome in outcomes.items() if outcome != "success"}
    if failed:
        print(f"[WorkflowHeartbeat] 存在非成功步骤，跳过正常心跳: {failed}")
        return

    if not should_send_heartbeat():
        print("[WorkflowHeartbeat] 今日已发送过 monitor.yml 心跳，跳过。")
        return

    send_system_heartbeat(
        POPO_WEBHOOK_URL,
        "Game Server Monitor",
        (
            "monitor.py、russia_event_monitor.py、game_calendar_monitor.py 均已正常执行；"
            "若本群没有其他游戏报警，表示本日暂未发现有效游戏故障、俄罗斯活动风险或新游/热游更新。"
        ),
    )


if __name__ == "__main__":
    main()

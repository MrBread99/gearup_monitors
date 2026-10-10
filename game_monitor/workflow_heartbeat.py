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
    }

    failed = {name: outcome or "unknown" for name, outcome in outcomes.items() if outcome != "success"}
    if not failed:
        print("[WorkflowHeartbeat] 全部步骤正常执行，按策略不发送心跳。")
        return

    if not should_send_heartbeat():
        print("[WorkflowHeartbeat] 今日已发送过 monitor.yml 异常告警，跳过。")
        return

    failed_desc = "、".join(f"{name}({outcome})" for name, outcome in failed.items())
    send_system_heartbeat(
        POPO_WEBHOOK_URL,
        "Game Server Monitor",
        f"以下步骤未正常完成: {failed_desc}\n请查看 GitHub Actions 运行日志排查。",
        status="存在失败步骤",
    )


if __name__ == "__main__":
    main()

"""
竞品情报聚合入口 — 每 24 小时运行一次
将 Discord 情报侦听 + 竞品定价 + 博客 + LinkedIn 动态合并为一条 POPO 消息发出。
"""
import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import (
    send_popo_alert,
    flush_scrape_block_alerts,
    has_scrape_block_alerts,
    send_system_heartbeat,
    report_monitor_crash,
    flush_monitor_crash_alerts,
    POPO_WEBHOOK_URL,
)
from openai import OpenAI

# ==================== Discord 侦听 ====================

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
HEALTH_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "competitor_health_snapshot.json",
)
HEALTH_ALERT_FAILURES = 3

qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    timeout=120.0,  # 单次 API 调用最多 2 分钟，防止无响应卡死
) if QWEN_API_KEY else None


def _load_health_snapshot() -> dict:
    if os.path.exists(HEALTH_SNAPSHOT_FILE):
        try:
            with open(HEALTH_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"_version": 1}


def _save_health_snapshot(snapshot: dict):
    snapshot["_version"] = 1
    with open(HEALTH_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_health(snapshot: dict, key: str) -> dict:
    health_map = snapshot.setdefault("_health", {})
    return health_map.setdefault(key, {
        "consecutive_failures": 0,
        "last_success_at": "",
        "last_failure_at": "",
        "last_status_code": None,
        "last_item_count": 0,
        "failure_alert_active": False,
    })


def _record_discord_failure(snapshot: dict, status_code: int | None, reason: str):
    health = _get_health(snapshot, "discord")
    health["consecutive_failures"] = int(health.get("consecutive_failures", 0) or 0) + 1
    health["last_failure_at"] = _now_iso()
    health["last_status_code"] = status_code
    health["last_failure_reason"] = reason

    failures = health["consecutive_failures"]
    print(f"[Discord] 数据源失败 {failures}/{HEALTH_ALERT_FAILURES}: {reason}")
    if failures >= HEALTH_ALERT_FAILURES and not health.get("failure_alert_active"):
        from utils.notifier import report_scrape_block
        report_scrape_block("competitor_discord", status_code=status_code)
        health["failure_alert_active"] = True


def _record_discord_success(snapshot: dict, message_count: int) -> list:
    health = _get_health(snapshot, "discord")
    previous_failures = int(health.get("consecutive_failures", 0) or 0)
    was_alerting = bool(health.get("failure_alert_active"))

    health["consecutive_failures"] = 0
    health["last_success_at"] = _now_iso()
    health["last_status_code"] = 200
    health["last_item_count"] = message_count
    health["last_failure_reason"] = ""
    health["failure_alert_active"] = False

    if was_alerting or previous_failures >= HEALTH_ALERT_FAILURES:
        return [{
            "game": "竞品 Discord",
            "region": "Global",
            "country": "",
            "issue": (
                "竞品 Discord 数据源已恢复\n"
                f"    恢复前连续失败: {previous_failures} 次\n"
                f"    当前拉取消息数: {message_count}"
            ),
            "alert_type": "competitor_radar",
            "source_name": "竞品 Discord 情报频道",
            "source_url": f"https://discord.com/channels/@me/{TARGET_CHANNEL_ID}" if TARGET_CHANNEL_ID else "",
        }]
    return []


def _summarize_discord_msg(content, author_name):
    """调用通义千问提炼竞品 Discord 公告情报。"""
    if not qwen_client:
        return f"(AI未配置，原话如下)\n{content[:500]}"
    prompt = (
        f"你是一个全球游戏加速器（GPN）的资深商业情报分析师。\n"
        f"我们刚从竞品【{author_name}】的官方 Discord 拦截到最新公告。\n\n"
        f"【公告原文】: {content}\n\n"
        f"请分析并输出:\n"
        f"1. 【核心情报】: 用一句中文高度概括（如：修复节点、版本更新、搞促销等）\n"
        f"2. 【商业建议】: 我们应如何应对？(1-2句即可)\n"
        f"(输出纯文本，不要使用 Markdown 加粗或特殊符号)"
    )
    try:
        resp = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个敏锐的游戏加速器情报专家。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        return str(resp.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Discord] AI 分析失败: {e}")
        return f"(AI 分析失败，原话如下)\n{content[:300]}"


def collect_discord_issues():
    """
    拉取过去 24 小时内竞品 Discord 频道的消息，返回 issue 列表。
    """
    health_snapshot = _load_health_snapshot()
    issues = []
    if not DISCORD_BOT_TOKEN or not TARGET_CHANNEL_ID:
        print("[Discord] 缺少 DISCORD_BOT_TOKEN 或 TARGET_CHANNEL_ID，跳过。")
        _record_discord_failure(health_snapshot, None, "缺少 DISCORD_BOT_TOKEN 或 TARGET_CHANNEL_ID")
        _save_health_snapshot(health_snapshot)
        return issues

    url = f"https://discord.com/api/v10/channels/{TARGET_CHANNEL_ID}/messages?limit=25"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[Discord] 抓取失败 HTTP {response.status_code}: {response.text}")
            _record_discord_failure(health_snapshot, response.status_code, "Discord API 返回非 200")
            _save_health_snapshot(health_snapshot)
            return issues
        messages = response.json()
    except Exception as e:
        print(f"[Discord] 请求异常: {e}")
        _record_discord_failure(health_snapshot, None, f"请求异常: {e}")
        _save_health_snapshot(health_snapshot)
        return issues

    issues.extend(_record_discord_success(health_snapshot, len(messages)))
    _save_health_snapshot(health_snapshot)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for msg in messages:
        try:
            msg_time = datetime.fromisoformat(msg["timestamp"])
        except Exception:
            continue
        if msg_time <= cutoff:
            continue

        content = msg.get("content", "")
        if not content and "embeds" in msg:
            for embed in msg["embeds"]:
                content += embed.get("description", "") + " "
        content = content.strip()
        if not content:
            continue

        author_name = msg.get("author", {}).get("username", "Unknown")
        ai_analysis = _summarize_discord_msg(content, author_name)
        guild_id = msg.get("guild_id", "@me")
        jump_url = f"https://discord.com/channels/{guild_id}/{TARGET_CHANNEL_ID}/{msg['id']}"

        issues.append({
            "game": f"竞品Discord ({author_name})",
            "region": "Global",
            "country": "",
            "issue": ai_analysis.replace("**", "").replace("__", ""),
            "alert_type": "competitor_radar",
            "source_name": "竞品 Discord 情报频道",
            "source_url": jump_url,
        })

    print(f"[Discord] 过去 24h 内获取到 {len(issues)} 条情报。")
    return issues


# ==================== 竞品定价 ====================

def collect_pricing_issues():
    """调用 exitlag_pricing 模块，返回所有定价变动 issue。"""
    from competitor_radar.exitlag_pricing import check_all_competitor_pricing
    results = check_all_competitor_pricing()
    print(f"[Pricing] 检测到 {len(results)} 条定价变动。")
    return results


# ==================== 竞品博客 ====================

def collect_blog_issues():
    """调用 competitor_blog_monitor 模块，返回新博客文章 issue。"""
    from competitor_radar.competitor_blog_monitor import check_competitor_blogs
    results = check_competitor_blogs()
    print(f"[Blog] 检测到 {len(results)} 篇新博客文章。")
    return results


def collect_linkedin_issues():
    """调用 linkedin_monitor 模块，返回 ExitLag LinkedIn 新动态 issue。"""
    from competitor_radar.linkedin_monitor import check_exitlag_linkedin
    results = check_exitlag_linkedin()
    print(f"[LinkedIn] 检测到 {len(results)} 条新动态。")
    return results


def _get_blog_status():
    """获取博客监控状态摘要（用于心跳消息）。"""
    try:
        from competitor_radar.competitor_blog_monitor import get_blog_status_summary
        return get_blog_status_summary()
    except Exception:
        return ""


def _get_linkedin_status():
    """获取 LinkedIn 当前最新动态摘要（用于心跳消息）。"""
    try:
        from competitor_radar.linkedin_monitor import get_linkedin_status_summary
        return get_linkedin_status_summary()
    except Exception:
        return ""


# ==================== 主入口 ====================

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    print("=" * 50)
    print("竞品情报聚合监控 (每24小时)")
    print("=" * 50)

    all_issues = []

    # 1. Discord 情报
    try:
        all_issues.extend(collect_discord_issues())
    except Exception as e:
        print(f"[Discord] 执行失败: {e}")
        report_monitor_crash("竞品情报: Discord", e)

    # 2. 竞品定价
    try:
        all_issues.extend(collect_pricing_issues())
    except Exception as e:
        print(f"[Pricing] 执行失败: {e}")
        report_monitor_crash("竞品情报: 定价监控", e)

    # 3. 竞品博客
    try:
        all_issues.extend(collect_blog_issues())
    except Exception as e:
        print(f"[Blog] 执行失败: {e}")
        report_monitor_crash("竞品情报: 博客监控", e)

    # 4. ExitLag LinkedIn 动态
    try:
        all_issues.extend(collect_linkedin_issues())
    except Exception as e:
        print(f"[LinkedIn] 执行失败: {e}")
        report_monitor_crash("竞品情报: LinkedIn 动态", e)

    # 汇总发送 — 所有情报合并为一条消息
    if all_issues:
        send_popo_alert(POPO_WEBHOOK_URL, all_issues)
    else:
        print("过去 24 小时内无竞品情报变动，静默退出。")
        if not has_scrape_block_alerts():
            blog_status = _get_blog_status()
            linkedin_status = _get_linkedin_status()
            summary = "过去 24 小时无新增竞品情报，且未检测到数据源异常。"
            if blog_status:
                summary += f"\n\n当前各竞品最新博客:\n{blog_status}"
            if linkedin_status:
                summary += f"\n\n当前 LinkedIn 最新动态:\n{linkedin_status}"
            send_system_heartbeat(
                POPO_WEBHOOK_URL,
                "竞品情报聚合",
                summary,
            )

    # 数据源异常汇总（如有）
    flush_scrape_block_alerts(POPO_WEBHOOK_URL)
    # 内部崩溃汇总（如有）
    flush_monitor_crash_alerts(POPO_WEBHOOK_URL)


if __name__ == "__main__":
    main()

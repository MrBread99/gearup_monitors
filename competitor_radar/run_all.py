"""
竞品情报聚合入口 — 每 24 小时运行一次
将 Discord 情报侦听 + 竞品定价监控合并为一条 POPO 消息发出。
"""
import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL
from openai import OpenAI

# ==================== Discord 侦听 ====================

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")

qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None


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
    issues = []
    if not DISCORD_BOT_TOKEN or not TARGET_CHANNEL_ID:
        print("[Discord] 缺少 DISCORD_BOT_TOKEN 或 TARGET_CHANNEL_ID，跳过。")
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
            return issues
        messages = response.json()
    except Exception as e:
        print(f"[Discord] 请求异常: {e}")
        return issues

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
    all_issues.extend(collect_discord_issues())

    # 2. 竞品定价
    all_issues.extend(collect_pricing_issues())

    # 汇总发送 — 所有情报合并为一条消息
    if all_issues:
        send_popo_alert(POPO_WEBHOOK_URL, all_issues)
    else:
        print("过去 24 小时内无竞品情报变动，静默退出。")

    # 数据源异常汇总（如有）
    flush_scrape_block_alerts(POPO_WEBHOOK_URL)


if __name__ == "__main__":
    main()

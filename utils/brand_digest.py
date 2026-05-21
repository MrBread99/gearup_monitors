import json
import os
import re
from datetime import datetime, timezone, timedelta

from utils.brand_report import GITHUB_REPORT_URL


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_FILE = os.path.join(ROOT_DIR, "brand_monitor", "brand_digest_snapshot.json")


REGION_LABELS = {
    "South Korea": "韩国",
    "Japan": "日本",
    "Taiwan": "台湾",
    "Russia": "俄语区",
    "Middle East": "中东",
}


def _load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_snapshot(candidates):
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
    snapshot = {
        "updated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "items": {c["key"]: c["evidence"] for c in candidates},
    }
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _count(text, label):
    match = re.search(rf"{label}\s*(\d+)", text)
    return int(match.group(1)) if match else 0


def _match_int(text, pattern):
    match = re.search(pattern, text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _region_label(item):
    source = item.get("source_name", "")
    if source == "YouTube":
        return "YouTube"
    country = item.get("country") or item.get("region") or "Global"
    return REGION_LABELS.get(country, country)


def _source_label(item):
    source = item.get("source_name", "")
    if "DC Inside" in source:
        return "DC Inside"
    if source == "YouTube":
        return "YouTube"
    return source.split("/")[0].strip() or "社区"


def _extract_competitors(text):
    match = re.search(r"涉及竞品:\s*([^\n]+)", text)
    if not match:
        return ""
    names = re.sub(r"\[[^\]]+\]", "", match.group(1)).strip(" 。")
    return "" if names in ("无", "暂无") else names


def _extract_insight(text):
    match = re.search(r"商业洞察:\s*([^\n]+)", text)
    if not match:
        return ""
    insight = re.sub(r"\[[^\]]+\]", "", match.group(1)).strip(" 。")
    return insight


def _detect_games(text):
    games = []
    for game in ("COD Mobile", "eFootball", "PUBG", "CS2"):
        if game.lower() in text.lower():
            games.append(game)
    return " / ".join(games[:2]) if games else "游戏场景"


def _candidate_from_item(item):
    text = (item.get("issue") or "").replace("**", "").replace("__", "")
    region = _region_label(item)
    source = _source_label(item)
    negative_count = _count(text, "负面")
    positive_count = _count(text, "正面")
    competitors = _extract_competitors(text)
    insight = _extract_insight(text)

    if "退款" in text or "환불" in text:
        count = negative_count or 1
        return {
            "key": f"{region}:refund:{count}",
            "score": 100,
            "title": f"[{region}] 退款投诉连续出现",
            "evidence": f"{source} 新增 {count} 条退款相关负面",
            "suggestion": "检查韩国退款链路与客服话术" if region == "韩国" else "检查退款链路与客服话术",
        }

    if item.get("source_name") == "YouTube":
        days = _match_int(text, r"过去(\d+)天")
        video_count = _match_int(text, r"共\s*([\d,]+)\s*个视频")
        top_views = _match_int(text, r"([\d,]+)\s*播放")
        if positive_count or video_count:
            games = _detect_games(text)
            evidence_parts = []
            if days and video_count:
                evidence_parts.append(f"{days} 天 {video_count} 个视频")
            if top_views:
                evidence_parts.append(f"最高播放 {top_views:,}")
            return {
                "key": f"youtube:positive:{video_count}:{top_views}",
                "score": 70,
                "title": f"[YouTube] {games} 正面短视频有扩散",
                "evidence": "，".join(evidence_parts) or "YouTube 出现正面短视频",
                "suggestion": "提炼“降低延迟前后对比”素材",
            }

    if negative_count:
        return {
            "key": f"{region}:negative:{negative_count}",
            "score": 90,
            "title": f"[{region}] 负面舆情需要关注",
            "evidence": f"{source} 新增 {negative_count} 条负面",
            "suggestion": insight or "定位具体问题场景并补充客服说明",
        }

    if competitors:
        return {
            "key": f"{region}:competitor:{competitors}",
            "score": 60,
            "title": f"[{region}] 出现竞品对比讨论",
            "evidence": f"提及竞品: {competitors}",
            "suggestion": "补充对比话术与场景化优势说明",
        }

    return None


def build_brand_monitor_message(items, max_items=3, update_snapshot=True):
    candidates = []
    for item in items:
        candidate = _candidate_from_item(item)
        if candidate:
            candidates.append(candidate)

    candidates.sort(key=lambda c: c["score"], reverse=True)

    old_items = _load_snapshot().get("items", {})
    fresh = [c for c in candidates if old_items.get(c["key"]) != c["evidence"]]
    selected = fresh[:max_items]
    if update_snapshot:
        _save_snapshot(candidates[:20])

    lines = ["【品牌舆情监控】", ""]

    if selected:
        for index, item in enumerate(selected, 1):
            if index > 1:
                lines.append("")
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   证据: {item['evidence']}")
            lines.append(f"   建议: {item['suggestion']}")
    else:
        lines.append("本次无新增重点品牌舆情。")

    lines.append("")
    lines.append(f"*详细报告链接: {GITHUB_REPORT_URL}*")
    return "\n".join(lines)

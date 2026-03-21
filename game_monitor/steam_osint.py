import requests
import time
from datetime import datetime, timezone, timedelta

# ==========================================
# Steam 近期差评监控模块
# ==========================================
# 利用 Steam Store API 拉取指定游戏的近期差评，
# 匹配网络故障相关关键词（lag, ping, packet loss 等），
# 作为 game-network-radar 的一个全球性数据渠道。
#
# Steam Store Reviews API 文档:
# https://partner.steamgames.com/doc/store/getreviews
# 此接口无需 API Key，直接可用。
# ==========================================

# Steam AppID 映射 — 从统一游戏注册表 (game_registry.py) 加载
from game_registry import get_steam_app_map
STEAM_APP_MAP = get_steam_app_map()

# 网络故障相关关键词（多语言）
NETWORK_KEYWORDS_EN = [
    "LAG", "PING", "LATENCY", "PACKET LOSS", "PACKETLOSS",
    "DISCONNECT", "DISCONNECTED", "RUBBER BAND", "RUBBERBANDING",
    "DESYNC", "HIGH PING", "SPIKE", "STUTTERING", "NETWORK",
    "SERVER", "SERVERS DOWN", "CANT CONNECT", "CONNECTION",
    "TIMEOUT", "ROUTING", "JITTER"
]

# 中文关键词（Steam 以繁体中文玩家为主，兼顾简中）
NETWORK_KEYWORDS_ZH = [
    # 繁体中文（台港澳玩家）
    "斷線", "爆PING", "卡頓", "連不上", "進不去", "伺服器",
    "馬鈴薯", "延遲", "丟包", "掉線", "高PING", "網路",
    "回彈", "抖動", "橡皮筋",
    # 简体中文
    "延迟", "卡顿", "丢包", "掉线", "断线", "网络",
    "连不上", "服务器", "橡皮筋", "回弹", "抖动"
]

# 日语关键词
NETWORK_KEYWORDS_JP = [
    "鯖落ち", "ラグい", "ラグ", "繋がらない", "落ちた",
    "通信エラー", "マッチしない", "回線落ち", "回線", "切断",
    "ピング", "パケロス", "パケットロス", "重い", "カクカク"
]

# 韩语关键词
NETWORK_KEYWORDS_KR = [
    "섭터짐", "핑", "렉", "접속불가", "튕김", "서버 다운",
    "서버", "끊김", "패킷로스", "지연", "랙", "디스코"
]

# 俄语关键词
NETWORK_KEYWORDS_RU = [
    "ПИНГ", "ЛАГ", "ЛАГИ", "ЗАДЕРЖКА", "ПОТЕРЯ ПАКЕТОВ",
    "ДИСКОННЕКТ", "СЕРВЕР"
]

# 阿拉伯语关键词
NETWORK_KEYWORDS_AR = [
    "لاق", "تأخير", "بنق", "بينق", "تقطيع", "قطع",
    "سيرفر", "انقطاع", "مشكلة اتصال", "فقدان حزم",
    "تعليق", "هنق", "ضعف الاتصال", "السيرفر طاح",
    "مشكلة بالنت", "نت", "تهنيق"
]

# 越南语关键词
NETWORK_KEYWORDS_VI = [
    "LAG", "GIẬT", "GIẬT LAG", "MẤT KẾT NỐI", "PING CAO",
    "RỚT MẠNG", "ĐỨNG HÌNH", "DELAY", "MẤT GÓI", "NGẮT KẾT NỐI",
    "SERVER DIE", "SERVER SẬP", "KHÔNG VÀO ĐƯỢC", "MẠNG YẾU",
    "TELEPORT", "BỊ OUT", "ĐỨNG GAME"
]

# 菲律宾语/他加禄语关键词
NETWORK_KEYWORDS_TL = [
    "LAG", "LAGGY", "NAKAKAINIS", "HINDI MAKACONNECT", "MABAGAL",
    "NAWAWALA", "PATAY SERVER", "DISCONNECTED", "PING MATAAS",
    "HINDI MAKAPASOK", "NAPUTOL", "BUMABAGSAK", "SOBRANG LAG"
]

# 印尼语关键词
NETWORK_KEYWORDS_ID = [
    "LAG", "NGELAG", "PATAH-PATAH", "PUTUS KONEKSI", "PING TINGGI",
    "SERVER DOWN", "GAK BISA MASUK", "DISCONNECT", "LEMOT",
    "PAKET HILANG", "JARINGAN JELEK", "GANGGUAN SERVER", "NGEFREEZE"
]

ALL_KEYWORDS = (
    NETWORK_KEYWORDS_EN + NETWORK_KEYWORDS_ZH +
    NETWORK_KEYWORDS_JP + NETWORK_KEYWORDS_KR +
    NETWORK_KEYWORDS_RU + NETWORK_KEYWORDS_AR +
    NETWORK_KEYWORDS_VI + NETWORK_KEYWORDS_TL +
    NETWORK_KEYWORDS_ID
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/2.1'
}


def check_steam_reviews(game_name, hours_window=2, threshold=5):
    """
    通过 Steam Store Reviews API 拉取指定游戏的近期差评，
    筛选网络问题相关关键词，判断是否达到报警阈值。

    :param game_name: 游戏名
    :param hours_window: 时间窗口（小时），默认 2 小时
    :param threshold: 匹配到的差评数量阈值，默认 5 条
    :return: issue dict 或 None
    """
    app_id = STEAM_APP_MAP.get(game_name)
    if not app_id:
        return None

    # Steam Reviews API 参数说明:
    # review_type=negative  只拉差评
    # purchase_type=all     包含免费游戏玩家
    # num_per_page=100      一次最多 100 条
    # filter=recent         按最近排序
    # language=all          所有语言
    url = (
        f"https://store.steampowered.com/appreviews/{app_id}"
        f"?json=1&filter=recent&language=all&review_type=negative"
        f"&purchase_type=all&num_per_page=100"
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[Steam] {game_name}: HTTP {response.status_code}")
            return None

        data = response.json()
        if not data.get('success'):
            print(f"[Steam] {game_name}: API returned success=false")
            return None

        reviews = data.get('reviews', [])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_window)

        network_complaints = 0
        matched_keywords = set()
        total_upvotes = 0

        for review in reviews:
            # 过滤时间窗口
            created = datetime.fromtimestamp(
                review.get('timestamp_created', 0), timezone.utc
            )
            if created < cutoff:
                continue

            # 只处理差评（API 已过滤，但 double check）
            if review.get('voted_up', True):
                continue

            text = review.get('review', '').upper()

            for kw in ALL_KEYWORDS:
                if kw in text:
                    network_complaints += 1
                    matched_keywords.add(kw)
                    total_upvotes += review.get('votes_up', 0)
                    break  # 一条评论只计一次

        # 热度飙升：单条差评被大量点赞
        is_viral = total_upvotes > 30

        if is_viral:
            threshold = 1

        if network_complaints >= threshold:
            viral_tag = "🔥 [热度飙升] " if is_viral else ""
            return {
                'game': game_name,
                'region': 'Global',
                'country': '',
                'issue': (
                    f"🟢 [加速器可解决] {viral_tag}Steam 差评涌现网络问题 "
                    f"(匹配词: {', '.join(list(matched_keywords)[:5])}, "
                    f"共{network_complaints}条差评/{hours_window}h)"
                ),
                'source_name': 'Steam Reviews',
                'source_url': f'https://store.steampowered.com/app/{app_id}/#app_reviews_hash'
            }

    except Exception as e:
        print(f"[Steam] 检测 {game_name} 差评时发生异常: {e}")

    return None


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Steam OSINT...")
    for game in STEAM_APP_MAP:
        if STEAM_APP_MAP[game]:
            res = check_steam_reviews(game)
            print(f"{game}: {res}")

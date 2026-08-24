import requests
import json
import os
import sys
import html
import re
from datetime import datetime, timezone, timedelta
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import (
    POPO_WEBHOOK_URL,
    flush_scrape_block_alerts,
    has_scrape_block_alerts,
    report_scrape_block,
    send_popo_alert,
    send_system_heartbeat,
)
from utils.reddit_client import get_last_reddit_request_meta, reddit_get

# 通义千问 API 客户端
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None

# ==========================================
# 新游上线 / 热游大版本更新监控
# ==========================================
# 功能：
# 1. 监控已追踪的 15 款游戏的大版本更新/新赛季（Steam News API）
# 2. 监控 Steam 热门新发售的联机游戏（潜在加速需求）
# 3. 监控 Steam 即将发售的热门联机游戏
#
# 价值：
# - 大版本更新当天用户量暴增，配合营销推送
# - 新赛季是加速器流量高峰
# - 热门新游上线前提前准备加速支持
# ==========================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

STEAM_API_KEY = os.environ.get('STEAM_API_KEY', '')

# 已监控游戏的 Steam AppID — 从统一游戏注册表 (game_registry.py) 加载
# 过滤掉没有 Steam AppID 的游戏（只有有 AppID 的游戏才能查 News）
from game_registry import get_steam_app_map
TRACKED_GAMES = {name: appid for name, appid in get_steam_app_map().items() if appid is not None}

# 非 Steam 游戏通过 Reddit 检测更新（含预告）
# official_url:   直接抓取的官方 game-updates 页面（Riot 系）
# blizzard_url:   Blizzard 官方新闻页面（OW2/WoW）
# hoyolab_gid:    HoyoLab API game ID（原神=2, 崩铁=6, 绝区零=8）
NON_STEAM_GAMES = {
    'League of Legends': {
        'subreddit': 'leagueoflegends',
        'keywords': ['patch', 'update', 'season', 'preseason', 'preview', 'upcoming', 'pbe'],
        'official_url': 'https://www.leagueoflegends.com/en-us/news/game-updates/',
    },
    'Valorant': {
        'subreddit': 'VALORANT',
        'keywords': ['patch', 'update', 'season', 'episode', 'act', 'upcoming', 'preview', 'roadmap'],
        'official_url': 'https://playvalorant.com/en-us/news/game-updates/',
    },
    'Overwatch 2': {
        'subreddit': 'Overwatch',
        'keywords': ['patch', 'update', 'season', 'hero', 'preview', 'ptr', 'upcoming'],
        'blizzard_url': 'https://overwatch.blizzard.com/en-us/news/patch-notes/',
    },
    'World of Warcraft': {
        'subreddit': 'wow',
        'keywords': ['patch', 'update', 'expansion', 'season', 'hotfix', 'maintenance', 'ptr', 'upcoming'],
        'blizzard_url': 'https://worldofwarcraft.blizzard.com/en-us/news',
    },
    'Genshin Impact': {
        'subreddit': 'Genshin_Impact',
        'keywords': ['update', 'version', 'patch', 'banner', 'preview', 'livestream', 'maintenance'],
        'hoyolab_gid': 2,
    },
    'Honkai Star Rail': {
        'subreddit': 'HonkaiStarRail',
        'keywords': ['update', 'version', 'patch', 'banner', 'preview', 'livestream', 'maintenance'],
        'hoyolab_gid': 6,
    },
    'Zenless Zone Zero': {
        'subreddit': 'ZenlessZoneZero',
        'keywords': ['update', 'version', 'patch', 'banner', 'preview', 'maintenance', 'livestream'],
        'hoyolab_gid': 8,
    },
    # 以下游戏无可靠官方 API，继续用 Reddit
    'Fortnite': {'subreddit': 'FortNiteBR', 'keywords': ['update', 'season', 'chapter', 'patch', 'downtime', 'upcoming', 'teaser', 'countdown']},
    'Call of Duty': {'subreddit': 'CallOfDuty', 'keywords': ['update', 'season', 'patch', 'warzone', 'upcoming', 'roadmap', 'preview']},
    'Wuthering Waves': {'subreddit': 'WutheringWaves', 'keywords': ['update', 'version', 'patch', 'banner', 'preview', 'maintenance', 'convene']},
    'Roblox': {'subreddit': 'roblox', 'keywords': ['update', 'patch', 'outage', 'down', 'maintenance', 'change']},
    'Aion 2': {'subreddit': 'aion', 'keywords': ['update', 'patch', 'maintenance', 'launch', 'upcoming', 'beta', 'release date']},
}

# 大版本更新 + 预告关键词（出现在 Steam News 标题中）
UPDATE_KEYWORDS = [
    # 已上线更新
    "UPDATE", "PATCH", "SEASON", "MAJOR", "RELEASE",
    "WIPE", "NEW MAP", "NEW AGENT", "NEW HERO",
    "CHAPTER", "EPISODE", "ACT", "EXPANSION",
    "LEAGUE", "RANKED", "NEW WEAPON", "REWORK",
    "OPERATION", "EVENT",
    # 预告类关键词
    "COMING SOON", "UPCOMING", "PREVIEW", "TEASER",
    "ROADMAP", "ANNOUNCEMENT", "REVEAL", "COUNTDOWN",
    "DEV UPDATE", "DEV BLOG", "DEVELOPER UPDATE",
    "PLANNED", "SCHEDULED", "MAINTENANCE NOTICE",
    "NEXT SEASON", "NEXT UPDATE", "WHAT'S NEXT",
]

# 联机游戏的 Steam 标签（用于过滤新游）
ONLINE_TAGS = [
    "Multiplayer", "Online Co-Op", "Online PvP", "MMO",
    "Massively Multiplayer", "Co-op", "PvP", "Battle Royale",
    "FPS", "Extraction Shooter", "MMORPG", "MOBA"
]

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'game_calendar_snapshot.json'
)

CALENDAR_SEEN_KEY_LIMIT = 1000
CALENDAR_HEARTBEAT_STATE_KEY = 'game_calendar_heartbeat_date'
CALENDAR_DIGEST_STATE_KEY = 'game_calendar_digest_date'
CALENDAR_PENDING_ISSUES_KEY = 'pending_calendar_issues'
CALENDAR_PENDING_ISSUE_LIMIT = 200
PER_SOURCE_ALERT_LIMIT = 2
STEAM_NEWS_403_FAIL_THRESHOLD = 5   # 连续 5 次 403 才静默（原 2 次太激进）
STEAM_NEWS_403_BACKOFF_DAYS = 3     # 静默 3 天（原 7 天太久）


def fetch_current_players(app_id):
    """获取 Steam 游戏当前在线人数（免费公开 API，无需 key）。失败返回 0。"""
    if not app_id:
        return 0
    try:
        resp = requests.get(
            f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}",
            headers=HEADERS, timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get('response', {}).get('player_count', 0) or 0
    except Exception:
        pass
    return 0


def estimate_game_hype(app_data, rank=None, category_label=''):
    """
    预估新游热度（0-100 分），基于多维度打分。
    在线人数是最硬的热度信号；Top Sellers 是销量榜，排名权重高于 New Releases。
    """
    score = 0

    if not app_data:
        return 50  # 无数据默认中等

    # 1. 当前在线人数 (最高 30 分；未发售游戏恒为 0)
    players = fetch_current_players(app_data.get('steam_appid'))
    if players > 100000:
        score += 30
    elif players > 50000:
        score += 25
    elif players > 20000:
        score += 20
    elif players > 10000:
        score += 15
    elif players > 5000:
        score += 10
    elif players > 1000:
        score += 6
    elif players > 100:
        score += 3

    # 2. 榜单排名 (New Releases 最高 20 分；Top Sellers 为销量榜，权重 1.5x)
    if rank:
        rank_score = max(0, 20 - (rank - 1) * 2)  # #1=20, #2=18, ..., #10=2
        if category_label == 'Top Sellers':
            rank_score = int(rank_score * 1.5)
        score += rank_score

    # 3. 评论数/关注度 (最高 15 分)
    recommendations = app_data.get('recommendations', {}).get('total', 0)
    if recommendations > 50000:
        score += 15
    elif recommendations > 10000:
        score += 12
    elif recommendations > 5000:
        score += 9
    elif recommendations > 1000:
        score += 6
    elif recommendations > 100:
        score += 3

    # 4. 免费游戏加成 (最高 10 分)
    is_free = app_data.get('is_free', False)
    if is_free:
        score += 10

    # 5. 热门游戏类型加成 (最高 10 分)
    genres = [g.get('description', '') for g in app_data.get('genres', [])]
    hot_genres = {'Action': 5, 'FPS': 8, 'RPG': 5, 'Adventure': 3,
                  'Massively Multiplayer': 8, 'Strategy': 3, 'Sports': 4,
                  'Racing': 3, 'Simulation': 2}
    genre_bonus = sum(hot_genres.get(g, 0) for g in genres)
    score += min(10, genre_bonus)

    # 6. 联机类型加成 (最高 15 分)
    categories = [c.get('description', '') for c in app_data.get('categories', [])]
    if 'Online PvP' in categories:
        score += 10
    elif 'Online Co-op' in categories:
        score += 7
    elif 'Multi-player' in categories:
        score += 5
    if 'MMO' in categories or 'Massively Multiplayer' in categories:
        score += 5

    return min(100, score)


def estimate_update_priority(reddit_score=0, accel_need_text=''):
    """
    预估热游更新的综合优先级（0-100 分），
    结合社区热度（Reddit score）和加速需求强度。
    """
    priority = 0

    # 1. Reddit 热度 (最高 50 分)
    if reddit_score > 5000:
        priority += 50
    elif reddit_score > 2000:
        priority += 40
    elif reddit_score > 1000:
        priority += 30
    elif reddit_score > 500:
        priority += 25
    elif reddit_score > 200:
        priority += 20
    elif reddit_score > 100:
        priority += 15
    elif reddit_score > 0:
        priority += 10

    # 2. 加速需求星级 (最高 50 分)
    star_count = accel_need_text.count('⭐')
    priority += star_count * 10

    return min(100, priority)


def format_hype_label(score):
    """将热度分数转换为可读标签"""
    if score >= 80:
        return f"🔥🔥🔥 热度极高 ({score}分)"
    elif score >= 60:
        return f"🔥🔥 热度较高 ({score}分)"
    elif score >= 40:
        return f"🔥 热度中等 ({score}分)"
    elif score >= 20:
        return f"热度一般 ({score}分)"
    else:
        return f"热度较低 ({score}分)"


def analyze_acceleration_need(game_name, app_data=None, update_content=''):
    """
    分析游戏的加速需求等级。
    结合 Steam 结构化数据（联机类型、游戏类型）和 Qwen AI 综合判断。

    返回格式：
    加速需求: ⭐⭐⭐⭐⭐ 极高 - FPS 竞技联机，延迟敏感度极高，且部分地区有封锁风险
    """
    # Step 1: 从结构化数据提取关键特征
    features = {
        'is_online': False,
        'online_type': [],      # PvP / Co-op / MMO
        'genres': [],
        'latency_sensitive': False,
        'region_locked': False,
        'supported_languages': '',
    }

    if app_data:
        categories = app_data.get('categories', [])
        cat_names = [c.get('description', '') for c in categories]
        genres = app_data.get('genres', [])
        genre_names = [g.get('description', '') for g in genres]

        features['genres'] = genre_names

        # 判断联机类型
        online_types = []
        if 'Online PvP' in cat_names:
            online_types.append('Online PvP')
        if 'Online Co-op' in cat_names:
            online_types.append('Online Co-op')
        if 'Multi-player' in cat_names:
            online_types.append('Multi-player')
        if 'MMO' in cat_names or 'Massively Multiplayer' in cat_names:
            online_types.append('MMO')

        features['is_online'] = bool(online_types)
        features['online_type'] = online_types

        # 延迟敏感度判断（FPS/格斗/MOBA/竞速/大逃杀 > 其他联机）
        high_sensitivity_genres = ['FPS', 'Shooter', 'Fighting', 'MOBA', 'Racing',
                                   'Battle Royale', 'Sports']
        features['latency_sensitive'] = any(
            g in genre_names or g.lower() in [gn.lower() for gn in genre_names]
            for g in high_sensitivity_genres
        )

        features['supported_languages'] = app_data.get('supported_languages', '')

    # Step 2: 调用 Qwen 做综合分析
    if not qwen_client:
        # 无 AI，基于规则给出简单评级
        if not features['is_online']:
            return "⭐ 低 - 单机游戏，无联机需求"
        elif features['latency_sensitive']:
            return "⭐⭐⭐⭐⭐ 极高 - 竞技联机，延迟敏感度高"
        elif 'MMO' in features['online_type']:
            return "⭐⭐⭐⭐ 高 - MMO 联机，跨区组队需要加速"
        else:
            return "⭐⭐⭐ 中 - 有联机模式"

    features_text = f"""联机类型: {', '.join(features['online_type']) if features['online_type'] else '无/未知'}
游戏类型: {', '.join(features['genres']) if features['genres'] else '未知'}
延迟敏感: {'是' if features['latency_sensitive'] else '否/未知'}
支持语言: {features['supported_languages'][:200] if features['supported_languages'] else '未知'}"""

    prompt = f"""你是一个游戏加速器产品专家。请从以下角度分析这款游戏的加速需求，并给出 1-5 星评级：

【游戏】: {game_name}
【结构化特征】:
{features_text}
【更新/游戏内容】: {update_content[:500] if update_content else '无'}

分析角度:
1. 是否联网游戏（纯单机=无需求，有联机=有需求）
2. 对延迟的敏感度（FPS/格斗/MOBA 极高，MMO/合作 中等，回合制 低）
3. 是否有跨区服务器（全球服/亚服/欧服分区 = 跨区加速需求）
4. 是否有地区封锁或限制风险（如某些游戏在特定国家不可用）
5. 本次更新是否会带来玩家涌入（新赛季/大版本/免费活动）
6. 联机稳定性需求（合作/社交联机、房主制 P2P 联机在部分地区存在连接失败、掉线、NAT 问题，加速器可改善）

评级规则：纯单机=1星；有联机模式最低 3 星（休闲合作/社交联机也不例外，其痛点是连接稳定性而非低延迟）；MMO/跨区组队=4星起；竞技 FPS/格斗/MOBA=5星。

请严格按以下格式输出一行（禁止换行，禁止 Markdown）:
⭐评级(1-5星) 需求等级(极高/高/中/低/无) - 一句话分析理由(30字以内)"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是游戏加速器产品专家，输出简洁一行。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=100
        )
        result = str(response.choices[0].message.content).strip()
        # 确保只返回一行
        result = result.split('\n')[0]
        # 联机游戏保底 3 星：休闲合作/社交联机常被 AI 低估，
        # 其真实痛点是联机建立失败、掉线、NAT 问题（部分地区加速需求）
        if features['is_online'] and 0 < result.count('⭐') < 3:
            result = "⭐⭐⭐ 中 - 联机游戏，部分地区存在联机稳定性/跨区连接需求"
        return result
    except Exception as e:
        print(f"[Calendar] AI 加速需求分析失败: {e}")
        if not features['is_online']:
            return "⭐ 低 - 单机游戏"
        elif features['latency_sensitive']:
            return "⭐⭐⭐⭐⭐ 极高 - 竞技联机"
        else:
            return "⭐⭐⭐ 中 - 联机游戏"


def infer_top_regions(app_data):
    """
    根据 Steam appdetails 的 supported_languages 和 ratings 推算 TOP5 目标市场。
    有全语音支持的语言 > 有字幕支持的语言 > 有分级的地区。
    """
    # 语言到地区的映射
    LANG_REGION_MAP = {
        'English': ('North America / Europe', 30),
        'Korean': ('South Korea', 15),
        'Japanese': ('Japan', 15),
        'Simplified Chinese': ('China', 12),
        'Traditional Chinese': ('Taiwan / Hong Kong', 10),
        'Russian': ('Russia / CIS', 10),
        'Portuguese - Brazil': ('Brazil / LATAM', 8),
        'Spanish - Latin America': ('LATAM', 6),
        'Spanish - Spain': ('Spain', 5),
        'French': ('France', 5),
        'German': ('Germany', 5),
        'Turkish': ('Turkey / Middle East', 5),
        'Polish': ('Poland / Eastern EU', 4),
        'Italian': ('Italy', 3),
        'Thai': ('Thailand / SEA', 5),
        'Vietnamese': ('Vietnam / SEA', 5),
        'Indonesian': ('Indonesia / SEA', 5),
        'Arabic': ('Middle East', 5),
    }

    # 分级机构到地区的映射
    RATING_REGION_MAP = {
        'esrb': ('North America', 5),
        'pegi': ('Europe', 5),
        'cero': ('Japan', 8),
        'kgrb': ('South Korea', 8),
        'csrr': ('Taiwan', 6),
        'usk': ('Germany', 3),
        'dejus': ('Brazil', 5),
        'oflc': ('Australia', 3),
        'fpb': ('South Africa', 2),
        'mda': ('Singapore / SEA', 4),
        'igrs': ('Indonesia / SEA', 4),
    }

    region_scores = {}

    # 从 supported_languages 推算
    langs_str = app_data.get('supported_languages', '')
    for lang, (region, base_score) in LANG_REGION_MAP.items():
        if lang in langs_str:
            # 全语音支持权重更高
            score = base_score * 1.5 if f'{lang}<strong>*</strong>' in langs_str else base_score
            region_scores[region] = region_scores.get(region, 0) + score

    # 从 ratings 推算
    ratings = app_data.get('ratings', {})
    for rating_key, (region, score) in RATING_REGION_MAP.items():
        if rating_key in ratings:
            region_scores[region] = region_scores.get(region, 0) + score

    # 排序取 TOP5
    sorted_regions = sorted(region_scores.items(), key=lambda x: x[1], reverse=True)
    top5 = sorted_regions[:5]

    if not top5:
        return "未知"

    # 计算占比
    total = sum(s for _, s in top5)
    result_parts = []
    for region, score in top5:
        pct = round(score / total * 100)
        result_parts.append(f"{region} {pct}%")

    return ', '.join(result_parts)


def summarize_new_game(game_name, description):
    """
    调用通义千问对新游戏进行玩法介绍。
    """
    if not qwen_client:
        from html import unescape
        import re
        clean = re.sub(r'<[^>]+>', '', unescape(description))
        return clean[:200].strip() + "..."

    from html import unescape
    import re
    clean_desc = re.sub(r'<[^>]+>', '', unescape(description))

    prompt = f"""你是一个游戏行业分析师。请根据以下游戏介绍，用 2-3 句中文简要介绍这款游戏的核心玩法和特色，并说明是否有联机/多人模式。

【游戏名称】: {game_name}
【游戏介绍】: {clean_desc[:1500]}

要求: 纯文本输出，禁止 Markdown，不超过 3 句话。"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个游戏行业分析师，输出简洁中文。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Calendar] AI 新游介绍失败: {e}")
        return clean_desc[:200].strip() + "..."


def summarize_reddit_title(title):
    """Reddit 新游/上新帖英文标题 → AI 一句话中文摘要。无 AI 或失败返回空。"""
    if not qwen_client or not title:
        return ''
    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是游戏行业编辑，输出简洁一行中文。"},
                {"role": "user", "content": f"把这条游戏相关英文帖子标题翻译并概括为一句中文（30字以内，说明什么游戏、什么事）：{title[:300]}"}
            ],
            temperature=0.2,
            max_tokens=80
        )
        return str(response.choices[0].message.content).strip().split('\n')[0]
    except Exception:
        return ''


def _summary_suffix(title):
    """生成报警文本的摘要后缀行；无摘要时返回空串。"""
    s = summarize_reddit_title(title)
    return f"\n    摘要: {s}" if s else ''


def summarize_update(game_name, title, content):
    """
    调用通义千问对游戏更新内容做中文摘要，提取：
    1. 更新/上线时间
    2. 2-3 句内容总结
    3. 对加速器的影响判断
    """
    if not qwen_client:
        # AI 未配置，退化为截取前 200 字
        snippet = content[:200].replace('\n', ' ').strip()
        return f"(AI未配置) {snippet}..."

    prompt = f"""你是一个游戏加速器产品经理的助手。请分析以下游戏更新公告，用纯文本输出（禁止 Markdown 格式）：

【游戏】: {game_name}
【标题】: {title}
【内容】: {content[:1500]}

请严格按以下格式输出：
更新时间: （提取公告中提到的具体日期/时间，如果没有明确提到则写"未提及"）
内容摘要: （2-3 句话概括核心更新内容，用中文）
加速器影响: （简短判断：新地图/新赛季/新模式等会带来玩家涌入需提前准备加速支持；反作弊/UI更新等对加速器无直接影响）
"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个专业的游戏行业分析助手，输出简洁的纯文本。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Calendar] AI 摘要失败: {e}")
        snippet = content[:200].replace('\n', ' ').strip()
        return f"(AI调用失败) {snippet}..."


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


def _today_bj():
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')


def _truncate_text(text, max_len=120):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 1].rstrip() + '…'


def _strip_leading_symbols(text):
    return re.sub(r'^[^\w\u4e00-\u9fff\[]+\s*', '', text or '').strip()


def _split_issue_tag_and_title(issue_text):
    first_line = _strip_leading_symbols((issue_text or '').splitlines()[0] if issue_text else '')
    match = re.match(r'\[([^\]]+)\]\s*(.*)', first_line)
    if match:
        tag = match.group(1).strip()
        title = match.group(2).strip()
    else:
        tag = ''
        title = first_line

    title = re.sub(r'\s*\(↑\d+\)\s*$', '', title).strip()
    return tag, title


def _extract_issue_field(issue_text, field_names):
    for line in (issue_text or '').splitlines():
        clean = line.strip()
        for field_name in field_names:
            pattern = rf'^{re.escape(field_name)}\s*[:：]\s*(.+)$'
            match = re.search(pattern, clean)
            if match:
                return match.group(1).strip()
    return ''


def _extract_issue_score(issue_text):
    match = re.search(r'↑\s*(\d+)', issue_text or '')
    return f"↑{match.group(1)}" if match else ''


def _compact_accel_need(value):
    value = re.sub(r'^加速需求\s*[:：]\s*', '', str(value or '')).strip()
    return _truncate_text(value, 46) if value else ''


def _compact_hype(value):
    value = str(value or '').strip()
    match = re.search(r'(热度[^（(]*[（(]\d+分[）)]|热度[^（(]+)', value)
    return _truncate_text(match.group(1), 24) if match else _truncate_text(value, 24)


def _compact_calendar_issue(issue):
    alert_type = issue.get('alert_type', 'game_calendar')
    issue_text = issue.get('issue', '')
    tag, title = _split_issue_tag_and_title(issue_text)
    source_name = issue.get('source_name', '')
    compact = dict(issue)

    if alert_type == 'game_update':
        kind = '预告/即将更新' if '预告' in tag or '即将' in tag else '版本更新'
        accel = _compact_accel_need(_extract_issue_field(issue_text, ['加速需求']))
        score = _extract_issue_score(issue_text)
        title = _truncate_text(title or issue.get('game', ''), 110)
        details = []
        if accel:
            details.append(f"加速需求: {accel}")
        if score:
            details.append(f"热度: {score}")
        summary = _truncate_text(_extract_issue_field(issue_text, ['摘要']), 40)
        if summary:
            details.append(f"摘要: {summary}")

        compact['issue'] = f"🎮 {kind}: {title}"
        if details:
            compact['issue'] += f"\n    {' | '.join(details)}"
        return compact

    if alert_type == 'new_game_release':
        source_label = tag or source_name or '新游/上新'
        release_date = _extract_issue_field(issue_text, ['上线时间'])
        if not release_date:
            match = re.search(r'预计发售\s*[:：]\s*([^|，,]+)', title)
            if match:
                release_date = match.group(1).strip()
                title = re.sub(r'\s*预计发售\s*[:：]\s*[^|，,]+', '', title).strip()

        hype = _compact_hype(_extract_issue_field(issue_text, ['热度预估']))
        if not hype:
            hype = _extract_issue_score(issue_text)
        accel = _compact_accel_need(_extract_issue_field(issue_text, ['加速需求']))

        if issue.get('game') in ('Epic Games Store', 'Xbox Game Pass') or issue.get('game', '').startswith(('PlayStation', 'Xbox')):
            headline = _truncate_text(title or issue.get('game', ''), 110)
        else:
            headline = _truncate_text(issue.get('game') or title, 80)

        details = []
        if release_date:
            details.append(f"上线: {release_date}")
        if hype:
            details.append(f"热度: {hype}")
        if accel:
            details.append(f"加速需求: {accel}")
        summary = _truncate_text(_extract_issue_field(issue_text, ['摘要']), 40)
        if summary:
            details.append(f"摘要: {summary}")

        compact['issue'] = f"🆕 {source_label}: {headline}"
        if details:
            compact['issue'] += f"\n    {' | '.join(details)}"
        return compact

    compact['issue'] = _truncate_text(issue_text, 140)
    return compact


def build_calendar_issue_key(issue):
    """Build a stable cross-run dedup key for calendar alerts."""
    alert_type = issue.get('alert_type', '')
    source_name = issue.get('source_name', '')
    source_url = (issue.get('source_url') or '').strip()
    issue_text = (issue.get('issue') or '').strip()
    first_line = issue_text.splitlines()[0].strip() if issue_text else ''
    first_line = re.sub(r'\s+', ' ', first_line)

    if source_url.startswith('https://store.steampowered.com/app/'):
        # 同一游戏可能被多个 Steam 数据源抓到，按 app URL 统一去重（不含 source_name）
        return f"{alert_type}|steam_app|{source_url}"

    if (
        'reddit.com' in source_url
        or 'hoyolab.com/article/' in source_url
        or '/news/app/' in source_url
    ):
        return f"{alert_type}|{source_url}"

    return f"{alert_type}|{source_name}|{source_url}|{first_line}"


def filter_new_calendar_issues(all_issues):
    """Filter out issues that were already alerted in previous runs."""
    snapshot = load_snapshot()
    seen_keys = snapshot.get('seen_calendar_issue_keys', [])
    seen_set = set(seen_keys)
    new_seen_keys = list(seen_keys)
    filtered = []

    for issue in all_issues:
        dedup_key = build_calendar_issue_key(issue)
        if dedup_key in seen_set:
            continue
        seen_set.add(dedup_key)
        new_seen_keys.append(dedup_key)
        filtered.append(issue)

    snapshot['seen_calendar_issue_keys'] = new_seen_keys[-CALENDAR_SEEN_KEY_LIMIT:]
    save_snapshot(snapshot)
    return filtered


def queue_calendar_issues_for_daily_digest(issues):
    if not issues:
        return 0, len(load_snapshot().get(CALENDAR_PENDING_ISSUES_KEY, []))

    snapshot = load_snapshot()
    pending = snapshot.get(CALENDAR_PENDING_ISSUES_KEY, [])
    if not isinstance(pending, list):
        pending = []

    pending_keys = set()
    for item in pending:
        if not isinstance(item, dict):
            continue
        key = item.get('_calendar_issue_key') or build_calendar_issue_key(item)
        if key:
            pending_keys.add(key)

    added = 0
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for issue in issues:
        # 低热度新游不入队，保持每日摘要简洁
        if issue.get('alert_type') == 'new_game_release' and issue.get('hype_score', 0) < 25:
            continue
        issue_key = build_calendar_issue_key(issue)
        if issue_key in pending_keys:
            continue
        stored = dict(issue)
        stored['_calendar_issue_key'] = issue_key
        stored['_queued_at'] = now_iso
        pending.append(stored)
        pending_keys.add(issue_key)
        added += 1

    snapshot[CALENDAR_PENDING_ISSUES_KEY] = pending[-CALENDAR_PENDING_ISSUE_LIMIT:]
    snapshot['last_calendar_pending_update_at'] = now_iso
    save_snapshot(snapshot)
    return added, len(snapshot[CALENDAR_PENDING_ISSUES_KEY])


def get_pending_calendar_issue_count():
    pending = load_snapshot().get(CALENDAR_PENDING_ISSUES_KEY, [])
    return len(pending) if isinstance(pending, list) else 0


def pop_calendar_digest_if_due():
    snapshot = load_snapshot()
    today_bj = _today_bj()
    if snapshot.get(CALENDAR_DIGEST_STATE_KEY) == today_bj:
        return []

    pending = snapshot.get(CALENDAR_PENDING_ISSUES_KEY, [])
    if not isinstance(pending, list) or not pending:
        return []

    updates = [i for i in pending if i.get('alert_type') == 'game_update']
    new_releases = [i for i in pending if i.get('alert_type') == 'new_game_release']
    others = [i for i in pending if i.get('alert_type') not in ('new_game_release', 'game_update')]
    updates.sort(key=lambda x: x.get('update_priority', 0), reverse=True)
    new_releases.sort(key=lambda x: x.get('hype_score', 0), reverse=True)
    ordered = updates + new_releases + others

    digest_issues = [_compact_calendar_issue(issue) for issue in ordered]

    snapshot[CALENDAR_PENDING_ISSUES_KEY] = []
    snapshot[CALENDAR_DIGEST_STATE_KEY] = today_bj
    snapshot['last_calendar_digest_sent_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    snapshot['last_calendar_digest_item_count'] = len(digest_issues)
    save_snapshot(snapshot)

    print(
        f"[Calendar DIGEST] prepared {len(digest_issues)} item(s) for {today_bj}; "
        f"updates={len(updates)}, new_releases={len(new_releases)}, others={len(others)}"
    )
    return digest_issues


def should_send_calendar_heartbeat():
    snapshot = load_snapshot()
    today_bj = _today_bj()
    last_sent = snapshot.get(CALENDAR_HEARTBEAT_STATE_KEY)
    if last_sent == today_bj:
        return False
    snapshot[CALENDAR_HEARTBEAT_STATE_KEY] = today_bj
    save_snapshot(snapshot)
    return True


def fetch_reddit_posts(subreddit, sort='new', limit=25):
    """Fetch subreddit listing posts through OAuth and return post wrappers."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&raw_json=1"
    response = reddit_get(url)
    if response is None:
        request_meta = get_last_reddit_request_meta()
        if request_meta.get('token_state') == 'missing_credentials':
            report_scrape_block('reddit_game_calendar_missing_credentials', url)
        return []
    if response.status_code != 200:
        request_meta = get_last_reddit_request_meta()
        token_state = request_meta.get('token_state')
        mode = request_meta.get('mode')
        source_key = 'reddit_game_calendar'

        if token_state == 'missing_credentials':
            # Reddit API 凭证未配置，已知限制，不发报警（避免噪音）
            print(f"[Calendar] Reddit 匿名 403 (无凭证): {url[:80]}")
            return []
        elif token_state in ('oauth_token_failed', 'oauth_token_exception'):
            source_key = 'reddit_game_calendar_token_failure'
        elif response.status_code == 403 and mode == 'oauth':
            source_key = 'reddit_game_calendar_oauth_403'
        elif response.status_code == 403 and mode == 'anonymous':
            source_key = 'reddit_game_calendar_anonymous_403'

        report_scrape_block(source_key, url, response.status_code)
        return []
    return response.json().get('data', {}).get('children', [])


def is_recent_reddit_post(post_data, hours=None, days=None):
    created_utc = post_data.get('created_utc')
    if not created_utc:
        return True

    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    elif days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        return True

    try:
        created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    except Exception:
        return True
    return created_at >= cutoff


def check_steam_news_updates():
    """
    检查已追踪游戏的 Steam News，检测大版本更新和新赛季。
    """
    issues = []
    old_snapshot = load_snapshot()
    seen_news = old_snapshot.get('seen_news_ids', [])
    new_seen = list(seen_news)
    steam_news_403_fail_counts = old_snapshot.get('steam_news_403_fail_counts', {})
    steam_news_403_suppressed_until = old_snapshot.get('steam_news_403_suppressed_until', {})

    # 接入 API Key 后清除旧的 403 退避状态，让所有 AppID 立即重试
    if STEAM_API_KEY and (steam_news_403_fail_counts or steam_news_403_suppressed_until):
        print("[Calendar] 检测到 STEAM_API_KEY，清除旧的 Steam News 403 退避状态。")
        steam_news_403_fail_counts.clear()
        steam_news_403_suppressed_until.clear()

    for game_name, app_id in TRACKED_GAMES.items():
        app_key = str(app_id)
        now_utc = datetime.now(timezone.utc)
        suppressed_until_raw = steam_news_403_suppressed_until.get(app_key)
        if suppressed_until_raw:
            try:
                suppressed_until = datetime.fromisoformat(suppressed_until_raw)
                if suppressed_until.tzinfo is None:
                    suppressed_until = suppressed_until.replace(tzinfo=timezone.utc)
                if suppressed_until > now_utc:
                    print(
                        f"[Calendar] {game_name} Steam News 403 backoff active "
                        f"until {suppressed_until.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    continue
            except Exception:
                pass
            steam_news_403_suppressed_until.pop(app_key, None)
            steam_news_403_fail_counts.pop(app_key, None)

        url = (
            f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
            f"?appid={app_id}&count=5&maxlength=2000&format=json"
        )
        if STEAM_API_KEY:
            url += f"&key={STEAM_API_KEY}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200:
                if response.status_code == 403:
                    fail_count = int(steam_news_403_fail_counts.get(app_key, 0)) + 1
                    steam_news_403_fail_counts[app_key] = fail_count
                    if fail_count >= STEAM_NEWS_403_FAIL_THRESHOLD:
                        backoff_until = now_utc + timedelta(days=STEAM_NEWS_403_BACKOFF_DAYS)
                        steam_news_403_suppressed_until[app_key] = backoff_until.isoformat()
                        print(
                            f"[Calendar] {game_name} Steam News returned 403 for {fail_count} consecutive runs; "
                            f"suppressing this AppID for {STEAM_NEWS_403_BACKOFF_DAYS} days."
                        )
                    elif not STEAM_API_KEY:
                        # 无 API Key 时才报数据源异常（系统性问题）
                        # 有 Key 时个别游戏 403 是 Valve 端限制，仅记日志
                        report_scrape_block('steam_news_api', url, response.status_code)
                    else:
                        print(f"[Calendar] {game_name} Steam News 403 ({fail_count}/{STEAM_NEWS_403_FAIL_THRESHOLD})")
                else:
                    report_scrape_block('steam_news_api', url, response.status_code)
                continue

            steam_news_403_fail_counts.pop(app_key, None)
            steam_news_403_suppressed_until.pop(app_key, None)

            data = response.json()
            news_items = data.get('appnews', {}).get('newsitems', [])

            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

            for item in news_items:
                gid = item.get('gid', '')
                title = item.get('title', '')
                contents = item.get('contents', '')
                date = datetime.fromtimestamp(item.get('date', 0), timezone.utc)
                feed = item.get('feedlabel', '')

                # 跳过已见过的新闻
                if gid in seen_news:
                    continue

                # 只看 48 小时内的
                if date < cutoff:
                    continue

                new_seen.append(gid)

                # 检测是否为大版本更新或预告
                title_upper = title.upper()
                is_major = any(kw in title_upper for kw in UPDATE_KEYWORDS)

                # 区分预告 vs 已上线
                PREVIEW_HINTS = ["COMING SOON", "UPCOMING", "PREVIEW", "TEASER",
                                "ROADMAP", "ANNOUNCEMENT", "REVEAL", "COUNTDOWN",
                                "DEV UPDATE", "DEV BLOG", "PLANNED", "SCHEDULED",
                                "NEXT SEASON", "NEXT UPDATE", "WHAT'S NEXT",
                                "MAINTENANCE NOTICE"]
                is_preview = any(kw in title_upper for kw in PREVIEW_HINTS)

                # 优先看官方公告（Community Announcements）
                is_official = feed in ('Community Announcements', 'steam_community_announcements')

                if is_major and is_official:
                    if is_preview:
                        tag = "📢 [预告/即将更新]"
                    else:
                        tag = "🎮 [大版本更新]"

                    # 调用 AI 生成内容摘要
                    summary = summarize_update(game_name, title, contents)
                    # 调用 AI 分析加速需求
                    accel_need = analyze_acceleration_need(game_name, update_content=contents)
                    # 综合优先级
                    update_priority = estimate_update_priority(reddit_score=0, accel_need_text=accel_need)

                    issues.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': f"{tag} {title}\n    加速需求: {accel_need}\n    {summary}",
                        'alert_type': 'game_update',
                        'update_priority': update_priority,
                        'source_name': 'Steam News',
                        'source_url': item.get('url', f'https://store.steampowered.com/news/app/{app_id}')
                    })

        except Exception as e:
            print(f"[Calendar] {game_name} Steam News 检测失败: {e}")

    # 保持 seen_news 不会无限增长（只保留最近 500 条）
    old_snapshot['seen_news_ids'] = new_seen[-500:]
    old_snapshot['steam_news_403_fail_counts'] = steam_news_403_fail_counts
    old_snapshot['steam_news_403_suppressed_until'] = steam_news_403_suppressed_until
    save_snapshot(old_snapshot)

    return issues


def check_official_page_updates(game_name, page_url):
    """
    抓取 Riot 官方 game-updates 页面，检测 48 小时内的 patch notes。
    识别页面内的 ISO 8601 时间戳（如 2026-04-01T...）。
    返回 issue dict 或 None。
    """
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('official_patch_page', page_url, response.status_code)
            print(f"[Calendar] {game_name} 官方页面返回 {response.status_code}")
            return None

        soup_text = html.unescape(response.text)

        # 查找 patch notes 标题：匹配 "Patch X.X Notes" 等变体
        PATCH_TITLE_RE = re.compile(
            r'(?i)(patch\s*\d+[\.\-]\d+\s*notes?|patch\s*notes?\s*\d+[\.\-]\d+)',
        )
        matches = PATCH_TITLE_RE.findall(soup_text)
        if not matches:
            return None
        patch_title = matches[0].strip()

        # 检查页面是否有 48 小时内的 ISO 8601 时间戳
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})')
        is_recent = False
        for date_str, time_str in DATE_RE.findall(soup_text):
            try:
                dt = datetime.fromisoformat(f"{date_str}T{time_str}:00+00:00")
                if dt >= cutoff:
                    is_recent = True
                    break
            except Exception:
                continue

        if not is_recent:
            return None

        accel_need = analyze_acceleration_need(game_name, update_content=patch_title)
        update_priority = estimate_update_priority(reddit_score=500, accel_need_text=accel_need)

        return {
            'game': game_name,
            'region': 'Global',
            'country': '',
            'issue': f"🎮 [版本更新] {patch_title}\n    加速需求: {accel_need}",
            'alert_type': 'game_update',
            'update_priority': update_priority,
            'source_name': '官方 Patch Notes',
            'source_url': page_url,
        }

    except Exception as e:
        print(f"[Calendar] {game_name} 官方页面检测失败: {e}")
        return None


def check_blizzard_updates(game_name, page_url):
    """
    抓取 Blizzard 官方新闻/Patch Notes 页面，检测 48 小时内的更新。
    Blizzard 页面使用 "Month DD, YYYY" 格式日期（如 "March 31, 2026"）。
    返回 issue dict 或 None。
    """
    MONTH_MAP = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
    }
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('official_patch_page', page_url, response.status_code)
            print(f"[Calendar] {game_name} Blizzard 页面返回 {response.status_code}")
            return None

        soup_text = html.unescape(response.text)

        # 从页面标题/h2/h3 中找到最新的 patch/update 标题
        TITLE_RE = re.compile(
            r'(?i)(?:patch|update|hotfix|season|maintenance)[^<"]{0,80}',
        )
        title_matches = TITLE_RE.findall(soup_text)
        patch_title = title_matches[0].strip() if title_matches else f"{game_name} 更新"

        # 检测 48h 内的 "Month DD, YYYY" 日期
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        DATE_RE = re.compile(
            r'(january|february|march|april|may|june|july|august|'
            r'september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})',
            re.IGNORECASE,
        )
        is_recent = False
        for month_str, day_str, year_str in DATE_RE.findall(soup_text):
            try:
                month_num = MONTH_MAP[month_str.lower()]
                dt = datetime(int(year_str), month_num, int(day_str), tzinfo=timezone.utc)
                if dt >= cutoff:
                    is_recent = True
                    break
            except Exception:
                continue

        if not is_recent:
            return None

        accel_need = analyze_acceleration_need(game_name, update_content=patch_title)
        update_priority = estimate_update_priority(reddit_score=500, accel_need_text=accel_need)

        return {
            'game': game_name,
            'region': 'Global',
            'country': '',
            'issue': f"🎮 [版本更新] {patch_title}\n    加速需求: {accel_need}",
            'alert_type': 'game_update',
            'update_priority': update_priority,
            'source_name': '官方 Patch Notes',
            'source_url': page_url,
        }

    except Exception as e:
        print(f"[Calendar] {game_name} Blizzard 页面检测失败: {e}")
        return None


def check_hoyolab_updates(game_name, gid):
    """
    调用 HoyoLab 官方 API 检测原神/崩铁/绝区零的版本更新。
    筛选条件：官方账号发布 + 标题含版本/更新关键词 + 48h 内发布。
    gid: 2=原神, 6=崩坏:星穹铁道, 8=绝区零
    返回 issue dict 或 None。
    """
    UPDATE_KEYWORDS_ZH = [
        'version', 'update', 'maintenance', 'patch',
        '版本', '更新', '维护', '公告', 'preview', '预告',
    ]
    api_url = (
        f"https://bbs-api-os.hoyoverse.com/community/post/wapi/getNewsList"
        f"?gids={gid}&type=3&page_size=10"
    )
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('hoyolab_api', api_url, response.status_code)
            print(f"[Calendar] {game_name} HoyoLab API 返回 {response.status_code}")
            return None

        data = response.json()
        posts = data.get('data', {}).get('list', [])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        for item in posts:
            post = item.get('post', {})
            user = item.get('user', {})
            subject = post.get('subject', '')
            created_at = post.get('created_at', 0)  # Unix timestamp
            nickname = user.get('nickname', '')

            # 仅接受官方账号发布的内容
            if 'official' not in nickname.lower():
                continue

            # 标题需含更新相关关键词
            subject_lower = subject.lower()
            if not any(kw in subject_lower for kw in UPDATE_KEYWORDS_ZH):
                continue

            # 48h 内发布
            try:
                dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
            except Exception:
                continue
            if dt < cutoff:
                continue

            # 命中
            post_id = post.get('post_id', '')
            post_url = f"https://www.hoyolab.com/article/{post_id}" if post_id else api_url
            accel_need = analyze_acceleration_need(game_name, update_content=subject)
            update_priority = estimate_update_priority(reddit_score=500, accel_need_text=accel_need)

            return {
                'game': game_name,
                'region': 'Global',
                'country': '',
                'issue': f"🎮 [版本更新] {subject}\n    加速需求: {accel_need}",
                'alert_type': 'game_update',
                'update_priority': update_priority,
                'source_name': 'HoyoLab 官方公告',
                'source_url': post_url,
            }

        return None  # 48h 内无官方更新公告

    except Exception as e:
        print(f"[Calendar] {game_name} HoyoLab API 检测失败: {e}")
        return None


def check_non_steam_updates():
    """
    通过 Reddit 检测非 Steam 游戏的大版本更新/新赛季/预告。
    时间窗口扩大到一周，以便提前捕获更新预告。
    """
    issues = []

    PREVIEW_HINTS = ["UPCOMING", "PREVIEW", "TEASER", "ROADMAP", "REVEAL",
                     "COUNTDOWN", "DEV UPDATE", "PBE", "PTR", "COMING SOON",
                     "NEXT SEASON", "ANNOUNCED"]

    for game_name, config in NON_STEAM_GAMES.items():
        keywords = config['keywords']

        # --- 优先级 1：Riot 系官网（ISO 时间戳）---
        official_url = config.get('official_url')
        if official_url:
            result = check_official_page_updates(game_name, official_url)
            if result:
                issues.append(result)
                continue  # 官方源命中，跳过 Reddit

        # --- 优先级 2：Blizzard 官网（Month DD, YYYY 日期）---
        blizzard_url = config.get('blizzard_url')
        if blizzard_url:
            result = check_blizzard_updates(game_name, blizzard_url)
            if result:
                issues.append(result)
                continue  # 官方源命中，跳过 Reddit

        # --- 优先级 3：HoyoLab API（原神/崩铁/绝区零）---
        hoyolab_gid = config.get('hoyolab_gid')
        if hoyolab_gid:
            result = check_hoyolab_updates(game_name, hoyolab_gid)
            if result:
                issues.append(result)
                continue  # 官方源命中，跳过 Reddit

        # --- 优先级 4：Reddit 兜底（Fortnite/CoD/鸣潮/Roblox/Aion 2）---
        subreddit = config.get('subreddit', '')
        if not subreddit:
            continue

        try:
            posts = fetch_reddit_posts(subreddit, sort='new', limit=25)
            if not posts:
                continue

            candidates = []
            for post in posts:
                post_data = post.get('data', {})
                title = post_data.get('title', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('ups', 0)
                flair = (post_data.get('link_flair_text', '') or '').upper()
                if not is_recent_reddit_post(post_data, days=7):
                    continue

                haystack_upper = f"{title}\n{selftext}".upper()
                title_upper = title.upper()
                is_update = any(kw.upper() in haystack_upper for kw in keywords)
                is_official = any(kw in flair for kw in (
                    'OFFICIAL', 'NEWS', 'PATCH', 'ANNOUNCEMENT',
                    'MEGATHREAD', 'SUB-META', 'GAME UPDATE', 'UPDATE',
                ))
                is_hot = score > 100

                # 区分预告 vs 已上线
                is_preview = any(kw in title_upper for kw in PREVIEW_HINTS)

                if is_update and (is_official or is_hot):
                    if is_preview:
                        tag = f"📢 [预告/即将更新]"
                    else:
                        tag = f"🎮 [版本更新]"

                    # 调用 AI 分析加速需求
                    accel_need = analyze_acceleration_need(game_name, update_content=selftext or title)

                    # 调用 AI 生成内容摘要（如果帖子有正文内容）
                    if selftext and len(selftext) > 50:
                        summary = summarize_update(game_name, title, selftext)
                        issue_text = f"{tag} {title} (↑{score})\n    加速需求: {accel_need}\n    {summary}"
                    else:
                        issue_text = f"{tag} {title} (↑{score})\n    加速需求: {accel_need}"

                    # 综合优先级
                    update_priority = estimate_update_priority(reddit_score=score, accel_need_text=accel_need)

                    candidates.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': issue_text,
                        'alert_type': 'game_update',
                        'update_priority': update_priority,
                        'match_score': score,
                        'source_name': f'r/{subreddit}',
                        'source_url': f"https://www.reddit.com{post_data.get('permalink', '')}"
                    })
            candidates.sort(
                key=lambda item: (item.get('update_priority', 0), item.get('match_score', 0)),
                reverse=True,
            )
            issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

        except Exception:
            pass

    return issues


def check_hot_new_releases():
    """
    检查 Steam 热门新发售和畅销榜，找出有联机需求的新游。
    """
    issues = []
    url = "https://store.steampowered.com/api/featuredcategories?cc=us"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('steam_featured', url, response.status_code)
            return issues

        data = response.json()

        # 检查 Top Sellers 和 New Releases
        for category_key in ['top_sellers', 'new_releases']:
            category = data.get(category_key, {})
            items = category.get('items', [])
            category_label = 'Top Sellers' if category_key == 'top_sellers' else 'New Releases'

            for rank, item in enumerate(items[:15], 1):  # 只看前 15，rank 从 1 开始
                name = item.get('name', '')
                app_id = item.get('id', 0)

                # 检查是否为联机游戏（通过 appdetails API）
                detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                try:
                    detail_resp = requests.get(detail_url, headers=HEADERS, timeout=10)
                    if detail_resp.status_code == 200:
                        detail_data = detail_resp.json()
                        app_data = detail_data.get(str(app_id), {}).get('data', {})

                        # 只关心游戏本体，过滤 DLC / Demo / 硬件等
                        if app_data.get('type', 'game') != 'game':
                            continue

                        # 检查类别是否包含联机标签
                        categories = app_data.get('categories', [])
                        category_names = [c.get('description', '') for c in categories]
                        genres = app_data.get('genres', [])
                        genre_names = [g.get('description', '') for g in genres]

                        all_tags = category_names + genre_names
                        is_online = any(
                            tag in all_tags
                            for tag in ['Multi-player', 'Online PvP', 'Online Co-op',
                                       'MMO', 'Massively Multiplayer', 'Co-op']
                        )

                        if is_online:
                            # 提取游戏类型
                            genre_str = ', '.join(genre_names[:3]) if genre_names else '未知类型'

                            release_date = app_data.get('release_date', {})
                            if not release_date.get('coming_soon', True):
                                date_str = release_date.get('date', '未知')
                                # 推算头部地区
                                top_regions = infer_top_regions(app_data)
                                # AI 新游玩法介绍
                                description = app_data.get('short_description', '') or app_data.get('about_the_game', '')
                                game_intro = summarize_new_game(name, description) if description else ''
                                # AI 加速需求分析
                                accel_need = analyze_acceleration_need(name, app_data)

                                # 热度预估
                                hype_score = estimate_game_hype(app_data, rank, category_label)
                                hype_label = format_hype_label(hype_score)

                                issue_text = f"🆕 [Steam {category_label} #{rank}] {name} ({genre_str})"
                                issue_text += f"\n    上线时间: {date_str}"
                                issue_text += f"\n    热度预估: {hype_label}"
                                issue_text += f"\n    加速需求: {accel_need}"
                                issue_text += f"\n    头部地区: {top_regions}"
                                if game_intro:
                                    issue_text += f"\n    玩法介绍: {game_intro}"

                                issues.append({
                                    'game': name,
                                    'region': 'Global',
                                    'country': '',
                                    'issue': issue_text,
                                    'alert_type': 'new_game_release',
                                    'hype_score': hype_score,  # 用于排序
                                    'source_name': 'Steam Store',
                                    'source_url': f'https://store.steampowered.com/app/{app_id}'
                                })

                    else:
                        report_scrape_block('steam_appdetails', detail_url, detail_resp.status_code)
                except Exception:
                    pass

        # 去重
        seen = set()
        unique_issues = []
        for issue in issues:
            key = issue['game']
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        # 按热度从高到低排序
        unique_issues.sort(key=lambda x: x.get('hype_score', 0), reverse=True)
        return unique_issues[:5]  # 最多报 5 条，避免刷屏

    except Exception as e:
        print(f"[Calendar] Steam Featured 检测失败: {e}")
        return []


def check_epic_new_releases():
    """
    通过 Reddit 检测 Epic Games Store 的新游上线和免费游戏赠送。
    Epic 免费送联机大作时 = 大量玩家涌入 = 加速需求暴增。
    """
    issues = []

    reddit_sources = [
        {
            'subreddit': 'EpicGamesPC',
            'label': 'Epic 新游/独占',
            'sort': 'new',
            'match_terms': ['EPIC', 'EXCLUSIVE', 'LAUNCH', 'RELEASE', 'FREE'],
        },
        {
            'subreddit': 'FreeGameFindings',
            'label': 'Epic 免费游戏',
            'sort': 'new',
            'match_terms': ['EPIC', 'FREE'],
        },
        {
            'subreddit': 'GameDeals',
            'label': 'Epic 促销/上线',
            'sort': 'hot',
            'match_terms': ['EPIC', 'FREE', 'LAUNCH', 'RELEASE'],
        }
    ]

    for source in reddit_sources:
        try:
            posts = fetch_reddit_posts(
                source['subreddit'],
                sort=source.get('sort', 'new'),
                limit=25,
            )
            if not posts:
                continue

            candidates = []
            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                if not is_recent_reddit_post(pd, days=2):
                    continue

                # 只报热帖（score > 50）
                if score > 50:
                    # 检查是否联机相关
                    title_upper = title.upper()
                    if not any(term in title_upper for term in source.get('match_terms', [])):
                        continue
                    online_hints = ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO',
                                   'BATTLE ROYALE', 'FPS', 'SHOOTER', 'FREE']
                    if any(kw in title_upper for kw in online_hints) or 'FREE' in title_upper:
                        candidates.append({
                            'game': 'Epic Games Store',
                            'region': 'Global',
                            'country': '',
                            'issue': f"🆕 [{source['label']}] {title} (↑{score})" + _summary_suffix(title),
                            'alert_type': 'new_game_release',
                            'hype_score': score,
                            'source_name': f"r/{source['subreddit']}",
                            'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                        })
            candidates.sort(key=lambda item: item.get('hype_score', 0), reverse=True)
            issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

        except Exception:
            pass

    return issues


def check_playstation_releases():
    """
    通过 Reddit 检测 PlayStation 新游上线和重大更新。
    """
    issues = []

    subreddits = [
        {'sub': 'PS5', 'query': 'new+release+OR+launch+OR+update+OR+season', 'label': 'PS5'},
        {'sub': 'PS4', 'query': 'new+release+OR+launch+OR+update', 'label': 'PS4'},
    ]

    for config in subreddits:
        try:
            posts = fetch_reddit_posts(config['sub'], sort='hot', limit=20)
            if not posts:
                continue

            candidates = []
            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                flair = (pd.get('link_flair_text', '') or '').upper()
                if not is_recent_reddit_post(pd, days=2):
                    continue

                title_upper = title.upper()
                is_game_news = any(kw in title_upper for kw in
                    ['LAUNCH', 'RELEASE', 'AVAILABLE NOW', 'OUT NOW', 'UPDATE', 'SEASON', 'PATCH'])
                is_online = any(kw in title_upper for kw in
                    ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO', 'FPS', 'SERVERS'])
                is_official = 'NEWS' in flair or 'OFFICIAL' in flair or 'GAME' in flair
                is_hot = score > 200

                if is_game_news and (is_online or is_hot) and (is_official or is_hot):
                    candidates.append({
                        'game': f'PlayStation ({config["label"]})',
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [PS 新游/更新] {title} (↑{score})" + _summary_suffix(title),
                        'alert_type': 'new_game_release',
                        'hype_score': score,
                        'source_name': f"r/{config['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
            candidates.sort(key=lambda item: item.get('hype_score', 0), reverse=True)
            issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

        except Exception:
            pass

    return issues


def check_xbox_gamepass_releases():
    """
    通过 Reddit 检测 Xbox / Game Pass 上新和重大更新。
    Game Pass 上新联机游戏 = 大量玩家零成本涌入 = 加速需求暴增。
    """
    issues = []

    subreddits = [
        {'sub': 'XboxGamePass', 'query': 'coming+soon+OR+new+OR+available+today+OR+day+one', 'label': 'Game Pass 上新'},
        {'sub': 'XboxSeriesX', 'query': 'new+release+OR+launch+OR+update+OR+season', 'label': 'Xbox 新游/更新'},
    ]

    for config in subreddits:
        try:
            posts = fetch_reddit_posts(config['sub'], sort='hot', limit=20)
            if not posts:
                continue

            candidates = []
            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                if not is_recent_reddit_post(pd, days=2):
                    continue

                title_upper = title.upper()
                is_gamepass = any(kw in title_upper for kw in
                    ['GAME PASS', 'GAMEPASS', 'DAY ONE', 'COMING SOON', 'AVAILABLE NOW', 'LAUNCH'])
                is_online = any(kw in title_upper for kw in
                    ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO', 'FPS'])
                is_hot = score > 100

                if (is_gamepass or is_hot) and (is_online or is_hot):
                    candidates.append({
                        'game': f'Xbox ({config["label"]})',
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [{config['label']}] {title} (↑{score})" + _summary_suffix(title),
                        'alert_type': 'new_game_release',
                        'hype_score': score,
                        'source_name': f"r/{config['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
            candidates.sort(key=lambda item: item.get('hype_score', 0), reverse=True)
            issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

        except Exception:
            pass

    return issues


def check_battlenet_updates():
    """
    通过 Reddit 检测暴雪/Battle.net 系游戏的大版本更新。
    覆盖 OW2、WoW、Diablo、Hearthstone 等。
    """
    issues = []

    blizzard_games = [
        {'sub': 'Overwatch', 'name': 'Overwatch 2', 'keywords': ['season', 'patch', 'update', 'new hero', 'event']},
        {'sub': 'wow', 'name': 'World of Warcraft', 'keywords': ['patch', 'update', 'expansion', 'season', 'raid']},
        {'sub': 'diablo4', 'name': 'Diablo 4', 'keywords': ['season', 'patch', 'update', 'expansion']},
        {'sub': 'hearthstone', 'name': 'Hearthstone', 'keywords': ['expansion', 'patch', 'update', 'new set']},
    ]

    for game in blizzard_games:
        try:
            posts = fetch_reddit_posts(game['sub'], sort='new', limit=15)
            if not posts:
                continue

            candidates = []
            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                flair = (pd.get('link_flair_text', '') or '').upper()
                selftext = pd.get('selftext', '')
                if not is_recent_reddit_post(pd, days=2):
                    continue

                haystack_upper = f"{title}\n{selftext}".upper()
                title_upper = title.upper()
                is_update = any(kw.upper() in haystack_upper for kw in game['keywords'])
                is_official = any(kw in flair for kw in ['OFFICIAL', 'NEWS', 'BLIZZARD', 'PATCH', 'UPDATE'])
                is_hot = score > 200

                if is_update and (is_official or is_hot):
                    candidates.append({
                        'game': game['name'],
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [Battle.net 更新] {title} (↑{score})" + _summary_suffix(title),
                        'alert_type': 'game_update',
                        'update_priority': score,
                        'source_name': f"r/{game['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
            candidates.sort(key=lambda item: item.get('update_priority', 0), reverse=True)
            issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

        except Exception:
            pass

    return issues


def check_steam_coming_soon():
    """
    检查 Steam 即将发售的热门联机游戏。
    通过 Featured Categories API 的 coming_soon 列表，
    逐个检查是否为联机游戏，提前 1-4 周发出预警。
    """
    issues = []
    url = "https://store.steampowered.com/api/featuredcategories?cc=us"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('steam_featured', url, response.status_code)
            return issues

        data = response.json()
        coming_soon = data.get('coming_soon', {}).get('items', [])

        for rank, item in enumerate(coming_soon[:10], 1):
            name = item.get('name', '')
            app_id = item.get('id', 0)

            try:
                detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                detail_resp = requests.get(detail_url, headers=HEADERS, timeout=10)
                if detail_resp.status_code != 200:
                    report_scrape_block('steam_appdetails', detail_url, detail_resp.status_code)
                    continue

                detail_data = detail_resp.json()
                app_data = detail_data.get(str(app_id), {}).get('data', {})

                # 只关心游戏本体，过滤 DLC / Demo / 硬件等
                if app_data.get('type', 'game') != 'game':
                    continue

                categories = app_data.get('categories', [])
                category_names = [c.get('description', '') for c in categories]

                is_online = any(
                    tag in category_names
                    for tag in ['Multi-player', 'Online PvP', 'Online Co-op',
                               'MMO', 'Massively Multiplayer', 'Co-op']
                )

                if is_online:
                    release_date = app_data.get('release_date', {})
                    date_str = release_date.get('date', 'TBD')

                    # 提取游戏类型
                    genres = app_data.get('genres', [])
                    genre_names = [g.get('description', '') for g in genres]
                    genre_str = ', '.join(genre_names[:3]) if genre_names else '未知类型'

                    # AI 加速需求分析
                    accel_need = analyze_acceleration_need(name, app_data)

                    # 热度预估
                    hype_score = estimate_game_hype(app_data, rank, 'Coming Soon')
                    hype_label = format_hype_label(hype_score)

                    issue_text = f"📢 [即将发售] {name} ({genre_str}) 预计发售: {date_str}"
                    issue_text += f"\n    热度预估: {hype_label}"
                    issue_text += f"\n    加速需求: {accel_need}"

                    issues.append({
                        'game': name,
                        'region': 'Global',
                        'country': '',
                        'issue': issue_text,
                        'alert_type': 'new_game_release',
                        'hype_score': hype_score,
                        'source_name': 'Steam Coming Soon',
                        'source_url': f'https://store.steampowered.com/app/{app_id}'
                    })

            except Exception:
                pass

        # 去重，最多 3 条
        seen = set()
        unique = []
        for issue in issues:
            if issue['game'] not in seen:
                seen.add(issue['game'])
                unique.append(issue)
        return unique[:3]

    except Exception as e:
        print(f"[Calendar] Steam Coming Soon 检测失败: {e}")
        return []


def check_popular_coming_soon():
    """
    检查 Steam 热门即将发售榜（popularcomingsoon，按愿望单热度排序，取前 30）。
    Featured coming_soon 仅前 10 且为编辑精选，会漏掉发售前测试期爆火的新游
    （如 WARDOGS 封闭测试期间愿望单 100 万但未进 featured 榜），本榜单覆盖该盲区。
    """
    issues = []
    url = ("https://store.steampowered.com/search/results/?query&start=0&count=30"
           "&dynamic_data=&sort_by=_ASC&filter=popularcomingsoon&ignore_preferences=1"
           "&snr=1_7_7_230_7&infinite=1&json=1")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            report_scrape_block('steam_popular_coming', url, response.status_code)
            return issues

        data = response.json()
        results_html = data.get('results_html', '') or ''
        # 每行 <a data-ds-appid=... class="search_result_row"> 内部紧跟本行 <span class="title">
        entries = re.findall(
            r'data-ds-appid="(\d+)"[\s\S]{0,2000}?<span class="title">([^<]+)</span>',
            results_html
        )[:30]

        for rank, (app_id_str, raw_name) in enumerate(entries, 1):
            app_id = int(app_id_str)
            name = html.unescape(raw_name).strip()

            try:
                detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                detail_resp = requests.get(detail_url, headers=HEADERS, timeout=10)
                if detail_resp.status_code != 200:
                    report_scrape_block('steam_appdetails', detail_url, detail_resp.status_code)
                    continue

                app_data = detail_resp.json().get(str(app_id), {}).get('data', {})

                # 只关心游戏本体，过滤 DLC / Demo / 硬件等
                if app_data.get('type', 'game') != 'game':
                    continue

                # 榜单理论上只含未发售游戏，已发售的交给 check_hot_new_releases
                release_date = app_data.get('release_date', {})
                if not release_date.get('coming_soon', False):
                    continue

                categories = app_data.get('categories', [])
                category_names = [c.get('description', '') for c in categories]

                is_online = any(
                    tag in category_names
                    for tag in ['Multi-player', 'Online PvP', 'Online Co-op',
                               'MMO', 'Massively Multiplayer', 'Co-op']
                )

                if is_online:
                    date_str = release_date.get('date', 'TBD')

                    genres = app_data.get('genres', [])
                    genre_names = [g.get('description', '') for g in genres]
                    genre_str = ', '.join(genre_names[:3]) if genre_names else '未知类型'

                    accel_need = analyze_acceleration_need(name, app_data)

                    # 热度预估
                    hype_score = estimate_game_hype(app_data, rank, 'Popular Coming Soon')
                    hype_label = format_hype_label(hype_score)

                    issue_text = f"📢 [热门即将发售 #{rank}] {name} ({genre_str}) 预计发售: {date_str}"
                    issue_text += f"\n    热度预估: {hype_label}"
                    issue_text += f"\n    加速需求: {accel_need}"

                    issues.append({
                        'game': name,
                        'region': 'Global',
                        'country': '',
                        'issue': issue_text,
                        'alert_type': 'new_game_release',
                        'hype_score': hype_score,
                        'source_name': 'Steam Popular Coming Soon',
                        'source_url': f'https://store.steampowered.com/app/{app_id}'
                    })

            except Exception:
                pass

        # 去重，最多 3 条
        seen = set()
        unique = []
        for issue in issues:
            if issue['game'] not in seen:
                seen.add(issue['game'])
                unique.append(issue)
        return unique[:3]

    except Exception as e:
        print(f"[Calendar] Steam Popular Coming Soon 检测失败: {e}")
        return []


def check_gamepass_upcoming():
    """
    通过 Reddit 检测 Game Pass 即将上新的游戏（通常提前 1-2 周公布）。
    """
    issues = []
    try:
        posts = fetch_reddit_posts('XboxGamePass', sort='hot', limit=20)
        if not posts:
            return issues

        candidates = []
        for post in posts:
            pd = post.get('data', {})
            title = pd.get('title', '')
            score = pd.get('ups', 0)
            if not is_recent_reddit_post(pd, days=7):
                continue

            title_upper = title.upper()
            is_upcoming = any(kw in title_upper for kw in
                ['COMING SOON', 'COMING TO GAME PASS', 'GAME PASS', 'SECOND HALF',
                 'FIRST HALF', 'LEAVING SOON', 'ANNOUNCED'])
            is_hot = score > 100

            if is_upcoming and is_hot:
                candidates.append({
                    'game': 'Xbox Game Pass',
                    'region': 'Global',
                    'country': '',
                    'issue': f"📢 [Game Pass 即将上新] {title} (↑{score})" + _summary_suffix(title),
                    'alert_type': 'new_game_release',
                    'hype_score': score,
                    'source_name': 'r/XboxGamePass',
                    'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                })
        candidates.sort(key=lambda item: item.get('hype_score', 0), reverse=True)
        issues.extend(candidates[:PER_SOURCE_ALERT_LIMIT])

    except Exception:
        pass

    return issues


def check_game_calendar():
    """主检测函数"""
    all_issues = []

    print("正在检测已追踪游戏的大版本更新/预告 (Steam News)...")
    all_issues.extend(check_steam_news_updates())

    print("正在检测非 Steam 游戏更新/预告 (Reddit)...")
    all_issues.extend(check_non_steam_updates())

    print("正在检测 Steam 热门新游上线...")
    all_issues.extend(check_hot_new_releases())

    print("正在检测 Steam 即将发售的联机热门...")
    all_issues.extend(check_steam_coming_soon())

    print("正在检测 Steam 热门即将发售榜 (popularcomingsoon)...")
    all_issues.extend(check_popular_coming_soon())

    print("正在检测 Epic Games Store 新游/免费游戏...")
    all_issues.extend(check_epic_new_releases())

    print("正在检测 PlayStation 新游/更新...")
    all_issues.extend(check_playstation_releases())

    print("正在检测 Xbox / Game Pass 上新...")
    all_issues.extend(check_xbox_gamepass_releases())

    print("正在检测 Game Pass 即将上新...")
    all_issues.extend(check_gamepass_upcoming())

    print("正在检测 Battle.net 游戏更新...")
    all_issues.extend(check_battlenet_updates())

    # 按 alert_type 分组排序
    new_releases = [i for i in all_issues if i.get('alert_type') == 'new_game_release']
    updates = [i for i in all_issues if i.get('alert_type') == 'game_update']
    others = [i for i in all_issues if i.get('alert_type') not in ('new_game_release', 'game_update')]

    # 新游按热度从高到低
    new_releases.sort(key=lambda x: x.get('hype_score', 0), reverse=True)
    # 热游更新按综合优先级从高到低
    updates.sort(key=lambda x: x.get('update_priority', 0), reverse=True)

    ordered_issues = updates + new_releases + others
    return filter_new_calendar_issues(ordered_issues)


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    try:
        print("Testing Game Calendar Monitor...")
        results = check_game_calendar()
        if results:
            for r in results:
                print(f"[{r['game']}] {r['issue']}")
            added, pending_total = queue_calendar_issues_for_daily_digest(results)
            print(
                f"[Calendar QUEUE] new={len(results)}, added={added}, "
                f"pending_total={pending_total}"
            )

        digest_results = pop_calendar_digest_if_due()
        if digest_results:
            for r in digest_results:
                print(f"[Calendar DIGEST ITEM] [{r['game']}] {r['issue']}")
            if POPO_WEBHOOK_URL:
                send_popo_alert(POPO_WEBHOOK_URL, digest_results)
        else:
            pending_total = get_pending_calendar_issue_count()
            if pending_total:
                print(
                    f"Calendar digest already sent today; "
                    f"{pending_total} item(s) queued for next daily digest."
                )
            else:
                print("No new hot-game updates or high-value releases detected.")

            if pending_total == 0 and not has_scrape_block_alerts() and should_send_calendar_heartbeat():
                send_system_heartbeat(
                    POPO_WEBHOOK_URL,
                    "Game Calendar Monitor",
                    "本次已正常执行；未发现新的热游版本更新或高价值新游/预告。",
                )
    except Exception as e:
        print(f"[GameCalendarMonitor] Top-level exception: {e}")
        import traceback
        traceback.print_exc()
        try:
            from utils.notifier import report_monitor_crash, flush_monitor_crash_alerts
            report_monitor_crash("game_calendar_monitor.py 顶层", e)
            flush_monitor_crash_alerts(POPO_WEBHOOK_URL)
        except Exception:
            pass
    finally:
        flush_scrape_block_alerts(POPO_WEBHOOK_URL)

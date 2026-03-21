import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/2.1'
}

# 已监控游戏的 Steam AppID（有 AppID 的游戏才能查 News）
TRACKED_GAMES = {
    'APEX Legends': 1172470,
    'CS2': 730,
    'PUBG': 578080,
    'Rainbow Six Siege': 359550,
    'Dota 2': 570,
    'Where Winds Meet': 1928380,
    'Escape from Tarkov': 1422440,
    'Arena Breakout Infinite': 2073620,
    'Path of Exile 2': 2694490,
}

# 非 Steam 游戏通过 Reddit 检测更新（含预告）
NON_STEAM_GAMES = {
    'Valorant': {'subreddit': 'VALORANT', 'keywords': ['patch', 'update', 'season', 'episode', 'act', 'upcoming', 'preview', 'roadmap']},
    'League of Legends': {'subreddit': 'leagueoflegends', 'keywords': ['patch', 'update', 'season', 'preseason', 'preview', 'upcoming', 'pbe']},
    'Fortnite': {'subreddit': 'FortNiteBR', 'keywords': ['update', 'season', 'chapter', 'patch', 'downtime', 'upcoming', 'teaser', 'countdown']},
    'Overwatch 2': {'subreddit': 'Overwatch', 'keywords': ['patch', 'update', 'season', 'hero', 'preview', 'ptr', 'upcoming']},
    'Call of Duty': {'subreddit': 'CallOfDuty', 'keywords': ['update', 'season', 'patch', 'warzone', 'upcoming', 'roadmap', 'preview']},
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


def check_steam_news_updates():
    """
    检查已追踪游戏的 Steam News，检测大版本更新和新赛季。
    """
    issues = []
    old_snapshot = load_snapshot()
    seen_news = old_snapshot.get('seen_news_ids', [])
    new_seen = list(seen_news)

    for game_name, app_id in TRACKED_GAMES.items():
        url = (
            f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
            f"?appid={app_id}&count=5&maxlength=2000&format=json"
        )

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200:
                continue

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

                    issues.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': f"{tag} {title}\n    {summary}",
                        'alert_type': 'game_calendar',
                        'source_name': 'Steam News',
                        'source_url': item.get('url', f'https://store.steampowered.com/news/app/{app_id}')
                    })

        except Exception as e:
            print(f"[Calendar] {game_name} Steam News 检测失败: {e}")

    # 保持 seen_news 不会无限增长（只保留最近 500 条）
    old_snapshot['seen_news_ids'] = new_seen[-500:]
    save_snapshot(old_snapshot)

    return issues


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
        subreddit = config['subreddit']
        keywords = config['keywords']

        query = '+OR+'.join(keywords)
        url = (
            f"https://www.reddit.com/r/{subreddit}/search.json"
            f"?q=flair%3Aofficial+OR+flair%3Anews+{query}"
            f"&restrict_sr=on&sort=new&t=week&limit=10"
        )

        try:
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code != 200:
                continue

            data = response.json()
            posts = data.get('data', {}).get('children', [])

            for post in posts:
                post_data = post.get('data', {})
                title = post_data.get('title', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('ups', 0)
                flair = (post_data.get('link_flair_text', '') or '').upper()

                title_upper = title.upper()
                is_update = any(kw.upper() in title_upper for kw in keywords)
                is_official = 'OFFICIAL' in flair or 'NEWS' in flair or 'PATCH' in flair
                is_hot = score > 100

                # 区分预告 vs 已上线
                is_preview = any(kw in title_upper for kw in PREVIEW_HINTS)

                if is_update and (is_official or is_hot):
                    if is_preview:
                        tag = f"📢 [预告/即将更新]"
                    else:
                        tag = f"🎮 [版本更新]"

                    # 调用 AI 生成内容摘要（如果帖子有正文内容）
                    if selftext and len(selftext) > 50:
                        summary = summarize_update(game_name, title, selftext)
                        issue_text = f"{tag} {title} (↑{score})\n    {summary}"
                    else:
                        issue_text = f"{tag} {title} (↑{score})"

                    issues.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': issue_text,
                        'alert_type': 'game_calendar',
                        'source_name': f'r/{subreddit}',
                        'source_url': f"https://www.reddit.com{post_data.get('permalink', '')}"
                    })
                    break  # 每个游戏只报一条

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
                                issues.append({
                                    'game': name,
                                    'region': 'Global',
                                    'country': '',
                                    'issue': f"🆕 [Steam {category_label} #{rank}] {name} ({genre_str})",
                                    'alert_type': 'game_calendar',
                                    'source_name': 'Steam Store',
                                    'source_url': f'https://store.steampowered.com/app/{app_id}'
                                })

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
            'query': 'free+game+OR+new+release+OR+exclusive+OR+launch',
            'label': 'Epic 新游/独占',
        },
        {
            'subreddit': 'FreeGameFindings',
            'query': 'epic+free',
            'label': 'Epic 免费游戏',
        },
        {
            'subreddit': 'GameDeals',
            'query': 'epic+free+OR+epic+launch',
            'label': 'Epic 促销/上线',
        }
    ]

    for source in reddit_sources:
        try:
            url = (
                f"https://www.reddit.com/r/{source['subreddit']}/search.json"
                f"?q={source['query']}&restrict_sr=on&sort=new&t=day&limit=10"
            )
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code != 200:
                continue

            posts = response.json().get('data', {}).get('children', [])

            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)

                # 只报热帖（score > 50）
                if score > 50:
                    # 检查是否联机相关
                    title_upper = title.upper()
                    online_hints = ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO',
                                   'BATTLE ROYALE', 'FPS', 'SHOOTER', 'FREE']
                    if any(kw in title_upper for kw in online_hints) or 'FREE' in title_upper:
                        issues.append({
                            'game': 'Epic Games Store',
                            'region': 'Global',
                            'country': '',
                            'issue': f"🆕 [{source['label']}] {title} (↑{score})",
                            'alert_type': 'game_calendar',
                            'source_name': f"r/{source['subreddit']}",
                            'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                        })
                        break  # 每个 source 最多报一条

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
            url = (
                f"https://www.reddit.com/r/{config['sub']}/search.json"
                f"?q={config['query']}&restrict_sr=on&sort=hot&t=day&limit=10"
            )
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code != 200:
                continue

            posts = response.json().get('data', {}).get('children', [])

            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                flair = (pd.get('link_flair_text', '') or '').upper()

                title_upper = title.upper()
                is_game_news = any(kw in title_upper for kw in
                    ['LAUNCH', 'RELEASE', 'AVAILABLE NOW', 'OUT NOW', 'UPDATE', 'SEASON', 'PATCH'])
                is_online = any(kw in title_upper for kw in
                    ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO', 'FPS', 'SERVERS'])
                is_official = 'NEWS' in flair or 'OFFICIAL' in flair or 'GAME' in flair
                is_hot = score > 200

                if is_game_news and (is_online or is_hot) and (is_official or is_hot):
                    issues.append({
                        'game': f'PlayStation ({config["label"]})',
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [PS 新游/更新] {title} (↑{score})",
                        'alert_type': 'game_calendar',
                        'source_name': f"r/{config['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
                    break

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
            url = (
                f"https://www.reddit.com/r/{config['sub']}/search.json"
                f"?q={config['query']}&restrict_sr=on&sort=hot&t=day&limit=10"
            )
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code != 200:
                continue

            posts = response.json().get('data', {}).get('children', [])

            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)

                title_upper = title.upper()
                is_gamepass = any(kw in title_upper for kw in
                    ['GAME PASS', 'GAMEPASS', 'DAY ONE', 'COMING SOON', 'AVAILABLE NOW', 'LAUNCH'])
                is_online = any(kw in title_upper for kw in
                    ['MULTIPLAYER', 'ONLINE', 'CO-OP', 'PVP', 'MMO', 'FPS'])
                is_hot = score > 100

                if (is_gamepass or is_hot) and (is_online or is_hot):
                    issues.append({
                        'game': f'Xbox ({config["label"]})',
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [{config['label']}] {title} (↑{score})",
                        'alert_type': 'game_calendar',
                        'source_name': f"r/{config['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
                    break

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
        query = '+OR+'.join(game['keywords'])
        try:
            url = (
                f"https://www.reddit.com/r/{game['sub']}/search.json"
                f"?q=flair%3Aofficial+OR+flair%3Anews+OR+flair%3Ablizzard+{query}"
                f"&restrict_sr=on&sort=new&t=day&limit=5"
            )
            response = requests.get(
                url,
                headers={'User-Agent': 'OSINT-Monitor/2.1'},
                timeout=10
            )
            if response.status_code != 200:
                continue

            posts = response.json().get('data', {}).get('children', [])

            for post in posts:
                pd = post.get('data', {})
                title = pd.get('title', '')
                score = pd.get('ups', 0)
                flair = (pd.get('link_flair_text', '') or '').upper()

                title_upper = title.upper()
                is_update = any(kw.upper() in title_upper for kw in game['keywords'])
                is_official = any(kw in flair for kw in ['OFFICIAL', 'NEWS', 'BLIZZARD', 'PATCH', 'UPDATE'])
                is_hot = score > 200

                if is_update and (is_official or is_hot):
                    issues.append({
                        'game': game['name'],
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [Battle.net 更新] {title} (↑{score})",
                        'alert_type': 'game_calendar',
                        'source_name': f"r/{game['sub']}",
                        'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                    })
                    break

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
            return issues

        data = response.json()
        coming_soon = data.get('coming_soon', {}).get('items', [])

        for item in coming_soon[:10]:
            name = item.get('name', '')
            app_id = item.get('id', 0)

            try:
                detail_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                detail_resp = requests.get(detail_url, headers=HEADERS, timeout=10)
                if detail_resp.status_code != 200:
                    continue

                detail_data = detail_resp.json()
                app_data = detail_data.get(str(app_id), {}).get('data', {})

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

                    issues.append({
                        'game': name,
                        'region': 'Global',
                        'country': '',
                        'issue': f"📢 [即将发售] {name} ({genre_str}) 预计发售: {date_str}",
                        'alert_type': 'game_calendar',
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


def check_gamepass_upcoming():
    """
    通过 Reddit 检测 Game Pass 即将上新的游戏（通常提前 1-2 周公布）。
    """
    issues = []
    try:
        url = (
            "https://www.reddit.com/r/XboxGamePass/search.json"
            "?q=coming+soon+OR+coming+to+game+pass+OR+leaving+game+pass+OR+second+half"
            "&restrict_sr=on&sort=hot&t=week&limit=10"
        )
        response = requests.get(
            url,
            headers={'User-Agent': 'OSINT-Monitor/2.1'},
            timeout=10
        )
        if response.status_code != 200:
            return issues

        posts = response.json().get('data', {}).get('children', [])

        for post in posts:
            pd = post.get('data', {})
            title = pd.get('title', '')
            score = pd.get('ups', 0)

            title_upper = title.upper()
            is_upcoming = any(kw in title_upper for kw in
                ['COMING SOON', 'COMING TO GAME PASS', 'GAME PASS', 'SECOND HALF',
                 'FIRST HALF', 'LEAVING SOON', 'ANNOUNCED'])
            is_hot = score > 100

            if is_upcoming and is_hot:
                issues.append({
                    'game': 'Xbox Game Pass',
                    'region': 'Global',
                    'country': '',
                    'issue': f"📢 [Game Pass 即将上新] {title} (↑{score})",
                    'alert_type': 'game_calendar',
                    'source_name': 'r/XboxGamePass',
                    'source_url': f"https://www.reddit.com{pd.get('permalink', '')}"
                })
                break

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

    return all_issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    print("Testing Game Calendar Monitor...")
    results = check_game_calendar()
    if results:
        for r in results:
            print(f"[{r['game']}] {r['issue']}")
        if POPO_WEBHOOK_URL:
            send_popo_alert(POPO_WEBHOOK_URL, results)
    else:
        print("暂无游戏更新或热门新游。")

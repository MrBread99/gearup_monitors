import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

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

# 非 Steam 游戏通过 Reddit 检测更新
NON_STEAM_GAMES = {
    'Valorant': {'subreddit': 'VALORANT', 'keywords': ['patch', 'update', 'season', 'episode', 'act']},
    'League of Legends': {'subreddit': 'leagueoflegends', 'keywords': ['patch', 'update', 'season', 'preseason']},
    'Fortnite': {'subreddit': 'FortNiteBR', 'keywords': ['update', 'season', 'chapter', 'patch', 'downtime']},
    'Overwatch 2': {'subreddit': 'Overwatch', 'keywords': ['patch', 'update', 'season', 'hero']},
    'Call of Duty': {'subreddit': 'CallOfDuty', 'keywords': ['update', 'season', 'patch', 'warzone']},
    'Aion 2': {'subreddit': 'aion', 'keywords': ['update', 'patch', 'maintenance', 'launch']},
}

# 大版本更新关键词（出现在 Steam News 标题中）
UPDATE_KEYWORDS = [
    "UPDATE", "PATCH", "SEASON", "MAJOR", "RELEASE",
    "WIPE", "NEW MAP", "NEW AGENT", "NEW HERO",
    "CHAPTER", "EPISODE", "ACT", "EXPANSION",
    "LEAGUE", "RANKED", "NEW WEAPON", "REWORK",
    "OPERATION", "EVENT",
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
            f"?appid={app_id}&count=5&maxlength=300&format=json"
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
                date = datetime.fromtimestamp(item.get('date', 0), timezone.utc)
                feed = item.get('feedlabel', '')

                # 跳过已见过的新闻
                if gid in seen_news:
                    continue

                # 只看 48 小时内的
                if date < cutoff:
                    continue

                new_seen.append(gid)

                # 检测是否为大版本更新
                title_upper = title.upper()
                is_major = any(kw in title_upper for kw in UPDATE_KEYWORDS)

                # 优先看官方公告（Community Announcements）
                is_official = feed in ('Community Announcements', 'steam_community_announcements')

                if is_major and is_official:
                    issues.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [大版本更新] {title}",
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
    通过 Reddit 检测非 Steam 游戏的大版本更新/新赛季。
    """
    issues = []

    for game_name, config in NON_STEAM_GAMES.items():
        subreddit = config['subreddit']
        keywords = config['keywords']

        query = '+OR+'.join(keywords)
        url = (
            f"https://www.reddit.com/r/{subreddit}/search.json"
            f"?q=flair%3Aofficial+OR+flair%3Anews+{query}"
            f"&restrict_sr=on&sort=new&t=day&limit=10"
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
                score = post_data.get('ups', 0)
                flair = (post_data.get('link_flair_text', '') or '').upper()

                title_upper = title.upper()
                is_update = any(kw.upper() in title_upper for kw in keywords)
                is_official = 'OFFICIAL' in flair or 'NEWS' in flair or 'PATCH' in flair
                is_hot = score > 100

                if is_update and (is_official or is_hot):
                    issues.append({
                        'game': game_name,
                        'region': 'Global',
                        'country': '',
                        'issue': f"🎮 [版本更新] {title} (↑{score})",
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

            for item in items[:15]:  # 只看前 15
                name = item.get('name', '')
                app_id = item.get('id', 0)
                price = item.get('final_price', 0)

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
                            # 检查是否为最近 7 天发售
                            release_date = app_data.get('release_date', {})
                            if not release_date.get('coming_soon', True):
                                issues.append({
                                    'game': name,
                                    'region': 'Global',
                                    'country': '',
                                    'issue': f"🆕 [热门新游/联机] {name} 登上 Steam {category_key.replace('_', ' ').title()}，有加速需求",
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


def check_game_calendar():
    """主检测函数"""
    all_issues = []

    print("正在检测已追踪游戏的大版本更新 (Steam News)...")
    all_issues.extend(check_steam_news_updates())

    print("正在检测非 Steam 游戏更新 (Reddit)...")
    all_issues.extend(check_non_steam_updates())

    print("正在检测 Steam 热门新游上线...")
    all_issues.extend(check_hot_new_releases())

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

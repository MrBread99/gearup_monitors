import requests
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# ==========================================
# GearUP Booster YouTube 舆情监控
# ==========================================
# 通过 YouTube Data API v3 搜索 GearUP Booster 相关视频，
# 分析近期视频的发布趋势、评分和评论情感。
#
# 环境变量: YOUTUBE_API_KEY
# ==========================================

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

SEARCH_QUERIES = [
    # 英文
    "GearUP Booster",
    "GearUP Booster review",
    "GearUP game booster",
    # 繁体中文
    "GearUP 加速器",
    "GearUP 遊戲加速器 評測",
    # 日语
    "GearUP ゲームブースター",
    "GearUP レビュー",
    # 韩语
    "GearUP 부스터",
    "GearUP 게임 부스터 리뷰",
    # 俄语
    "GearUP Booster обзор",
    # 阿拉伯语
    "GearUP Booster مراجعة",
    "مسرع العاب GearUP",
]

# 情感关键词（用于分析视频标题和描述）
NEGATIVE_KEYWORDS = [
    "SCAM", "VIRUS", "MALWARE", "FAKE", "DON'T", "DONT", "WORST",
    "TERRIBLE", "TRASH", "GARBAGE", "WARNING", "EXPOSED", "HONEST",
    "TRUTH", "AVOID", "UNINSTALL",
    # 中文
    "骗子", "垃圾", "差评", "别买", "坑", "真相", "曝光",
    # 阿拉伯语
    "نصب", "احتيال", "سيء", "فيروس", "ما ينفع", "لا تشتري",
]

POSITIVE_KEYWORDS = [
    "BEST", "AMAZING", "GREAT", "REVIEW", "TUTORIAL", "HOW TO",
    "WORKS", "IMPROVED", "RECOMMEND", "LEGIT", "FIX LAG",
    # 中文
    "好用", "推荐", "测评", "教程", "降低延迟",
    # 阿拉伯语
    "ممتاز", "أفضل", "مراجعة", "أنصح", "يستاهل", "رهيب",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/2.1'
}


def search_youtube_videos(query, max_results=25, hours_window=168):
    """
    通过 YouTube Data API v3 搜索视频。
    默认时间窗口 168 小时（7 天），因为 YouTube 视频发布频率远低于论坛帖子。

    API 配额消耗: search=100, videos=1 per call
    """
    if not YOUTUBE_API_KEY:
        print("[YouTube] 未配置 YOUTUBE_API_KEY 环境变量，跳过。")
        return []

    videos = []
    published_after = (
        datetime.now(timezone.utc) - timedelta(hours=hours_window)
    ).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Step 1: 搜索视频 (消耗 100 配额)
    search_url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&q={requests.utils.quote(query)}"
        f"&type=video&order=date&maxResults={max_results}"
        f"&publishedAfter={published_after}"
        f"&key={YOUTUBE_API_KEY}"
    )

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            error_info = response.json().get('error', {}).get('message', response.status_code)
            print(f"[YouTube] 搜索 '{query}' 失败: {error_info}")
            return []

        data = response.json()
        items = data.get('items', [])

        video_ids = []
        video_snippets = {}

        for item in items:
            vid = item.get('id', {}).get('videoId')
            if vid:
                video_ids.append(vid)
                snippet = item.get('snippet', {})
                video_snippets[vid] = {
                    'title': snippet.get('title', ''),
                    'description': snippet.get('description', ''),
                    'channel': snippet.get('channelTitle', ''),
                    'published': snippet.get('publishedAt', ''),
                }

        if not video_ids:
            return []

        # Step 2: 获取视频统计数据 (消耗 1 配额)
        stats_url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=statistics&id={','.join(video_ids)}"
            f"&key={YOUTUBE_API_KEY}"
        )

        stats_response = requests.get(stats_url, headers=HEADERS, timeout=15)
        stats_data = {}
        if stats_response.status_code == 200:
            for item in stats_response.json().get('items', []):
                stats = item.get('statistics', {})
                stats_data[item['id']] = {
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                }

        # 合并数据
        for vid in video_ids:
            snippet = video_snippets.get(vid, {})
            stats = stats_data.get(vid, {})
            videos.append({
                'id': vid,
                'title': snippet.get('title', ''),
                'description': snippet.get('description', ''),
                'channel': snippet.get('channel', ''),
                'published': snippet.get('published', ''),
                'url': f'https://www.youtube.com/watch?v={vid}',
                'views': stats.get('views', 0),
                'likes': stats.get('likes', 0),
                'comments': stats.get('comments', 0),
            })

    except Exception as e:
        print(f"[YouTube] 搜索 '{query}' 异常: {e}")

    return videos


def analyze_video_sentiment(videos):
    """对视频进行简单的情感分类"""
    negative = []
    positive = []
    neutral = []

    for video in videos:
        content = (video['title'] + ' ' + video['description']).upper()

        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content)
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content)

        if neg_count > pos_count:
            video['sentiment'] = 'negative'
            negative.append(video)
        elif pos_count > neg_count:
            video['sentiment'] = 'positive'
            positive.append(video)
        else:
            video['sentiment'] = 'neutral'
            neutral.append(video)

    return negative, positive, neutral


def check_gearup_youtube(hours_window=168):
    """
    主检测函数：搜索 YouTube，汇总 GearUP Booster 相关视频舆情。
    默认 7 天窗口。
    """
    if not YOUTUBE_API_KEY:
        print("[YouTube] YOUTUBE_API_KEY 未配置，跳过 YouTube 监控。")
        return []

    issues = []
    all_videos = []

    for query in SEARCH_QUERIES:
        print(f"  - 正在搜索 YouTube: '{query}'...")
        results = search_youtube_videos(query, hours_window=hours_window)
        all_videos.extend(results)

    # 去重
    seen_ids = set()
    unique_videos = []
    for v in all_videos:
        if v['id'] not in seen_ids:
            seen_ids.add(v['id'])
            unique_videos.append(v)

    if not unique_videos:
        return issues

    # 情感分析
    negative, positive, neutral = analyze_video_sentiment(unique_videos)

    total = len(unique_videos)
    total_views = sum(v['views'] for v in unique_videos)
    summary_parts = []
    if negative:
        summary_parts.append(f"负面 {len(negative)} 个")
    if positive:
        summary_parts.append(f"正面 {len(positive)} 个")
    if neutral:
        summary_parts.append(f"中性 {len(neutral)} 个")

    days = hours_window // 24
    summary = f"过去{days}天 共 {total} 个视频, 总播放 {total_views:,} ({', '.join(summary_parts)})"

    issue_desc = f"📺 GearUP Booster YouTube 舆情: {summary}"

    # 高播放量视频
    hot_videos = sorted(unique_videos, key=lambda x: x['views'], reverse=True)
    if hot_videos:
        top = hot_videos[0]
        issue_desc += f"\n    🔥 最热视频: \"{top['title'][:50]}\" ({top['channel']}, {top['views']:,} 播放)"

    # 负面视频预警
    if negative:
        top_neg = sorted(negative, key=lambda x: x['views'], reverse=True)[0]
        issue_desc += f"\n    ⚠️ 负面视频: \"{top_neg['title'][:50]}\" ({top_neg['channel']}, {top_neg['views']:,} 播放)"

    issues.append({
        'game': 'GearUP Booster',
        'region': 'Global',
        'country': '',
        'issue': issue_desc,
        'source_name': 'YouTube',
        'source_url': 'https://www.youtube.com/results?search_query=GearUP+Booster'
    })

    return issues


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    # 支持命令行传入 API Key 做本地测试
    if len(sys.argv) > 1:
        YOUTUBE_API_KEY = sys.argv[1]

    print("Testing GearUP YouTube Monitor...")
    results = check_gearup_youtube()
    if results:
        for r in results:
            print(r['issue'])
    else:
        print("过去 7 天无 GearUP 相关 YouTube 视频（或未配置 API Key）。")

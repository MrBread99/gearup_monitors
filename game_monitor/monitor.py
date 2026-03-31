import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from openai import OpenAI

# 自动把根目录加入 path，以便找到 utils 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import apac_osint # 引入亚太区域本地化 OSINT 模块
import downdetector_osint # 引入聚合报错监控模块
import cis_osint # 引入独联体/俄语区 OSINT 模块
import steam_osint # 引入 Steam 差评监控模块
from game_registry import get_apac_configs, get_game_config, get_all_game_names  # 统一游戏注册表
from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL
from utils.reddit_client import reddit_get

# 通义千问 API 客户端（用于总结玩家反馈内容）
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None


def summarize_player_complaints(game_name, post_titles):
    """
    调用通义千问对玩家反馈帖子标题做中文摘要，
    概括玩家具体在抱怨什么网络问题。
    """
    if not qwen_client or not post_titles:
        return ""

    titles_text = '\n'.join(post_titles[:10])  # 最多传 10 条标题

    prompt = f"""你是一个游戏加速器产品经理的助手。以下是 {game_name} 玩家在社区集中反馈的帖子标题，请用 1-2 句中文概括玩家反馈的核心网络问题是什么（如：哪些地区受影响、什么类型的故障、哪个运营商等）。

帖子标题:
{titles_text}

要求: 纯文本输出，不要 Markdown 格式，不要超过 2 句话。"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个游戏网络问题分析专家，输出简洁中文。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Monitor] AI 摘要失败: {e}")
        return ""


# 解决 Windows 控制台输出 Emoji 时的编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def check_reddit_osint(game_name, subreddit):
    """
    通过 OSINT (Reddit) 抓取最近 2 小时内玩家关于服务器、延迟、丢包的集中反馈。
    """
    issues = []
    # 搜索包含服务器、延迟、丢包等关键字的最新帖子
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day"
    
    try:
        response = reddit_get(url)
        if response is None:
            return issues
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            recent_complaints = 0
            two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
            
            regions_mentioned = set()
            countries_mentioned = set()
            complaint_titles = []  # 收集帖子标题用于 AI 摘要
            
            # 关键字映射，用于提取细粒度的国家与大区
            region_map = {
                "NA": "NA", "NORTH AMERICA": "NA",
                "EU": "EU", "EUROPE": "EU", 
                "APAC": "APAC", "ASIA": "APAC", "SEA": "APAC",
                "SA": "SA", "LATAM": "SA", "SOUTH AMERICA": "SA",
                "MIDDLE EAST": "MENA", "MENA": "MENA", "ME": "MENA" # 新增中东大区
            }
            country_map = {
                "JAPAN": "Japan", "TOKYO": "Japan", 
                "KOREA": "South Korea", "SEOUL": "South Korea",
                "BRAZIL": "Brazil", "SAO PAULO": "Brazil",
                "GERMANY": "Germany", "FRANKFURT": "Germany",
                "SYDNEY": "Australia", "AUSTRALIA": "Australia",
                "SINGAPORE": "Singapore",
                # 新增中东地区细分
                "SAUDI": "Saudi Arabia", "KSA": "Saudi Arabia", "STC": "Saudi Arabia (ISP)",
                "BAHRAIN": "Bahrain", "DUBAI": "UAE", "UAE": "UAE"
            }
            
            for post in posts:
                post_data = post['data']
                post_time = datetime.fromtimestamp(post_data['created_utc'], timezone.utc)
                
                # 仅统计过去 2 小时内的反馈
                if post_time > two_hours_ago:
                    recent_complaints += 1
                    title = post_data.get('title', '').upper()
                    text = post_data.get('selftext', '').upper()
                    content = title + " " + text
                    complaint_titles.append(post_data.get('title', ''))  # 原始标题用于 AI
                    
                    for key, val in region_map.items():
                        if key in content: regions_mentioned.add(val) # 改为直接包含匹配，不再强制要求 split 分词
                    for key, val in country_map.items():
                        if key in content: countries_mentioned.add(val)
            
            # 如果 2 小时内有相关的反馈，则根据地区调整触发阈值
            # 欧美大区发帖量大，阈值为 5；其他小区域发帖量小，阈值降为 3
            threshold = 5
            is_minor_region = bool(regions_mentioned.intersection({"MENA", "SA", "APAC"})) or bool(countries_mentioned)
            if is_minor_region:
                threshold = 3
            
            # ======== 商业化优化 3: 热度预测 (Velocity Tracking) ========
            total_upvotes = 0
            total_comments = 0
            for post in posts:
                post_data = post['data']
                post_time = datetime.fromtimestamp(post_data['created_utc'], timezone.utc)
                if post_time > two_hours_ago:
                    total_upvotes += post_data.get('ups', 0)
                    total_comments += post_data.get('num_comments', 0)
                    
            # 降低热度报警门槛：点赞 > 20 或 评论 > 10
            is_viral = total_upvotes > 20 or total_comments > 10
            if is_viral:
                # 即使没达到发帖数量阈值，但单贴热度极高，也强制降低阈值到 1 触发警报
                threshold = 1
            # =========================================================

            if recent_complaints >= threshold:
                detected_region = ", ".join(regions_mentioned) if regions_mentioned else "Global/Unknown"
                detected_country = ", ".join(countries_mentioned) if countries_mentioned else ""
                
                # ======== 商业化优化 1 & 2: 区分故障类型并提取 ISP ========
                # 初始化为通用故障
                issue_desc = f"玩家社区反馈集中 ({recent_complaints}篇帖子/2h) 涉及网络问题"
                
                # 定义 ISP 和路由相关的关键字库 (扩充全球主流与母语别名)
                isp_keywords = [
                    # 俄罗斯 & 独联体
                    "ROSTELECOM", "DOM.RU", "ER-TELECOM", "MTS", "BEELINE", "РОСТЕЛЕКОМ", "БИЛАЙН",
                    # 越南
                    "VIETTEL", "VNPT", "FPT",
                    # 台湾
                    "HINET", "中华电信", "中華電信", "凯擘", "凱擘", "KRO", "台湾大哥大", "台灣大哥大", "远传", "遠傳",
                    # 印尼
                    "INDIHOME", "TELKOMSEL", "BIZNET", "MYREPUBLIC", "FIRST MEDIA",
                    # 菲律宾
                    "PLDT", "CONVERGE", "GLOBE",
                    # 日本
                    "KDDI", "AU HIKARI", "NTT", "FLET", "NURO", "SONY", "JCOM", "SOFTBANK",
                    # 韩国
                    "KT", "KOREA TELECOM", "SK", "SKB", "SK BROADBAND", "LG", "LG U+", "LGU+",
                    # 北美
                    "COMCAST", "XFINITY", "CHARTER", "SPECTRUM", "AT&T", "ATT", "VERIZON", "FIOS", "COX", "CENTURYLINK", "BELL", "ROGERS",
                    # 墨西哥
                    "TOTALPLAY", "TELMEX", "IZZI", "MEGACABLE",
                    # 南美 (巴西/阿根廷/智利等)
                    "VIVO", "CLARO", "OI", "MOVISTAR", "MUNDO", "VTR", "PERSONAL", "FIBERTEL",
                    # 欧洲
                    "BT", "EE", "VIRGIN", "VIRGIN MEDIA", "TELEKOM", "DEUTSCHE TELEKOM", "VODAFONE", "ORANGE", "FREE", "SFR", "MASORANGE", "DIGI", "HYPEROPTIC",
                    # 中东
                    "STC", "MOBILY", "ZAIN", "ETISALAT", "DU"
                ]
                routing_keywords = ["PING", "LAG", "PACKET LOSS", "ROUTING", "LATENCY", "SPIKE", "PACKETLOSS"]
                down_keywords = ["DOWN", "OFFLINE", "LOGIN FAILED", "CRASH", "MAINTENANCE"]

                found_isps = []
                is_routing_issue = False
                is_down_issue = False

                # 短 ISP 名（<=3 字符）需要词边界匹配，防止 "BT" 匹配 "BTW", "SK" 匹配 "SKIN"
                import re
                short_isps = {kw for kw in isp_keywords if len(kw) <= 3}
                long_isps = {kw for kw in isp_keywords if len(kw) > 3}
                
                # 重新扫描合并后的文本以判断问题性质和提取ISP
                for post in posts:
                    post_data = post['data']
                    post_time = datetime.fromtimestamp(post_data['created_utc'], timezone.utc)
                    if post_time > two_hours_ago:
                        content = (post_data.get('title', '') + " " + post_data.get('selftext', '')).upper()
                        
                        # 长 ISP 名直接子串匹配
                        for kw in long_isps:
                            if kw in content and kw not in found_isps:
                                found_isps.append(kw)
                        # 短 ISP 名词边界匹配，且要求同帖出现网络关键词
                        for kw in short_isps:
                            if re.search(r'\b' + re.escape(kw) + r'\b', content):
                                if any(nkw in content for nkw in routing_keywords + ["INTERNET", "ISP", "NETWORK", "CONNECTION"]):
                                    if kw not in found_isps:
                                        found_isps.append(kw)
                        for kw in routing_keywords:
                            if kw in content: is_routing_issue = True
                        for kw in down_keywords:
                            if kw in content: is_down_issue = True

                # 根据分析结果重写 issue 描述，标注加速器是否可解决
                if is_down_issue and not is_routing_issue:
                    issue_desc = "🔴 [加速器无效] 疑似官方宕机/维护"
                elif is_routing_issue:
                    isp_str = f"涉及ISP: {', '.join(found_isps)} " if found_isps else ""
                    # 追加热度标志
                    viral_tag = "🔥 [热度飙升]" if is_viral else ""
                    issue_desc = f"🟢 [加速器可解决] {viral_tag} ⭐⭐⭐ 绝佳营销时机 (路由/高Ping故障) - {isp_str}(共{recent_complaints}篇反馈/2h)"
                else:
                    issue_desc = f"🟡 [待确认] 玩家社区反馈集中 ({recent_complaints}篇帖子/2h) 涉及网络问题，需人工判断"

                # AI 总结玩家反馈内容
                ai_summary = summarize_player_complaints(game_name, complaint_titles)
                if ai_summary:
                    issue_desc += f"\n    玩家反馈概要: {ai_summary}"
                
                # =========================================================

                issues.append({
                    'game': game_name,
                    'region': detected_region,
                    'country': detected_country,
                    'issue': issue_desc,
                    'source_name': f'r/{subreddit}',
                    'source_url': f'https://www.reddit.com/r/{subreddit}/search?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day'
                })
    except Exception as e:
        print(f"[{game_name}] 获取 Reddit 数据时出错: {e}")
        
    return issues

def check_epic_games_status():
    """
    检查 Epic Games 官方 API 获取 Fortnite 服务器状态。
    同一状态的多个组件会合并为一条报警，避免刷屏。
    """
    issues = []
    url = "https://status.epicgames.com/api/v2/components.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            components = response.json().get('components', [])
            
            # 按状态分组聚合异常组件
            status_groups = {}
            for comp in components:
                if "Fortnite" in comp['name'] and comp['status'] != 'operational':
                    status_label = comp['status'].replace('_', ' ').title()
                    if status_label not in status_groups:
                        status_groups[status_label] = []
                    status_groups[status_label].append(comp['name'])
            
            # 每种状态只生成一条合并报警
            for status_label, comp_names in status_groups.items():
                if len(comp_names) == 1:
                    desc = f"🔴 [加速器无效] {comp_names[0]} 官方状态: {status_label}"
                else:
                    desc = f"🔴 [加速器无效] {len(comp_names)} 个组件异常 ({', '.join(comp_names)}) 官方状态: {status_label}"
                issues.append({
                    'game': 'Fortnite',
                    'region': 'Global',
                    'country': '',
                    'issue': desc,
                    'source_name': 'Epic Status API',
                    'source_url': 'https://status.epicgames.com/'
                })
    except Exception as e:
        print(f"[Fortnite] 获取 Epic 状态 API 时出错: {e}")
    return issues

def check_apac_osint_for_game(game_name):
    """
    针对给定的游戏执行亚太地区 (TW, JP, KR) 的本地化监控
    """
    issues = []
    
    # 游戏到各个社区板块 ID 或本地化搜索词的映射 — 从统一游戏注册表 (game_registry.py) 加载
    game_configs = get_apac_configs()
    
    config = game_configs.get(game_name)
    if not config:
        return issues
        
    print(f"    - 正在扫描亚太社区本地化反馈 ({game_name})...")
    
    # 1. 台湾 - 巴哈姆特
    if config['tw_bsn']:
        tw_res = apac_osint.check_taiwan_bahamut(game_name, config['tw_bsn'])
        if tw_res: issues.append(tw_res)
        
    # 3. 韩国 - DC Inside
    kr_res = apac_osint.check_korea_dcinside(game_name, config['kr_dc'], gallery_type=config.get('kr_dc_type', 'major'))
    if kr_res: issues.append(kr_res)
        
    return issues

def check_all_channels_for_game(game_name, reddit_sub, apac_name):
    """
    统一入口：一次性检查某个游戏的所有渠道 (Reddit, APAC, CIS, 聚合报错)
    """
    issues = []
    
    # 1. 检查 Reddit
    issues.extend(check_reddit_osint(game_name, reddit_sub))
    
    # 2. 检查亚太本土社区
    issues.extend(check_apac_osint_for_game(apac_name or game_name))
    
    # 3. 检查独联体/俄语区 (VK.com)
    cis_res = cis_osint.check_cis_vk(game_name)
    if cis_res: issues.append(cis_res)
    # detector404.ru 在 main() 中批量调用，不在此逐个调用
    
    # 4. 检查全球故障聚合网站 (替代 Downdetector)
    dd_res = downdetector_osint.check_downdetector_global(game_name)
    if dd_res: issues.append(dd_res)
    
    # 5. 检查 Steam 近期差评中的网络问题
    steam_res = steam_osint.check_steam_reviews(game_name)
    if steam_res: issues.append(steam_res)
        
    return issues

from utils.alert_dedup import process_alerts


def main():
    all_issues = []
    
    # 从统一游戏注册表 (game_registry.py) 加载所有游戏名，动态遍历
    for game_name in get_all_game_names():
        config = get_game_config(game_name)
        subreddit = config.get('subreddit', '')
        
        print(f"正在检测 {game_name}...")
        
        # Fortnite 额外检查 Epic Games 官方状态 API
        if game_name == 'Fortnite':
            all_issues.extend(check_epic_games_status())
        
        all_issues.extend(check_all_channels_for_game(game_name, subreddit, game_name))
    
    # detector404.ru 批量检测（中等合并，高级别逐条）
    print("正在批量检测 detector404.ru 俄罗斯区故障...")
    all_issues.extend(cis_osint.check_detector404_batch(get_all_game_names()))
    
    # 平台与通讯工具状态检测（合并到同一条消息）
    print("正在检测平台与通讯工具状态...")
    import platform_status_monitor
    all_issues.extend(platform_status_monitor.check_all_platforms())
    
    # 处理报警：🔴 加速器无效合并去重，🟢🟡 正常输出
    all_issues = process_alerts(all_issues)
    
    # 发送通知汇总（游戏+平台合并一条消息）
    send_popo_alert(POPO_WEBHOOK_URL, all_issues)
    # 发送反爬拦截警告（如有）
    flush_scrape_block_alerts(POPO_WEBHOOK_URL)

if __name__ == "__main__":
    main()
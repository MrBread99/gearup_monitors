import requests
import json
import os
from datetime import datetime, timezone, timedelta

# 从环境变量中获取 POPO Webhook URL
POPO_WEBHOOK_URL = os.environ.get("POPO_WEBHOOK_URL")

def send_popo_alert(webhook_url, issues_list):
    """
    将问题列表格式化为 Markdown 表格，并发送至 NetEase POPO Webhook。
    如果列表为空，发送一切正常的通知。
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not issues_list:
        md_content = f"✅ **全球游戏网络监控报告** ✅\n*监控时间: {current_time} (过去4小时)*\n\n目前各大热门 PC 游戏（Valorant, LOL, APEX, CS2, Fortnite）各服务器网络状态平稳，未检测到大规模丢包或宕机异常，请放心游玩！"
    else:
        # 构造 Markdown 表格
        md_content = f"🚨 **全球游戏网络监控警报** 🚨\n*监控时间: {current_time} (过去4小时)*\n\n"
        md_content += "| 游戏 | 地区/国家 | 问题反馈 | 数据来源 |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"
        
        for item in issues_list:
            # 处理国家/地区的展示
            region_display = f"{item['region']} ({item['country']})" if item.get('country') else item['region']
            # 处理带有可点击链接的数据来源
            source_display = f"[{item['source_name']}]({item['source_url']})" if item.get('source_url') else item['source_name']
            
            md_content += f"| **{item['game']}** | {region_display} | {item['issue']} | {source_display} |\n"

    headers = {'Content-Type': 'application/json'}
    payload = {
        "msg_type": "text",
        "content": {
            "text": md_content
        }
    }
    
    if not webhook_url:
        print("未配置 POPO_WEBHOOK_URL，控制台输出结果如下：\n")
        print(md_content)
        return

    try:
        response = requests.post(webhook_url, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        print("成功发送警报至 POPO Webhook。")
    except Exception as e:
        print(f"发送 POPO 警报失败: {e}")

def check_reddit_osint(game_name, subreddit):
    """
    通过 OSINT (Reddit) 抓取最近 4 小时内玩家关于服务器、延迟、丢包的集中反馈。
    """
    issues = []
    # 搜索包含服务器、延迟、丢包等关键字的最新帖子
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Monitor/1.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            recent_complaints = 0
            four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
            
            regions_mentioned = set()
            countries_mentioned = set()
            
            # 关键字映射，用于提取细粒度的国家与大区
            region_map = {"NA": "NA", "EU": "EU", "APAC": "APAC", "SA": "SA", "LATAM": "SA", "ASIA": "APAC"}
            country_map = {
                "JAPAN": "Japan", "TOKYO": "Japan", 
                "KOREA": "South Korea", "SEOUL": "South Korea",
                "BRAZIL": "Brazil", "SAO PAULO": "Brazil",
                "GERMANY": "Germany", "FRANKFURT": "Germany",
                "SYDNEY": "Australia", "AUSTRALIA": "Australia",
                "SINGAPORE": "Singapore"
            }
            
            for post in posts:
                post_data = post['data']
                post_time = datetime.fromtimestamp(post_data['created_utc'], timezone.utc)
                
                # 仅统计过去 4 小时内的反馈
                if post_time > four_hours_ago:
                    recent_complaints += 1
                    title = post_data.get('title', '').upper()
                    text = post_data.get('selftext', '').upper()
                    content = title + " " + text
                    
                    for key, val in region_map.items():
                        if key in content.split(): regions_mentioned.add(val)
                    for key, val in country_map.items():
                        if key in content.split(): countries_mentioned.add(val)
            
            # 如果 4 小时内有 5 个以上的集中反馈，则触发警报 (阈值可调)
            if recent_complaints >= 5:
                detected_region = ", ".join(regions_mentioned) if regions_mentioned else "Global/Unknown"
                detected_country = ", ".join(countries_mentioned) if countries_mentioned else ""
                
                issues.append({
                    'game': game_name,
                    'region': detected_region,
                    'country': detected_country,
                    'issue': f"玩家社区反馈集中 ({recent_complaints}篇帖子/4h) 涉及延迟或丢包",
                    'source_name': f'r/{subreddit}',
                    'source_url': f'https://www.reddit.com/r/{subreddit}/search?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day'
                })
    except Exception as e:
        print(f"[{game_name}] 获取 Reddit 数据时出错: {e}")
        
    return issues

def check_epic_games_status():
    """
    检查 Epic Games 官方 API 获取 Fortnite 服务器状态。
    """
    issues = []
    url = "https://status.epicgames.com/api/v2/components.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            components = response.json().get('components', [])
            for comp in components:
                if "Fortnite" in comp['name'] and comp['status'] != 'operational':
                    issues.append({
                        'game': 'Fortnite',
                        'region': 'Global',
                        'country': '',
                        'issue': f"{comp['name']} 官方状态: {comp['status'].replace('_', ' ').title()}",
                        'source_name': 'Epic Status API',
                        'source_url': 'https://status.epicgames.com/'
                    })
    except Exception as e:
        print(f"[Fortnite] 获取 Epic 状态 API 时出错: {e}")
    return issues

def main():
    all_issues = []
    
    print("正在检测 Valorant...")
    all_issues.extend(check_reddit_osint('Valorant', 'VALORANT'))
    
    print("正在检测 League of Legends...")
    all_issues.extend(check_reddit_osint('League of Legends', 'leagueoflegends'))
    
    print("正在检测 APEX Legends...")
    all_issues.extend(check_reddit_osint('APEX Legends', 'apexlegends'))
    
    print("正在检测 CS2...")
    all_issues.extend(check_reddit_osint('CS2', 'GlobalOffensive'))
    
    print("正在检测 Fortnite...")
    all_issues.extend(check_epic_games_status())
    all_issues.extend(check_reddit_osint('Fortnite', 'FortNiteBR'))
    
    # 发送通知汇总
    send_popo_alert(POPO_WEBHOOK_URL, all_issues)

if __name__ == "__main__":
    main()

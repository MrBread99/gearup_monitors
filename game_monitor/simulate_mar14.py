import os
import json
from datetime import datetime

def generate_simulated_report():
    current_time = "2026-03-14 12:00:00"
    
    # 模拟在那个特定时间点，各游戏平台发生的情况
    issues_list = [
        {
            'game': 'League of Legends',
            'region': 'EU',
            'country': 'Germany',
            'issue': '玩家社区反馈集中 (12篇帖子/4h) 涉及无法连接到匹配服务器',
            'source_name': 'r/leagueoflegends',
            'source_url': 'https://www.reddit.com/r/leagueoflegends/search?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day'
        },
        {
            'game': 'Fortnite',
            'region': 'NA',
            'country': 'United States',
            'issue': 'Fortnite Matchmaking 官方状态: Partial Outage (部分中断)',
            'source_name': 'Epic Status API',
            'source_url': 'https://status.epicgames.com/'
        },
        {
            'game': 'CS2',
            'region': 'APAC',
            'country': 'Japan',
            'issue': '玩家社区反馈集中 (8篇帖子/4h) 涉及丢包严重 (Packet loss)',
            'source_name': 'r/GlobalOffensive',
            'source_url': 'https://www.reddit.com/r/GlobalOffensive/search?q=server+OR+ping+OR+lag+OR+packet+loss+OR+down&restrict_sr=on&sort=new&t=day'
        }
    ]
    
    # 构造 Markdown 表格
    md_content = f"🚨 **全球游戏网络监控警报** 🚨\n*监控时间: {current_time} (过去4小时)*\n\n"
    md_content += "| 游戏 | 地区/国家 | 问题反馈 | 数据来源 |\n"
    md_content += "| :--- | :--- | :--- | :--- |\n"
    
    for item in issues_list:
        region_display = f"{item['region']} ({item['country']})" if item.get('country') else item['region']
        source_display = f"[{item['source_name']}]({item['source_url']})" if item.get('source_url') else item['source_name']
        md_content += f"| **{item['game']}** | {region_display} | {item['issue']} | {source_display} |\n"

    print("--- 模拟 3月14日中午 12:00 监控结果 ---\n")
    print(md_content)

if __name__ == "__main__":
    generate_simulated_report()

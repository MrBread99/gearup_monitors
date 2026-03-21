import requests
import json
import os
from datetime import datetime

# 从环境变量中获取 POPO Webhook URL
POPO_WEBHOOK_URL = os.environ.get("POPO_WEBHOOK_URL")

def send_popo_alert(webhook_url, issues_list):
    """
    将问题列表格式化为纯文本，并发送至 NetEase POPO Webhook。
    支持按 alert_type 分组输出不同标题的报警。
    为了减少打扰，如果 issues_list 为空，直接静默退出。
    """
    if not issues_list:
        print("未检测到异常或情报，静默退出，不发送打扰信息。")
        return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 按 alert_type 分组
    ALERT_TITLES = {
        'game_monitor': '【全球监控商机雷达警报】',
        'new_game_release': '【新游上线预告】',
        'game_update': '【热游版本更新预告】',
        'game_calendar': '【新游上线/热游更新预告】',
        'platform_status': '【平台与通讯工具状态警报】',
        'brand_monitor': '【品牌舆情监控报告】',
        'competitor_radar': '【竞品情报警报】',
    }

    groups = {}
    for item in issues_list:
        alert_type = item.get('alert_type', 'game_monitor')
        if alert_type not in groups:
            groups[alert_type] = []
        groups[alert_type].append(item)

    # 构造极简纯文本格式
    plain_content = ""
    for alert_type, items in groups.items():
        title = ALERT_TITLES.get(alert_type, '【监控警报】')
        plain_content += f"{title}\n时间: {current_time}\n\n"

        for item in items:
            # 去掉 issue 中可能包含的粗体和红灯 emoji
            clean_issue = item['issue'].replace('**', '').replace('__', '')

            plain_content += f"[{item['game']}]\n"

            # 新游上线/热游更新不显示"地区: Global"（issue 内已有头部地区信息）
            if alert_type not in ('new_game_release', 'game_update'):
                region_display = f"{item['region']} ({item['country']})" if item.get('country') else item['region']
                plain_content += f"地区: {region_display}\n"

            plain_content += f"情报: {clean_issue}\n"

            if item.get('source_url'):
                plain_content += f"来源: {item['source_name']} ({item['source_url']})\n"
            else:
                plain_content += f"来源: {item['source_name']}\n"

            plain_content += "-" * 30 + "\n"

        plain_content += "\n"

    headers = {'Content-Type': 'application/json'}
    payload = {
        "message": plain_content
    }
    
    if not webhook_url:
        print("未配置 POPO_WEBHOOK_URL，控制台输出结果如下：\n")
        print(plain_content)
        return

    try:
        response = requests.post(webhook_url, headers=headers, data=json.dumps(payload), timeout=10)
        # 无论成功还是失败，打印 POPO 的真实返回内容，方便排查原因
        print(f"POPO 接口返回 HTTP 状态码: {response.status_code}")
        print(f"POPO 接口返回详细内容: {response.text}")
        response.raise_for_status()
        print("代码执行：成功发送请求至 POPO Webhook。")
    except Exception as e:
        print(f"发送 POPO 警报失败: {e}")

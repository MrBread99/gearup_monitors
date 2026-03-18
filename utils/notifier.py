import requests
import json
import os
from datetime import datetime

# 从环境变量中获取 POPO Webhook URL
POPO_WEBHOOK_URL = os.environ.get("POPO_WEBHOOK_URL")

def send_popo_alert(webhook_url, issues_list):
    """
    将问题列表格式化为 Markdown 表格，并发送至 NetEase POPO Webhook。
    【重要修改】：为了减少打扰，如果 issues_list 为空，直接静默退出，不再发送“一切正常”的通知。
    """
    if not issues_list:
        print("未检测到异常或情报，静默退出，不发送打扰信息。")
        return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 构造 Markdown 表格
    md_content = f"🚨 **全球监控商机雷达警报** 🚨\n*监控时间: {current_time}*\n\n"
    md_content += "| 监控项 | 地区/国家 | 情报反馈 | 数据来源 |\n"
    md_content += "| :--- | :--- | :--- | :--- |\n"
        
    for item in issues_list:
        # 处理国家/地区的展示
        region_display = f"{item['region']} ({item['country']})" if item.get('country') else item['region']
        # 处理带有可点击链接的数据来源
        source_display = f"[{item['source_name']}]({item['source_url']})" if item.get('source_url') else item['source_name']
        
        md_content += f"| **{item['game']}** | {region_display} | {item['issue']} | {source_display} |\n"

    headers = {'Content-Type': 'application/json'}
    # 根据 POPO 官方群机器人要求，最基础且一定能识别的字段名为 "message"
    payload = {
        "message": md_content
    }
    
    if not webhook_url:
        print("未配置 POPO_WEBHOOK_URL，控制台输出结果如下：\n")
        print(md_content)
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

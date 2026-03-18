import requests
import os
import json
from datetime import datetime, timezone, timedelta

# 这里的 sys.path 处理和 monitor 类似，以便能引入 utils 和 openai
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL
from openai import OpenAI

# 1. 基础配置
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")

# 你的私人服务器频道 ID
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "")

# 初始化通义千问客户端
client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None

def summarize_with_qwen(content, author_name):
    """调用通义千问提炼情报"""
    if not client:
        return f"**(AI未配置，原话如下)**\n{content[:500]}..."
        
    prompt = f"""
    你是一个全球游戏加速器（GPN）的资深商业情报分析师。
    我们刚刚从竞品【{author_name}】的官方 Discord 拦截到了一条最新公告。
    
    【公告原文】: {content}
    
    请分析这段情报，输出格式如下：
    1. 【核心情报】: 用一句中文高度概括（如：修复了某某节点、更新了版本、搞促销等）。
    2. 【商业建议】: 我们应该如何应对？(简短1-2句即可)
    (请注意：输出纯文本，绝对不要使用任何 Markdown 加粗或者特殊符号)
    """
    
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是一个敏锐的游戏加速器情报专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"AI 生成失败: {e}")
        return f"**(AI 分析失败，原话如下)**\n{content[:300]}..."

def fetch_recent_discord_messages():
    """
    使用 Discord REST API (无需保持长连接)，主动去拉取频道里最近的消息。
    """
    if not DISCORD_BOT_TOKEN or not TARGET_CHANNEL_ID:
        print("错误: 缺少 DISCORD_BOT_TOKEN 或 TARGET_CHANNEL_ID 环境变量。")
        return []
        
    # Discord API 拉取消息的 Endpoint
    url = f"https://discord.com/api/v10/channels/{TARGET_CHANNEL_ID}/messages?limit=10"
    
    # 必须以 Bot Token 身份请求
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"抓取 Discord 失败! HTTP {response.status_code}: {response.text}")
            return []
            
        messages = response.json()
        
        # 只筛选出过去 4 小时内的消息
        four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
        valid_messages = []
        
        for msg in messages:
            # Discord 的 timestamp 是 ISO 8601 格式
            msg_time = datetime.fromisoformat(msg['timestamp'])
            
            if msg_time > four_hours_ago:
                valid_messages.append(msg)
                
        return valid_messages
        
    except Exception as e:
        print(f"请求 Discord API 异常: {e}")
        return []

def main():
    print("开始主动侦测 Discord 私人情报频道的最新消息...")
    recent_msgs = fetch_recent_discord_messages()
    
    if not recent_msgs:
        print("过去 4 小时内，Discord 情报频道没有新动态。")
        return
        
    print(f"抓取到 {len(recent_msgs)} 条新动态，正在交由通义千问分析...")
    
    for msg in recent_msgs:
        content = msg.get('content', '')
        
        # 如果公告是在 Embed 卡片里发送的
        if not content and 'embeds' in msg and msg['embeds']:
            for embed in msg['embeds']:
                if 'description' in embed and embed['description']:
                    content += embed['description'] + " "
                    
        if not content.strip():
            continue
            
        # 提取发件人名字
        author_name = msg.get('author', {}).get('username', 'Unknown')
        # 如果是 webhook 转发，通常真正的名字会被存在 webhook 的名字里
        
        ai_analysis = summarize_with_qwen(content, author_name)
        
        # 构造纯文本推流格式
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plain_content = f"【竞品 Discord 情报雷达】\n"
        plain_content += f"时间: {current_time}\n"
        plain_content += f"来源: {author_name}\n\n"
        
        clean_ai = ai_analysis.replace('**', '').replace('__', '')
        plain_content += f"{clean_ai}\n\n"
        
        # 尝试拼凑消息的跳转链接
        guild_id = msg.get('guild_id', '@me') # 有些 webhook 抓不到 guild_id
        jump_url = f"https://discord.com/channels/{guild_id}/{TARGET_CHANNEL_ID}/{msg['id']}"
        plain_content += f"跳转至原文: {jump_url}"
        
        headers = {'Content-Type': 'application/json'}
        payload = {"message": plain_content}
        
        # 发送给 POPO
        if not POPO_WEBHOOK_URL:
            print("未配置 POPO_WEBHOOK_URL，控制台输出如下：\n" + plain_content)
        else:
            try:
                r = requests.post(POPO_WEBHOOK_URL, headers=headers, data=json.dumps(payload), timeout=10)
                r.raise_for_status()
                print("成功推送至 POPO！")
            except Exception as e:
                print(f"发送 POPO 警报失败: {e}")

if __name__ == "__main__":
    main()

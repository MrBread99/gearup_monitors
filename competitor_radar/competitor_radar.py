import requests
from bs4 import BeautifulSoup
import feedparser
import os
import sys
import json
import urllib.parse
from datetime import datetime, timezone, timedelta
from openai import OpenAI

# 自动把根目录加入 path，以便找到 utils 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, POPO_WEBHOOK_URL

# 解决 Windows 控制台输出的编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# ==========================================
# 1. 配置区域
# ==========================================

# 1.1 竞品官网/新闻源配置
# (很多官网使用 WordPress 或类似架构，可以尝试直接抓取 /feed/ 或 /rss/)
COMPETITORS = {
    'ExitLag': {
        'url': 'https://www.exitlag.com/news',
        'type': 'scraping', # 需要写特定爬虫
        'selector': '.news-list-item' # 假设的 CSS 选择器，需根据实际情况调整
    },
    'WTFast': {
        'url': 'https://blog.wtfast.com/rss.xml', # 尝试使用 RSS
        'type': 'rss'
    },
    'GearUP Booster': {
        'url': 'https://www.gearupbooster.com/blog/',
        'type': 'scraping',
        'selector': '.blog-card'
    }
}

# 1.2 监控关键字 (情报过滤)
# 我们只关心跟这些词相关的官方通告
TARGET_KEYWORDS = [
    # 路由/节点相关 (最重要)
    'route', 'routing', 'node', 'server', 'latency', 'ping', 'connection', 'fix', 'resolved', 'isp', 'telecom', 'added', 'new server',
    # 新游戏/打折
    'support', 'new game', 'sale', 'black friday', 'discount', 'off',
    # 宕机
    'outage', 'down', 'maintenance'
]

# 1.3 通义千问 (Qwen) 配置 (用于总结和翻译)
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")
# 使用 OpenAI 的 SDK，但是把 base_url 指向阿里云百炼的端点
client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None

# ==========================================
# 2. 抓取逻辑
# ==========================================

def fetch_rss_feed(competitor_name, feed_url):
    """通过 RSS 获取最新动态"""
    results = []
    feed = feedparser.parse(feed_url)
    
    # 设定只看过去 24 小时的内容
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    
    for entry in feed.entries:
        try:
            # 尝试解析发布时间
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                # 获取时间元组进行显式转换
                t = entry.published_parsed
                import time
                if isinstance(t, time.struct_time):
                    published_time = datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, tzinfo=timezone.utc)
                else:
                    try:
                        # 忽略类型检查系统的误报，由于 feedparser 返回的数据结构比较特殊
                        t_year = int(str(t[0]))
                        t_mon = int(str(t[1]))
                        t_mday = int(str(t[2]))
                        t_hour = int(str(t[3]))
                        t_min = int(str(t[4]))
                        t_sec = int(str(t[5]))
                        published_time = datetime(t_year, t_mon, t_mday, t_hour, t_min, t_sec, tzinfo=timezone.utc)
                    except Exception:
                        continue
            else:
                continue
                
            if published_time > yesterday:
                title = str(entry.title)
                link = str(entry.link)
                
                # 检查内容
                content = ""
                if 'summary' in entry:
                    content = str(entry.summary)
                elif 'description' in entry:
                    content = str(entry.description)
                
                # 检查是否包含目标关键词
                text_to_check = (title + " " + content).lower()
                matched_keywords = [kw for kw in TARGET_KEYWORDS if kw in text_to_check]
                
                if matched_keywords:
                    results.append({
                        'competitor': competitor_name,
                        'title': title,
                        'link': link,
                        'content': BeautifulSoup(content, "html.parser").text[:500], # 剥离HTML标签，取前500字
                        'matched_keywords': matched_keywords,
                        'source_type': 'RSS'
                    })
        except Exception as e:
            print(f"Error parsing RSS entry for {competitor_name}: {e}")
            continue
            
    return results

def fetch_website_scraping(competitor_name, url, selector):
    """简单的网页爬虫 (作为没有 RSS 时的备用)"""
    # 这部分高度依赖竞品网站的 DOM 结构，需要根据实际页面去调整 CSS 选择器。
    # 为了演示，这里写一个通用框架
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.select(selector)[:5] # 只看最新 5 篇
            
            for article in articles:
                # 尝试提取标题和链接
                a_tag = article.find('a')
                if not a_tag: continue
                
                title = str(a_tag.text).strip()
                link_attr = a_tag.get('href', '')
                link = str(link_attr[0] if isinstance(link_attr, list) else link_attr)
                
                if link.startswith('/'):
                    # 处理相对路径
                    parsed_url = urllib.parse.urlparse(url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    link = base_url + link
                    
                text_to_check = title.lower()
                matched_keywords = [kw for kw in TARGET_KEYWORDS if kw in text_to_check]
                
                if matched_keywords:
                    # 注意：网页爬虫很难判断精确时间，所以这里可能会抓到老文章
                    results.append({
                        'competitor': competitor_name,
                        'title': title,
                        'link': link,
                        'content': "原文内容需点击链接查看",
                        'matched_keywords': matched_keywords,
                        'source_type': 'Website Blog'
                    })
    except Exception as e:
        print(f"Error scraping {competitor_name}: {e}")
        
    return results

# ==========================================
# 3. AI 处理逻辑 (翻译与总结摘要)
# ==========================================

def summarize_with_ai(news_item):
    """
    使用 LLM 把竞品英文动态翻译成中文，并提取商业情报摘要。
    """
    if not QWEN_API_KEY:
        # 如果没有配置 API Key，直接返回一个降级的文本
        return f"**(未配置AI摘要, 以下为原文)**\n{news_item['title']}\n关键词命中: {', '.join(news_item['matched_keywords'])}"
        
    prompt = f"""
    你是一个全球游戏加速器（VPN/GPN）的高级商业分析师。
    我刚刚拦截到了竞争对手【{news_item['competitor']}】发布的最新动态。
    
    【标题】: {news_item['title']}
    【原文节选】: {news_item['content']}
    
    请帮我分析这段情报，输出格式如下：
    1. 🎯 **核心情报**: 用一句话高度概括（中文）。比如“新增了从XX到XX的节点”、“支持了某某新游戏”、“开启了黑五打折”。
    2. 💡 **商业建议**: 根据这条情报，我们的产品应该如何应对？（比如：检查我们相同线路的质量、跟进营销等。简短即可）
    """
    
    try:
        if not client:
            return f"**(AI 客户端未初始化, 以下为原文)**\n{news_item['title']}"
            
        response = client.chat.completions.create(
            model="qwen-plus", # 替换为通义千问模型
            messages=[
                {"role": "system", "content": "你是一个游戏加速器行业的情报专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=250
        )
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"AI 摘要生成失败: {e}")
        return f"**(AI 分析失败, 以下为原文)**\n{news_item['title']}"

# ==========================================
# 4. 汇总与报警
# ==========================================

def check_all_competitors():
    all_news = []
    print("开始侦测竞品动态...")
    
    for name, config in COMPETITORS.items():
        print(f"正在扫描: {name}...")
        if config['type'] == 'rss':
            news = fetch_rss_feed(name, config['url'])
            all_news.extend(news)
        elif config['type'] == 'scraping':
            # 在实际生产中，你需要根据 ExitLag 或 GearUP 官网真实的 DOM 结构去调整 `selector`
            news = fetch_website_scraping(name, config['url'], config['selector'])
            all_news.extend(news)
            
    return all_news

def main():
    competitor_news = check_all_competitors()
    
    if not competitor_news:
        print("过去 24 小时内未发现竞品有重要动态发布。")
        return
        
    # 借用原来 send_popo_alert 的格式结构
    # 但因为我们需要展示 AI 摘要，原本表格结构太窄，我们把 summary 放进 issue 字段
    formatted_issues = []
    
    print(f"发现 {len(competitor_news)} 条竞品高价值动态！正在进行 AI 分析...")
    
    for item in competitor_news:
        ai_analysis = summarize_with_ai(item)
        
        formatted_issues.append({
            'game': item['competitor'], # 借用 game 字段显示竞品名
            'region': '竞品情报', # 借用 region 字段显示分类
            'country': '',
            'issue': ai_analysis, # 将 AI 的长文分析放入 issue 栏
            'source_name': '官方公告',
            'source_url': item['link']
        })
        
    send_popo_alert(POPO_WEBHOOK_URL, formatted_issues)

if __name__ == "__main__":
    main()
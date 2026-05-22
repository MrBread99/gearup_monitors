import os
from openai import OpenAI

# ==========================================
# 品牌舆情 AI 总结
# ==========================================
# 把所有帖子标题+链接一起给 AI，由 AI 统一判断分类和总结，
# 避免关键词分类和 AI 总结不一致的问题。
# ==========================================

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None

COMPETITOR_KEYWORDS = [
    "ExitLag", "LagoFast", "NoPing", "Hone.gg", "wtfast", "Mudfish",
    "UU加速器", "迅游", "雷神", "엑싯랙", "드롭스마이너",
]
HIGH_RISK_KEYWORDS = [
    "refund", "scam", "fraud", "virus", "malware", "doesn't work", "doesnt work",
    "환불", "사기", "안됨", "退費", "退款", "騙錢", "诈骗", "обман", "возврат",
]


def _combined_text(posts):
    return "\n".join(str(p.get("title", "")) for p in posts)


def _has_keyword(text, keywords):
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def _should_call_qwen(region_name, positive_posts, negative_posts, neutral_posts):
    all_posts = positive_posts + negative_posts + neutral_posts
    if not all_posts:
        return False

    text = _combined_text(all_posts)
    if negative_posts or _has_keyword(text, HIGH_RISK_KEYWORDS):
        return True
    if _has_keyword(text, COMPETITOR_KEYWORDS):
        return True

    if "youtube" in region_name.lower():
        total_views = sum(int(p.get("views", 0) or 0) for p in all_posts)
        return len(all_posts) >= 10 or total_views >= 1000

    return False


def _fallback_summary(unique_posts):
    links = [f"{p.get('title', '')[:40]} ({p.get('url', '')})" for p in unique_posts[:3] if p.get('url')]
    if links:
        return f"共 {len(unique_posts)} 篇讨论。代表帖子: {'; '.join(links)}"
    return f"共 {len(unique_posts)} 篇讨论。"


def summarize_sentiment(brand_name, region_name, positive_posts, negative_posts, neutral_posts):
    """
    对品牌舆情进行 AI 分类总结，并附上来源链接。
    将所有帖子合并后交给 AI 统一分析，避免关键词分类与 AI 总结不一致。
    """
    # 合并所有帖子，附带编号和链接
    all_posts = []
    for p in positive_posts:
        all_posts.append(p)
    for p in negative_posts:
        all_posts.append(p)
    for p in neutral_posts:
        all_posts.append(p)

    if not all_posts:
        return ""

    # 去重
    seen = set()
    unique_posts = []
    for p in all_posts:
        key = p.get('title', '')[:50]
        if key and key not in seen:
            seen.add(key)
            unique_posts.append(p)

    reference_posts = unique_posts[:15]

    should_call_qwen = qwen_client and _should_call_qwen(
        region_name, positive_posts, negative_posts, neutral_posts
    )

    if not should_call_qwen:
        from utils.brand_report import add_report_section, get_report_url
        fallback_text = _fallback_summary(unique_posts)
        if qwen_client:
            fallback_text += "\nAI总结: 未命中重点阈值，已跳过 Qwen 调用。"
        else:
            fallback_text += "\nAI总结: QWEN_API_KEY 未配置，使用基础摘要。"
        add_report_section(
            region_name,
            brand_name,
            positive_posts,
            negative_posts,
            neutral_posts,
            fallback_text,
            reference_posts=reference_posts,
        )
        return f"{fallback_text}\n详细来源: {get_report_url(region_name, brand_name)}"

    # 构建带编号和链接的帖子列表（最多 15 条给 AI）
    post_lines = []
    for i, p in enumerate(reference_posts, 1):
        title = p.get('title', '')[:120]
        url = p.get('url', '')
        source = p.get('source', '')
        line = f"[{i}] {title}"
        if url:
            line += f" | 链接: {url}"
        if source:
            line += f" | 来源: {source}"
        post_lines.append(line)

    posts_text = '\n'.join(post_lines)

    prompt = f"""你是一个游戏加速器品牌舆情分析师。以下是 {region_name} 地区关于 {brand_name} 的 {len(unique_posts)} 篇社区讨论帖子。

请你自己判断每篇帖子属于正面、负面还是中性，然后分别总结。

帖子列表:
{posts_text}

重要要求:
- 如果帖子中提到了其他竞品加速器或 VPN（如 ExitLag, LagoFast, NoPing, Hone.gg, wtfast, Mudfish, UU加速器, 迅游, 雷神 等），必须在总结中写出具体的竞品名称。
- 每条总结后面用方括号标注对应的帖子编号，如 [1][3]。
- 如果某个分类没有对应的帖子，写"暂无"。

请严格按以下格式输出（纯文本，禁止 Markdown，每项 1-2 句话）:
正面评价: （总结 + 帖子编号）
负面评价: （总结 + 帖子编号）
中性讨论: （总结 + 帖子编号）
涉及竞品: （列出所有竞品/VPN 名称，逗号分隔，无则写"无"）
商业洞察: （1 句建议）"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是品牌舆情分析师，输出简洁中文。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=400
        )
        ai_text = str(response.choices[0].message.content).strip()

        # 来源链接写入报告文件，不放在报警里
        from utils.brand_report import add_report_section, get_report_url
        add_report_section(
            region_name,
            brand_name,
            positive_posts,
            negative_posts,
            neutral_posts,
            ai_text,
            reference_posts=reference_posts,
        )

        # 报警里只附报告链接
        ai_text += f'\n详细来源: {get_report_url(region_name, brand_name)}'

        return ai_text

    except Exception as e:
        print(f"[Brand AI] 舆情总结失败: {e}")
        return ""

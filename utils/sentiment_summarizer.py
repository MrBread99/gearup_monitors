import os
from openai import OpenAI

# ==========================================
# 品牌舆情 AI 总结
# ==========================================
# 调用通义千问对各地区品牌舆情进行分类总结，
# 并附上每类评价的代表性帖子链接。
# ==========================================

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None


def _extract_top_links(posts, max_count=2):
    """提取帖子列表中前 N 条的链接"""
    links = []
    for p in posts[:max_count]:
        url = p.get('url', '')
        title = p.get('title', '')[:40]
        if url:
            links.append(f"{title} ({url})")
        elif title:
            links.append(title)
    return links


def summarize_sentiment(brand_name, region_name, positive_posts, negative_posts, neutral_posts):
    """
    对品牌舆情进行 AI 分类总结，并附上来源链接。
    """
    if not qwen_client:
        # AI 不可用时，只返回链接摘要
        result = ""
        if positive_posts:
            links = _extract_top_links(positive_posts)
            result += f"正面评价 ({len(positive_posts)} 篇): " + '; '.join(links) + "\n"
        if negative_posts:
            links = _extract_top_links(negative_posts)
            result += f"负面评价 ({len(negative_posts)} 篇): " + '; '.join(links) + "\n"
        return result.strip() if result else ""

    # 提取标题用于 AI 分析（每类最多 5 条）
    pos_titles = '\n'.join(
        f"- {p.get('title', '')[:100]}"
        for p in positive_posts[:5]
    ) or "（无）"

    neg_titles = '\n'.join(
        f"- {p.get('title', '')[:100]}"
        for p in negative_posts[:5]
    ) or "（无）"

    neu_titles = '\n'.join(
        f"- {p.get('title', '')[:100]}"
        for p in neutral_posts[:5]
    ) or "（无）"

    prompt = f"""你是一个游戏加速器品牌舆情分析师。请根据以下 {region_name} 地区关于 {brand_name} 的讨论帖子标题，分别总结正面、负面和中性评价的核心内容。

【正面评价 ({len(positive_posts)} 篇)】:
{pos_titles}

【负面评价 ({len(negative_posts)} 篇)】:
{neg_titles}

【中性讨论 ({len(neutral_posts)} 篇)】:
{neu_titles}

重要要求:
- 如果帖子中提到了其他竞品加速器或 VPN（如 ExitLag, LagoFast, NoPing, Hone.gg, wtfast, Mudfish, UU加速器, 迅游, 雷神 等），必须在总结中写出具体的竞品名称。
- 如果有用户在对比 {brand_name} 和其他竞品，请在总结中明确指出对比对象和结论。

请严格按以下格式输出（纯文本，禁止 Markdown，每项 1 句话，无内容则写"暂无"）:
正面评价: （总结核心正面反馈，提及具体竞品名称）
负面评价: （总结核心负面反馈，提及具体竞品名称）
中性讨论: （总结主要讨论方向，提及具体竞品名称）
涉及竞品: （列出帖子中出现的所有竞品/VPN 名称，用逗号分隔，无则写"无"）
商业洞察: （对加速器产品的 1 句建议）"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "你是品牌舆情分析师，输出简洁中文。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        ai_text = str(response.choices[0].message.content).strip()

        # 在 AI 总结后附上各类代表性帖子链接
        link_lines = []
        if positive_posts:
            links = _extract_top_links(positive_posts)
            link_lines.append(f"正面来源: {'; '.join(links)}")
        if negative_posts:
            links = _extract_top_links(negative_posts)
            link_lines.append(f"负面来源: {'; '.join(links)}")
        if neutral_posts:
            links = _extract_top_links(neutral_posts, 1)
            link_lines.append(f"中性来源: {'; '.join(links)}")

        if link_lines:
            ai_text += '\n' + '\n'.join(link_lines)

        return ai_text

    except Exception as e:
        print(f"[Brand AI] 舆情总结失败: {e}")
        return ""

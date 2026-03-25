import os
from openai import OpenAI

# ==========================================
# 品牌舆情 AI 总结
# ==========================================
# 调用通义千问对各地区品牌舆情进行分类总结：
# - 正面评价：总结核心正面反馈
# - 负面评价：总结核心负面反馈
# - 中性评价：总结主要讨论方向
# ==========================================

QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
qwen_client = OpenAI(
    api_key=QWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
) if QWEN_API_KEY else None


def summarize_sentiment(brand_name, region_name, positive_posts, negative_posts, neutral_posts):
    """
    对品牌舆情进行 AI 分类总结。

    :param brand_name: 品牌名
    :param region_name: 地区名
    :param positive_posts: 正面帖子列表 [{'title': ..., 'text': ...}, ...]
    :param negative_posts: 负面帖子列表
    :param neutral_posts: 中性帖子列表
    :return: 中文总结字符串
    """
    if not qwen_client:
        return ""

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

请严格按以下格式输出（纯文本，禁止 Markdown，每项 1 句话，无内容则写"暂无"）:
正面评价: （总结核心正面反馈）
负面评价: （总结核心负面反馈）
中性讨论: （总结主要讨论方向）
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
        return str(response.choices[0].message.content).strip()
    except Exception as e:
        print(f"[Brand AI] 舆情总结失败: {e}")
        return ""

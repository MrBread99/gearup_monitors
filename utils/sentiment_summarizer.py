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

    if not qwen_client:
        # AI 不可用，只返回帖子数量和链接
        links = [f"{p.get('title', '')[:40]} ({p.get('url', '')})" for p in unique_posts[:3] if p.get('url')]
        return f"共 {len(unique_posts)} 篇讨论。代表帖子: {'; '.join(links)}" if links else ""

    # 构建带编号和链接的帖子列表（最多 15 条给 AI）
    post_lines = []
    for i, p in enumerate(unique_posts[:15], 1):
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

        # 从 AI 输出中提取引用的帖子编号，附上对应链接
        import re
        referenced_ids = set(int(x) for x in re.findall(r'\[(\d+)\]', ai_text))

        if referenced_ids:
            link_lines = []
            for idx in sorted(referenced_ids):
                if 1 <= idx <= len(unique_posts):
                    p = unique_posts[idx - 1]
                    url = p.get('url', '')
                    title = p.get('title', '')[:50]
                    if url:
                        link_lines.append(f"[{idx}] {title} ({url})")
            if link_lines:
                ai_text += '\n来源链接:\n' + '\n'.join(link_lines)

        return ai_text

    except Exception as e:
        print(f"[Brand AI] 舆情总结失败: {e}")
        return ""

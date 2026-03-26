import os
from datetime import datetime, timezone, timedelta

# ==========================================
# 品牌舆情报告文件生成
# ==========================================
# 每个 brand_monitor 脚本运行时追加自己的 section 到报告文件，
# 最后由 GitHub Actions workflow 统一 push 到仓库。
# 报警中只附 GitHub 链接，避免报警文案过长。
# ==========================================

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')
REPORT_FILE = os.path.join(REPORT_DIR, 'brand_report_latest.md')

GITHUB_REPORT_URL = 'https://github.com/MrBread99/gearup_monitors/blob/main/reports/brand_report_latest.md'


def init_report():
    """初始化报告文件（写入头部，清空旧内容）"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    beijing_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f'# 品牌舆情监控详细报告\n\n')
        f.write(f'> 生成时间: {beijing_time} (UTC+8)\n')
        f.write(f'> 本报告每 24 小时更新一次\n\n')
        f.write(f'---\n\n')


def add_report_section(region_name, brand_name, positive_posts, negative_posts, neutral_posts, ai_summary=''):
    """
    追加一个地区的舆情详情到报告文件（直接写磁盘，跨进程安全）。
    """
    os.makedirs(REPORT_DIR, exist_ok=True)

    # 如果文件不存在，先初始化
    if not os.path.exists(REPORT_FILE):
        init_report()

    lines = []
    lines.append(f'## {region_name} - {brand_name}\n')

    if ai_summary:
        lines.append(f'### AI 分析\n```\n{ai_summary}\n```\n')

    for label, posts in [('正面评价', positive_posts), ('负面评价', negative_posts), ('中性讨论', neutral_posts)]:
        lines.append(f'### {label} ({len(posts)} 篇)\n')
        if posts:
            for p in posts[:5]:
                title = p.get('title', '')[:100]
                url = p.get('url', '')
                source = p.get('source', '')
                if url:
                    lines.append(f'- {title} - [{source}]({url})\n')
                else:
                    lines.append(f'- {title}\n')
        else:
            lines.append('- 暂无\n')
        lines.append('\n')

    lines.append('---\n\n')

    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        f.writelines(lines)


def get_report_url():
    return GITHUB_REPORT_URL

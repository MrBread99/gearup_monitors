"""
品牌舆情聚合入口 — 每 24 小时运行一次
将全部 9 个地区的品牌舆情监控结果合并为一条 POPO 消息发出。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import send_popo_alert, flush_scrape_block_alerts, POPO_WEBHOOK_URL
from utils.brand_report import init_report


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    print("=" * 50)
    print("品牌舆情聚合监控 (每24小时)")
    print("=" * 50)

    # 初始化本次报告文件
    init_report()

    all_issues = []

    # --- 1. Reddit 全站舆情 ---
    try:
        from brand_monitor.gearup_reddit import check_gearup_reddit
        results = check_gearup_reddit()
        print(f"[Reddit] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[Reddit] 执行失败: {e}")

    # --- 2. YouTube 舆情 ---
    try:
        from brand_monitor.gearup_youtube import check_gearup_youtube
        results = check_gearup_youtube()
        print(f"[YouTube] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[YouTube] 执行失败: {e}")

    # --- 3. Trustpilot 评分 ---
    try:
        from brand_monitor.trustpilot_monitor import check_trustpilot
        results = check_trustpilot()
        print(f"[Trustpilot] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[Trustpilot] 执行失败: {e}")

    # --- 4. 台湾舆情 ---
    try:
        from brand_monitor.taiwan_monitor import check_taiwan_brand
        results = check_taiwan_brand()
        print(f"[台湾] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[台湾] 执行失败: {e}")

    # --- 5. 韩国舆情 ---
    try:
        from brand_monitor.korea_monitor import check_korea_brand
        results = check_korea_brand()
        print(f"[韩国] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[韩国] 执行失败: {e}")

    # --- 6. 俄罗斯舆情 ---
    try:
        from brand_monitor.russia_monitor import check_russia_brand
        results = check_russia_brand()
        print(f"[俄罗斯] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[俄罗斯] 执行失败: {e}")

    # --- 7. 中东舆情 ---
    try:
        from brand_monitor.mideast_monitor import check_mideast_brand
        results = check_mideast_brand()
        print(f"[中东] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[中东] 执行失败: {e}")

    # --- 8. 东南亚舆情 ---
    try:
        from brand_monitor.southeast_asia_monitor import check_sea_brand
        results = check_sea_brand()
        print(f"[东南亚] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[东南亚] 执行失败: {e}")

    # --- 9. 日本舆情 ---
    try:
        from brand_monitor.japan_monitor import check_japan_brand
        results = check_japan_brand()
        print(f"[日本] {len(results)} 条舆情")
        all_issues.extend(results)
    except Exception as e:
        print(f"[日本] 执行失败: {e}")

    print(f"\n汇总: 共 {len(all_issues)} 条品牌舆情。")

    # 所有结果合并为一条 POPO 消息
    if all_issues:
        send_popo_alert(POPO_WEBHOOK_URL, all_issues)
    else:
        print("过去 24 小时内无品牌舆情异常，静默退出。")

    # 数据源异常汇总（如有）
    flush_scrape_block_alerts(POPO_WEBHOOK_URL)


if __name__ == "__main__":
    main()

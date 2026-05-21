import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.notifier import (
    POPO_WEBHOOK_URL,
    flush_monitor_crash_alerts,
    flush_scrape_block_alerts,
    report_monitor_crash,
    report_scrape_block,
    send_popo_alert,
)


# ==========================================
# 全球重点地区法定节假日 / 长假 / 特殊假期监控
# ==========================================
# 监控目标：
# 1. 覆盖运营重点地区的法定节假日
# 2. 自动识别连续 3 天及以上长假 / 长周末
# 3. 对高价值特殊假期打标签，辅助提前排班、营销和节点容量准备
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Holiday-Monitor/1.0"
}

SNAPSHOT_FILE = os.environ.get(
    "HOLIDAY_MONITOR_SNAPSHOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "holiday_monitor_snapshot.json"),
)

LOOKAHEAD_DAYS = int(os.environ.get("HOLIDAY_LOOKAHEAD_DAYS", "45"))
ALERT_STAGES = {
    7: "T-7",
    3: "T-3",
    1: "T-1",
    0: "当天",
}

COUNTRIES = [
    {"name_zh": "俄罗斯", "name_en": "Russia", "code": "RU", "source": "nager"},
    {"name_zh": "越南", "name_en": "Vietnam", "code": "VN", "source": "nager"},
    {"name_zh": "台湾", "name_en": "Taiwan", "code": "TW", "source": "taiwan"},
    {"name_zh": "美国", "name_en": "United States", "code": "US", "source": "nager"},
    {"name_zh": "印度尼西亚", "name_en": "Indonesia", "code": "ID", "source": "nager"},
    {"name_zh": "韩国", "name_en": "South Korea", "code": "KR", "source": "nager"},
    {"name_zh": "菲律宾", "name_en": "Philippines", "code": "PH", "source": "nager"},
    {"name_zh": "巴西", "name_en": "Brazil", "code": "BR", "source": "nager"},
    {"name_zh": "日本", "name_en": "Japan", "code": "JP", "source": "nager"},
    {"name_zh": "澳大利亚", "name_en": "Australia", "code": "AU", "source": "nager"},
    {"name_zh": "加拿大", "name_en": "Canada", "code": "CA", "source": "nager"},
    {"name_zh": "墨西哥", "name_en": "Mexico", "code": "MX", "source": "nager"},
]

SPECIAL_KEYWORDS = {
    "RU": ["New Year", "Christmas", "Victory Day", "Russia Day"],
    "VN": ["Tet", "Lunar New Year", "Hung Kings", "Reunification", "National Day"],
    "TW": ["Chinese New Year", "Lunar New Year", "Dragon Boat", "Mid-Autumn", "National Day"],
    "US": ["Thanksgiving", "Christmas", "New Year's Day", "Independence Day", "Labor Day"],
    "ID": ["Eid", "Idul", "Lebaran", "Nyepi", "Vesak", "Christmas", "Independence Day"],
    "KR": ["Seollal", "Korean New Year", "Chuseok", "Liberation Day", "Christmas"],
    "PH": ["Holy Week", "Maundy", "Good Friday", "All Saints", "Christmas", "Rizal"],
    "BR": ["Carnival", "Good Friday", "Tiradentes", "Independence", "Christmas"],
    "JP": ["Golden Week", "Constitution", "Greenery", "Children's Day", "Marine Day", "Respect for the Aged"],
    "AU": ["Australia Day", "Anzac", "Good Friday", "Easter", "Christmas", "Boxing Day"],
    "CA": ["Canada Day", "Thanksgiving", "Remembrance", "Christmas", "Boxing Day"],
    "MX": ["Constitution", "Benito Juarez", "Independence", "Revolution", "Christmas"],
}

TAIWAN_FALLBACK_HOLIDAYS = {
    2026: [
        ("2026-01-01", "New Year's Day", "元旦"),
        ("2026-02-16", "Chinese New Year", "农历春节"),
        ("2026-02-17", "Chinese New Year", "农历春节"),
        ("2026-02-18", "Chinese New Year", "农历春节"),
        ("2026-02-19", "Chinese New Year", "农历春节"),
        ("2026-02-20", "Chinese New Year", "农历春节"),
        ("2026-02-27", "Peace Memorial Day", "和平纪念日"),
        ("2026-04-03", "Children's Day", "儿童节"),
        ("2026-04-06", "Tomb Sweeping Day", "清明节"),
        ("2026-05-01", "Labour Day", "劳动节"),
        ("2026-06-19", "Dragon Boat Festival", "端午节"),
        ("2026-09-25", "Mid-Autumn Festival", "中秋节"),
        ("2026-09-28", "Confucius' Birthday", "孔子诞辰纪念日"),
        ("2026-10-09", "National Day", "台湾双十节补假"),
        ("2026-10-26", "Retrocession Day", "台湾光复节补假"),
        ("2026-12-25", "Constitution Day", "行宪纪念日"),
    ],
}


def today_bj() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_snapshot(snapshot: dict) -> None:
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def fetch_nager_holidays(year: int, country_code: str) -> list[dict]:
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            report_scrape_block("nager_holiday_api", url, resp.status_code)
            return []
        holidays = []
        for item in resp.json():
            types = item.get("types") or []
            if item.get("counties"):
                continue
            if "Public" not in types and "Bank" not in types:
                continue
            holidays.append(
                {
                    "date": date.fromisoformat(item["date"]),
                    "name": item.get("name") or item.get("localName") or "Public holiday",
                    "local_name": item.get("localName") or item.get("name") or "",
                    "country_code": country_code,
                    "global": bool(item.get("global", False)),
                    "counties": item.get("counties") or [],
                    "types": types,
                    "source_name": "Nager.Date",
                    "source_url": url,
                }
            )
        return holidays
    except Exception as e:
        report_monitor_crash(f"Nager.Date {country_code} {year}", e)
        return []


def fetch_calendarific_taiwan(year: int) -> list[dict]:
    api_key = os.environ.get("CALENDARIFIC_API_KEY", "")
    if not api_key:
        return []

    url = "https://calendarific.com/api/v2/holidays"
    params = {
        "api_key": api_key,
        "country": "TW",
        "year": year,
        "type": "national",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if resp.status_code != 200:
            report_scrape_block("calendarific_holiday_api", resp.url, resp.status_code)
            return []
        data = resp.json().get("response", {}).get("holidays", [])
        holidays = []
        for item in data:
            iso_date = str(item.get("date", {}).get("iso", ""))[:10]
            if not iso_date:
                continue
            holidays.append(
                {
                    "date": date.fromisoformat(iso_date),
                    "name": item.get("name") or "Public holiday",
                    "local_name": item.get("name") or "",
                    "country_code": "TW",
                    "global": True,
                    "counties": [],
                    "types": item.get("type") or ["National"],
                    "source_name": "Calendarific",
                    "source_url": "https://calendarific.com/api-documentation",
                }
            )
        return holidays
    except Exception as e:
        report_monitor_crash(f"Calendarific TW {year}", e)
        return []


def taiwan_fallback_holidays(year: int) -> list[dict]:
    rows = TAIWAN_FALLBACK_HOLIDAYS.get(year, [])
    holidays = []
    for iso_date, name, local_name in rows:
        holidays.append(
            {
                "date": date.fromisoformat(iso_date),
                "name": name,
                "local_name": local_name,
                "country_code": "TW",
                "global": True,
                "counties": [],
                "types": ["Public"],
                "source_name": "Taiwan static fallback",
                "source_url": "https://www.dgpa.gov.tw/",
            }
        )
    return holidays


def fetch_country_holidays(country: dict, years: set[int]) -> list[dict]:
    holidays = []
    for year in sorted(years):
        if country["source"] == "taiwan":
            fetched = fetch_calendarific_taiwan(year)
            holidays.extend(fetched if fetched else taiwan_fallback_holidays(year))
        else:
            holidays.extend(fetch_nager_holidays(year, country["code"]))
    return holidays


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def classify_holiday(country_code: str, names: list[str], span_days: int) -> tuple[str, list[str]]:
    labels = ["法定节假日"]
    haystack = " | ".join(names).lower()
    for keyword in SPECIAL_KEYWORDS.get(country_code, []):
        if keyword.lower() in haystack:
            labels.append("特殊假期")
            break
    if span_days >= 3:
        labels.append("长假/长周末")
    return " / ".join(dict.fromkeys(labels)), labels


def build_holiday_windows(holidays: list[dict], window_start: date, window_end: date) -> list[dict]:
    holidays_by_date: dict[date, list[dict]] = {}
    for holiday in holidays:
        holidays_by_date.setdefault(holiday["date"], []).append(holiday)

    holiday_dates = set(holidays_by_date.keys())
    handled: set[tuple[date, date]] = set()
    windows = []

    for holiday_date in sorted(holiday_dates):
        cluster_start = holiday_date
        while (cluster_start - timedelta(days=1)) in holiday_dates:
            cluster_start -= timedelta(days=1)

        cluster_end = holiday_date
        while (cluster_end + timedelta(days=1)) in holiday_dates:
            cluster_end += timedelta(days=1)

        expanded_start = cluster_start
        while is_weekend(expanded_start - timedelta(days=1)) or (expanded_start - timedelta(days=1)) in holiday_dates:
            expanded_start -= timedelta(days=1)

        expanded_end = cluster_end
        while is_weekend(expanded_end + timedelta(days=1)) or (expanded_end + timedelta(days=1)) in holiday_dates:
            expanded_end += timedelta(days=1)

        expanded_span = (expanded_end - expanded_start).days + 1
        if expanded_span >= 3:
            start, end = expanded_start, expanded_end
        else:
            start, end = cluster_start, cluster_end

        key = (start, end)
        if key in handled:
            continue
        handled.add(key)

        if end < window_start or start > window_end:
            continue

        window_holidays = []
        cursor = start
        while cursor <= end:
            window_holidays.extend(holidays_by_date.get(cursor, []))
            cursor += timedelta(days=1)

        if not window_holidays:
            continue

        names = []
        holiday_types = set()
        counties = set()
        global_flags = []
        source_name = window_holidays[0].get("source_name", "Holiday API")
        source_url = window_holidays[0].get("source_url", "")
        for item in window_holidays:
            display_name = item["name"]
            if item.get("local_name") and item["local_name"] != item["name"]:
                display_name = f"{item['name']} / {item['local_name']}"
            if display_name not in names:
                names.append(display_name)
            holiday_types.update(item.get("types") or [])
            counties.update(item.get("counties") or [])
            global_flags.append(bool(item.get("global", False)))

        windows.append(
            {
                "start": start,
                "end": end,
                "span_days": (end - start).days + 1,
                "holiday_dates": sorted({item["date"] for item in window_holidays}),
                "names": names,
                "types": sorted(holiday_types),
                "counties": sorted(counties),
                "is_global": all(global_flags) if global_flags else False,
                "source_name": source_name,
                "source_url": source_url,
            }
        )

    return sorted(windows, key=lambda item: (item["start"], item["end"], item["names"]))


def format_date_range(start: date, end: date) -> str:
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()} - {end.isoformat()}"


def describe_scope(window: dict) -> str:
    counties = window.get("counties") or []
    holiday_types = set(window.get("types") or [])

    if counties:
        return f"地区性假期（{', '.join(counties[:3])}{' 等' if len(counties) > 3 else ''}）"
    if "Public" in holiday_types or "National" in holiday_types:
        return "全国性公共假期"
    if "Bank" in holiday_types:
        return "银行/金融机构假期"
    if "School" in holiday_types:
        return "学校假期"
    if "Authorities" in holiday_types:
        return "政府机构假期"
    if "Optional" in holiday_types:
        return "可选假期"
    if window.get("is_global"):
        return "全国性假期"
    return "范围未明确"


def build_issue(country: dict, window: dict, stage: str, days_until: int) -> dict:
    names = "、".join(window["names"][:4])
    if len(window["names"]) > 4:
        names += f" 等 {len(window['names'])} 个假期"

    issue = (
        f"假期: {names}，{describe_scope(window)}\n"
        f"时间: {format_date_range(window['start'], window['end'])}"
        f"（{window['span_days']} 天）"
    )

    return {
        "game": "地区节假日监控",
        "region": country["name_zh"],
        "country": country["code"],
        "issue": issue,
        "alert_type": "holiday_monitor",
        "source_name": window["source_name"],
        "source_url": window["source_url"],
        "sort_key": (days_until, country["name_zh"], window["start"].isoformat()),
    }


def filter_new_alerts(issues: list[dict]) -> list[dict]:
    snapshot = load_snapshot()
    alerted = set(snapshot.get("alerted_holidays", []))
    fresh = []

    for issue in issues:
        window_key = issue.pop("_dedup_key")
        if window_key in alerted:
            continue
        alerted.add(window_key)
        fresh.append(issue)

    snapshot["alerted_holidays"] = list(alerted)[-1000:]
    snapshot["last_run_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_snapshot(snapshot)
    return fresh


def check_holidays() -> list[dict]:
    start = today_bj()
    end = start + timedelta(days=LOOKAHEAD_DAYS)
    years = {start.year, end.year}
    candidates = []

    for country in COUNTRIES:
        print(f"正在检测 {country['name_zh']} 节假日...")
        holidays = fetch_country_holidays(country, years)
        windows = build_holiday_windows(holidays, start, end)

        for window in windows:
            days_until = (window["start"] - start).days
            if days_until not in ALERT_STAGES:
                continue

            stage = ALERT_STAGES[days_until]
            issue = build_issue(country, window, stage, days_until)
            name_key = "|".join(window["names"])[:120]
            issue["_dedup_key"] = (
                f"{country['code']}|{window['start'].isoformat()}|"
                f"{window['end'].isoformat()}|{stage}|{name_key}"
            )
            candidates.append(issue)

    candidates.sort(key=lambda item: item.get("sort_key", (99, "", "")))
    for item in candidates:
        item.pop("sort_key", None)
    return filter_new_alerts(candidates)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    try:
        print("Testing Holiday Monitor...")
        results = check_holidays()
        if results:
            for result in results:
                print(f"[{result['region']}] {result['issue']}")
            send_popo_alert(POPO_WEBHOOK_URL, results)
        else:
            print("近期无需要发送的地区节假日预警。")
    except Exception as e:
        print(f"[HolidayMonitor] 顶层异常: {e}")
        import traceback

        traceback.print_exc()
        report_monitor_crash("holiday_monitor.py 顶层", e)
        flush_monitor_crash_alerts(POPO_WEBHOOK_URL)
    finally:
        flush_scrape_block_alerts(POPO_WEBHOOK_URL)

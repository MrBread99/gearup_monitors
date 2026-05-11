# GearUP Monitors - 监控脚本总览 (v4.5.0)

> **当前版本**: v4.5.0 | **最后更新**: 2026-04-22
>
> 本文档是供 AI Agent 快速上手的**唯一参考**，描述当前代码的真实状态。
>
> **修改游戏配置的唯一入口**: `game_monitor/game_registry.py`（56 款游戏，新增/修改/删除游戏只改这一个文件）

---

## 项目结构

```
gearup_monitors/
│
├── game_monitor/
│   ├── game_registry.py             # ★ 唯一游戏配置源（56 款游戏）
│   │                                #   字段：steam_appid / subreddit / vk_group / itsd_slug /
│   │                                #         tw_bsn / jp_search / kr_dc / kr_dc_type
│   ├── monitor.py                   # 主入口：56 款游戏 × 8 渠道，逐游戏 try/except 防级联失败
│   ├── steam_osint.py               # Steam 近期差评（9 语种关键词）
│   ├── apac_osint.py                # 亚太社区（巴哈姆特 / DC Inside Playwright+requests 双层降级）
│   ├── cis_osint.py                 # 俄罗斯/CIS（VK + detector404.ru）
│   │                                #   DETECTOR404_MAP: 46 游戏 + 9 平台 = 55 条
│   │                                #   DETECTOR404_PLATFORMS: 平台名称集合（防重复检测用）
│   │                                #   get_detector404_game_only_names(): 仅返回游戏条目
│   │                                #   批量请求间隔 4-7s；429 内联重试 + 连续 2 次 429 冷却后提前终止
│   ├── downdetector_osint.py        # 全球故障聚合（IsTheServiceDown）
│   ├── platform_status_monitor.py   # 14 个平台/通讯工具状态（独占 detector404 平台检测）
│   ├── game_calendar_monitor.py     # 新游上线 + 热游更新（官方 API + Reddit listing 兜底 + AI 摘要）
│   │                                #   跨运行去重（snapshot key，最多 1000 条）
│   │                                #   每个数据源限 2 条最优结果（PER_SOURCE_ALERT_LIMIT）
│   │                                #   Steam News 连续 5 次 403 后静默 3 天
│   └── russia_event_monitor.py      # 俄罗斯大型活动日历 + 网络管控预警（AI 不可用时仍报警）
│
├── competitor_radar/
│   ├── run_all.py                   # ★ 聚合入口（Discord 24h + 定价 + 博客 + LinkedIn），合并为一条消息；含 Discord 健康状态
│   ├── discord_listener.py          # 竞品 Discord 公告 + Qwen AI 翻译提炼
│   ├── exitlag_pricing.py           # 多竞品定价追踪（Playwright + stealth 三层降级 + 跨运行健康状态）
│   │                                #   降级顺序：Playwright headless Chromium > cloudscraper 单例 > requests
│   │                                #   403 时销毁整个 browser context（含 cookie/storage）并重建
│   │                                #   Chromium 启动参数含 --disable-blink-features=AutomationControlled
│   ├── competitor_blog_monitor.py   # 竞品博客动态监控 + Qwen AI 中文摘要 + 跨运行健康状态
│                                    #   ExitLag: WP REST API → Playwright + stealth → requests
│                                    #   LagoFast: requests + __NEXT_DATA__ JSON → Playwright
│                                    #   快照去重（slug），首次运行保存基线不报警
│   └── linkedin_monitor.py          # ExitLag LinkedIn 公司动态监控（公开 Updates HTML + Playwright fallback + 跨运行健康状态）
│
├── brand_monitor/
│   ├── run_all.py                   # ★ 聚合入口（9 地区舆情），合并为一条消息；无结果时发心跳
│   ├── trustpilot_monitor.py        # ⚠️ 暂时禁用（Cloudflare 封锁 GitHub Actions IP，等 Business API key）
│   ├── gearup_reddit.py             # Reddit 全站舆情
│   ├── gearup_youtube.py            # YouTube 多语言舆情（每天 1 次）
│   ├── taiwan_monitor.py            # 巴哈姆特 / PTT
│   ├── japan_monitor.py             # 5ch / Google JP
│   ├── korea_monitor.py             # Naver Search API / DC Inside（Playwright+requests 双层降级）
│   ├── russia_monitor.py            # VK / Google 俄语搜索（Otzovik 已废弃，CAPTCHA）
│   ├── mideast_monitor.py           # Reddit MENA / Google AR
│   └── southeast_asia_monitor.py    # Tinhte / Reddit SEA / Google 多语
│
├── utils/
│   ├── notifier.py                  # 通知发送（6 种标题分组 + 超 4000 字自动分割 + 3 次重试 + UTC+8）
│   │                                #   反爬状态码集合: (403, 429, 507)
│   │                                #   专属 _SCRAPE_ADVICE 优先于泛化状态码逻辑（但 404/5xx 优先于自定义建议）
│   │                                #   cloudflare_pricing 403 需 ≥2 次才发 POPO（min_notify_count: 2）
│   │                                #   send_system_heartbeat(): 心跳通知
│   │                                #   report_monitor_crash() / flush_monitor_crash_alerts(): 内部崩溃感知
│   ├── reddit_client.py             # Reddit 共享客户端（OAuth2 可选 + 匿名 4s 限流 + 429 重试）
│   │                                #   熔断器: 连续 3 次 403 后停止本轮所有 Reddit 调用
│   │                                #   _last_request_meta: 请求元数据追踪（mode/token_state/status_code）
│   ├── google_client.py             # Google 搜索共享客户端（5-8s 随机延迟 + 多语言含 ru）
│   ├── playwright_client.py         # ★ 共享 Playwright 无头浏览器（懒初始化/context 轮换/stealth）
│   │                                #   pw_fetch(url) → (html, status); pw_close() 清理
│   │                                #   Trustpilot / DC Inside(游戏+品牌) / exitlag_pricing 共用
│   ├── alert_dedup.py               # 🔴 报警合并（游戏名+地区）+ 跨运行去重
│   ├── brand_report.py              # 品牌报告生成（锚点深链接 + AI 引用来源列表）
│   └── sentiment_summarizer.py      # AI 情感分析聚合（传引用帖子到报告）
│
└── .github/workflows/
    ├── monitor.yml                  # 每 2 小时：游戏故障 + 平台 + 俄罗斯预警 + 新游更新
    │                                #   continue-on-error: true + 步骤 ID + 运行摘要
    │                                #   pip install -r game_monitor/requirements-ci.txt
    ├── brand_monitor.yml            # 每天 UTC 00:00（北京 08:00）：品牌舆情聚合 + 运行摘要
    └── competitor_radar.yml         # 每天 UTC 01:00（北京 09:00）：竞品情报聚合 + 运行摘要
                                     #   pip install -r competitor_radar/requirements-ci.txt
                                     #   包含 playwright install chromium 步骤
```

---

## 一、游戏网络故障监控 (`monitor.py`)

| 维度 | 数据 |
|------|------|
| 监控游戏 | **56 款**（见 `game_registry.py` 完整列表） |
| 监控渠道 | **8 个**：Reddit OSINT、Steam 差评、巴哈姆特、DC Inside、VK、detector404.ru、IsTheServiceDown、Epic 官方 API（Fortnite 专用） |
| 关键词语种 | **9 种**：英/繁中/日/韩/俄/阿拉伯/越南/菲律宾/印尼 |
| 报警标签 | 🟢 加速器可解决 / 🔴 加速器无效 / 🟡 待确认 |
| AI 能力 | Qwen 总结玩家反馈核心内容 |
| 🔴 报警处理 | 合并为一条摘要（保留游戏名+地区），跨运行去重（报过不再报） |
| detector404.ru | **仅检测游戏**（不含平台），46 个游戏条目；平台由 `platform_status_monitor.py` 独占负责 |
| 运行频率 | 每 2 小时 |
| 容错机制 | 逐游戏 `try/except`（单游戏异常不中断整体）+ 顶层 `try/except` + `continue-on-error: true` |

---

## 二、平台与通讯工具状态 (`platform_status_monitor.py`)

| # | 平台 | 类型 | 数据源 | 重点关注 |
|---|------|------|--------|---------|
| 1 | Discord | 通讯 | 官方 Status API（15 区域 Voice）+ detector404.ru | 俄罗斯区域特殊标注 |
| 2 | Telegram | 通讯 | Reddit（英文+俄语）+ detector404.ru | 俄罗斯/CIS 封锁 |
| 3 | WhatsApp | 通讯 | Reddit（英文+俄语+阿拉伯语） | 中东 VoIP + 俄罗斯 |
| 4 | LINE | 通讯 | Reddit（日语+泰语） | 日本/泰国/台湾 |
| 5 | Steam | 游戏平台 | steamstat.us + Reddit + detector404.ru | 全球 + 俄罗斯 |
| 6 | Epic Games | 游戏平台 | 官方 Status API + detector404.ru | 全球 + 俄罗斯 |
| 7 | Battle.net | 游戏平台 | Reddit | OW2/CoD/WoW |
| 8 | Riot Games | 游戏平台 | 官方 CDN Status API（7 区域） | Valorant/LOL 分区域 |
| 9 | EA App | 游戏平台 | Reddit | Apex/FIFA |
| 10 | Ubisoft Connect | 游戏平台 | Reddit + detector404.ru | R6 Siege |
| 11 | FACEIT | 对战平台 | incident.io API + Reddit + detector404.ru | CS2 第三方对战 |
| 12 | Xbox Live | 主机 | Reddit + detector404.ru | 主机联机 |
| 13 | PSN | 主机 | Reddit + detector404.ru | 主机联机 |
| 14 | Garena | 地区平台 | Reddit | 东南亚 LOL/Free Fire |

> **架构约束**: `platform_status_monitor.py` 是所有平台 detector404 检测的**唯一负责方**。
> `monitor.py` 调用 `check_detector404_batch(get_detector404_game_only_names())` 只扫游戏，
> 不得再传入平台名称，否则会产生重复报警。

---

## 三、新游上线 + 热游更新 (`game_calendar_monitor.py`)

### 非 Steam 游戏数据源（官方 API 优先，Reddit 兜底）

| 游戏 | 主数据源 | 检测函数 | 备注 |
|------|---------|---------|------|
| League of Legends | 官方 game-updates 页 | `check_official_page_updates()` | ISO 8601 时间戳 |
| Valorant | 官方 game-updates 页 | `check_official_page_updates()` | ISO 8601 时间戳 |
| Overwatch 2 | Blizzard 官方新闻 | `check_blizzard_updates()` | "Month DD, YYYY" 日期解析 |
| World of Warcraft | Blizzard 官方新闻 | `check_blizzard_updates()` | "Month DD, YYYY" 日期解析 |
| Genshin Impact (gid=2) | HoyoLab API | `check_hoyolab_updates()` | Unix 时间戳 JSON |
| Honkai Star Rail (gid=6) | HoyoLab API | `check_hoyolab_updates()` | Unix 时间戳 JSON |
| Zenless Zone Zero (gid=8) | HoyoLab API | `check_hoyolab_updates()` | Unix 时间戳 JSON |
| Fortnite / CoD / Wuthering Waves / Roblox / Aion 2 | Reddit listing API | `check_non_steam_updates()` | 客户端关键词过滤（title + selftext） |

### Steam 平台检测覆盖

| 检测内容 | 数据源 | 报警标题 |
|---------|--------|---------|
| 已追踪游戏大版本更新/预告 | Steam News API（有 AppID 的游戏） | 【热游版本更新预告】 |
| Steam 热门新游上线 | Steam Featured API（Top Sellers + New Releases） | 【新游上线预告】 |
| Steam 即将发售联机热门 | Steam Coming Soon API | 【新游上线预告】 |
| Epic 新游/免费游戏赠送 | Reddit（3 个子版块） | 【新游上线预告】 |
| PlayStation 新游 | Reddit（PS5/PS4） | 【新游上线预告】 |
| Xbox / Game Pass 上新 | Reddit | 【新游上线预告】 |
| Battle.net 游戏更新 | Reddit（OW2/WoW/D4/炉石） | 【热游版本更新预告】 |

**新游上线报警字段**: 上线时间 → 热度预估(0-100) → 加速需求(1-5★) → 头部地区 TOP5 → AI 玩法介绍，按热度从高到低排序。

**热游更新报警字段**: 加速需求(1-5★) → AI 更新时间/内容摘要/加速器影响，按综合优先级排序。

---

## 四、俄罗斯大型活动预警 (`russia_event_monitor.py`)

| 检测内容 | 数据源 | 预警时间 |
|---------|--------|---------|
| SPIEF/EEF/BRICS/SCO 等 8 个已知年度活动 | 硬编码日历 | 提前 14 天 |
| 活动进行中（高风险） | 硬编码日历 | 实时 |
| 临时峰会/外交访问 | Reddit 搜索 | 实时 |
| Roskomnadzor VPN 封锁动态 | Reddit 搜索 + AI 风险评估 | 实时 |

风险等级：🔴 极高 / 🟠 高 / 🟡 中等 / 🟢 低。每个活动只报一次（快照去重）。

---

## 五、竞品情报 (`competitor_radar/`)

| 模块 | 功能 | 覆盖 |
|------|------|------|
| `run_all.py` | 聚合 Discord + 定价 + 博客 + LinkedIn，**合并一条消息**发出；无结果时发心跳；Discord 连续失败到阈值才报异常，恢复时提示一次 | 每天北京时间 09:00 |
| `discord_listener.py` | Discord 公告监听 + Qwen AI 翻译提炼 | 竞品 Discord 频道 |
| `exitlag_pricing.py` | 多竞品定价变动追踪，Playwright + stealth 绕 Cloudflare；所有地区连续失败到阈值才报异常，恢复时提示一次 | ExitLag 9 地区 + LagoFast 10 地区 = 19 个 |
| `competitor_blog_monitor.py` | 竞品博客新文章监控 + Qwen AI 中文摘要 | ExitLag 博客 + LagoFast 博客 |
| `linkedin_monitor.py` | ExitLag LinkedIn 公司动态监控，发现新动态后并入竞品情报警报；连续失败到阈值才报数据源异常，恢复时提示一次 | ExitLag 公司页 |

**定价抓取降级链**: Playwright headless Chromium (playwright-stealth) → cloudscraper 单例会话复用 → requests。Playwright 403 时销毁整个 browser context（含 cookie/storage）并重建重试；所有层级均尝试后统一判断是否报警（单次 403 仅日志，≥2 次才发 POPO）。

**定价健康状态**: 当前启用的 LagoFast 定价监控在所有地区都无法解析到价格时才累计失败；连续 3 次失败进入数据源异常，同一故障期只报一次，恢复后提示一次。

多竞品架构：`COMPETITORS` 字典配置，新增竞品只需加一条配置。

**博客监控抓取策略**:
- ExitLag（WordPress）: WP REST API 优先（结构化 JSON + 全文内容）→ Playwright + stealth → requests HTML 解析
- LagoFast（Next.js）: requests + `__NEXT_DATA__` JSON 解析 → DOM 解析 fallback → Playwright
- 快照去重：以文章 slug 为 key，跨运行持久化；首次运行保存基线，不生成报警
- 新文章摘要过短时自动抓取全文页面，提供充分上下文给 AI
- 数据源健康状态：LagoFast 博客连续失败 3 次才进入数据源异常汇总，同一故障期只报一次，恢复后提示一次

---

## 六、品牌舆情 (`brand_monitor/`)

| 渠道 | 模块 | 覆盖地区 | 语言 | 备注 |
|------|------|---------|------|------|
| Trustpilot | `trustpilot_monitor.py` | 全球 | 英文 | GearUP + 5 竞品；Playwright 绕 Cloudflare；仅报**评分变动**和 **1 星差评占比上升** |
| Reddit | `gearup_reddit.py` | 全球 | 英文 | |
| YouTube | `gearup_youtube.py` | 全球 | 8 语 | 每天 1 次（配额限制） |
| 巴哈姆特 / PTT | `taiwan_monitor.py` | 台湾 | 繁中 | |
| 5ch / Google JP | `japan_monitor.py` | 日本 | 日语 | |
| Naver Search API / DC Inside | `korea_monitor.py` | 韩国 | 韩语 | DC Inside 用 Playwright 绕 Cloudflare；需配置 `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` |
| VK / Google 俄语搜索 | `russia_monitor.py` | 俄罗斯/CIS | 俄语 | Otzovik 已废弃（全站 CAPTCHA），改用 Google RU 间接索引 |
| Reddit MENA / Google AR | `mideast_monitor.py` | 中东 | 阿拉伯语 | |
| Tinhte / Reddit SEA / Google 多语 | `southeast_asia_monitor.py` | 东南亚 | 越/菲/印尼/泰 | |

所有地区通过 `run_all.py` 聚合为**一条消息**，每天北京时间 08:00 发送。

---

## 七、基础设施

| 组件 | 功能 | 关键细节 |
|------|------|---------|
| `utils/notifier.py` | 6 种报警标题分组 + 超 4000 字自动分割 + 3 次重试指数退避 + UTC+8 + 心跳 | 反爬码 (403/429/507)；404/5xx 优先于自定义建议；`min_notify_count` 降噪 |
| `utils/reddit_client.py` | OAuth2 可选（600 req/min）+ 2s 限流 + 429 自动重试 + 请求元数据追踪 | `get_last_reddit_request_meta()` 返回 mode/token_state/status_code |
| `utils/google_client.py` | 5-8s 随机延迟 + 多语言 Accept-Language（含 ru） | CAPTCHA 三重检测 |
| `utils/alert_dedup.py` | 🔴 报警合并（保留游戏名+地区）+ 跨运行去重 | 仅作用于 🔴 类型 |
| `game_monitor/game_registry.py` | 56 款游戏统一配置 | 唯一修改游戏配置的文件 |
| GitHub Actions cache | **7** 个快照文件持久化（日历/平台事件/无效报警去重/俄罗斯活动/定价/评分/博客） | 去重跨运行生效的前提 |
| `requirements-ci.txt` | `game_monitor/` 和 `competitor_radar/` 各有独立的 pinned 依赖文件 | workflow 使用 `pip install -r` |

---

## 八、GitHub Actions 工作流

| 工作流 | 触发时间 | 执行内容 | 特殊步骤 |
|--------|---------|---------|---------|
| `monitor.yml` | 每 2 小时 | monitor.py + russia_event_monitor.py + game_calendar_monitor.py | `continue-on-error: true` + step ID + 运行摘要 |
| `brand_monitor.yml` | 每天北京 08:00 | `brand_monitor/run_all.py`，自动 push 舆情报告到 `reports/` | `permissions: contents: write` + 运行摘要 |
| `competitor_radar.yml` | 每天北京 09:00 | `competitor_radar/run_all.py` | `playwright install chromium` + `requirements-ci.txt` + 运行摘要 |
|                        |                 | Discord + 定价 + 博客 + LinkedIn 监控 | 博客/LinkedIn/健康状态快照文件加入 cache |

---

## 九、GitHub Secrets 配置

| Secret | 必填 | 用途 |
|--------|------|------|
| `POPO_WEBHOOK_URL` | ✅ | 所有报警发送目标（网易 POPO 机器人） |
| `QWEN_API_KEY` | ✅ | Qwen AI 摘要（玩家反馈/更新内容/加速需求/新游介绍/竞品公告翻译/俄罗斯风险评估） |
| `REDDIT_CLIENT_ID` | 推荐 | Reddit OAuth2（未配置时降级为匿名，4s 间隔 + 熔断器保护） |
| `REDDIT_CLIENT_SECRET` | 推荐 | Reddit OAuth2（当前无法申请，匿名模式运行中） |
| `YOUTUBE_API_KEY` | ✅ | YouTube Data API v3（YouTube 舆情，未配置时跳过） |
| `DISCORD_BOT_TOKEN` | ✅ | 竞品 Discord 公告监听 |
| `TARGET_CHANNEL_ID` | ✅ | 竞品 Discord 目标频道 ID |
| `NAVER_CLIENT_ID` | 推荐 | Naver Search Open API（未配置时跳过韩国 Naver 检测） |
| `NAVER_CLIENT_SECRET` | 推荐 | Naver Search Open API |

---

## 十、已知架构约束 & 注意事项

1. **手游不监控** — 用户明确要求只监控 PC 端游戏
2. **detector404 分工** — `monitor.py` 只传游戏名，`platform_status_monitor.py` 只传平台名，不得交叉，否则产生重复报警
3. **Otzovik 废弃** — `russia_monitor.py` 中 `search_otzovik()` 已替换为 `search_google_ru()`，不要恢复
4. **竞品定价 Cloudflare** — `exitlag_pricing.py` 必须用 Playwright + stealth 作为首选；403 时销毁整个 browser context 并重建（不是仅新建 page）；cloudscraper 和 requests 作为后续 fallback 全链路尝试
5. **快照持久化** — 本地运行快照文件不提交（已加入 `.gitignore`）；GitHub Actions 通过 `actions/cache` 持久化，`restore-keys` 保证跨 run 读到历史数据
6. **报警时间** — 所有报警时间统一 UTC+8，在 `notifier.py` 内处理，下游模块不需要转换时区
7. **级联失败防护** — `monitor.py` 中每款游戏的检测已被 `try/except` 包裹；新增检测模块时应遵循相同模式
8. **Trustpilot 暂时禁用** — Cloudflare 封锁 GitHub Actions IP，Playwright + stealth 也无法通过。`run_all.py` 中调用已注释，等 Trustpilot Business API key 再恢复
9. **日历报警去重** — `game_calendar_monitor.py` 通过 snapshot key 跨运行去重，同一更新只报一次；快照丢失（cache miss）时会重新报
10. **detector404 限流** — 批量请求间隔 4-7s，连续 2 次 429 后冷却并提前终止批次；部分游戏可能在某次运行中未被检查
11. **Steam News 403 静默** — 同一 AppID 连续 **5** 次 Steam News 403 后静默 **3** 天
12. **Reddit listing API** — 日历监控的 Reddit 调用已从 search API 改为 listing API（`/new.json`、`/hot.json`）+ 客户端关键词过滤
13. **Reddit 匿名模式** — 无法申请 OAuth 凭证（Reddit 政策限制），当前以匿名模式运行（4s 间隔 + 熔断器）；`missing_credentials` 不再发报警
14. **品牌舆情搜索窗口** — Reddit `t=week`、YouTube 3 天、Google `tbs=qdr:w`，所有搜索限一周内，避免每日重复报警
15. **内部崩溃感知** — 所有 try/except 捕获的异常通过 `report_monitor_crash()` 登记，脚本末尾由 `flush_monitor_crash_alerts()` 统一发 POPO。新增模块时应遵循此模式
16. **品牌报告格式** — `brand_report.py` 只展示 AI 分析 + 引用来源，不展示关键词预分类结果（避免和 AI 分类矛盾）

---

## 十一、数字总结

| 维度 | 数量 |
|------|------|
| Python 脚本 | **30 个**（含 `playwright_client.py` + 2 个 `requirements-ci.txt`） |
| 监控游戏 | **56 款** |
| 游戏故障渠道 | **8 个** |
| 平台/通讯工具 | **14 个** |
| detector404 监控条目 | **55 条**（46 游戏 + 9 平台） |
| 品牌舆情渠道 | **8 个**（Trustpilot 暂时禁用） |
| 竞品定价地区 | **19 个** |
| 覆盖地区 | **8 个**（欧美/台湾/日本/韩国/俄罗斯-CIS/中东/东南亚/拉美部分） |
| 覆盖语言 | **9 种** |
| AI 接入点 | **7 个**（玩家反馈总结/更新摘要/加速需求/新游介绍/俄罗斯风险评估/竞品公告翻译/竞品博客摘要） |
| 快照文件 | **7 个**（跨运行持久化） |
| 运行频率 | 故障监控每 **2 小时**；品牌舆情/竞品情报每天 **1 次** |
| 报警标题 | **6 种**（商机雷达/新游上线/热游更新/平台状态/品牌舆情/竞品情报）+ 心跳 + 内部崩溃 |

---

## 十二、已知架构约束补充

17. **竞品博客监控反爬策略** — ExitLag 博客（WordPress + Cloudflare）优先使用 WP REST API（不触发 Cloudflare），失败时降级 Playwright + stealth，最后 requests 兜底。LagoFast 博客（Next.js SSR）优先通过 requests 抓取 `__NEXT_DATA__` JSON（服务端渲染的结构化数据），失败时尝试 DOM 解析和 Playwright
18. **博客快照首次运行** — `competitor_blog_monitor.py` 首次运行（快照中无对应竞品 key）仅保存当前文章列表为基线，不生成报警，避免首次部署时产生大量历史文章的误报

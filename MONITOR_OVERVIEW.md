# GearUP Monitors - 监控脚本总览 (v4.2.1)

> **当前版本**: v4.2.1 | **最后更新**: 2026-04-03
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
│   ├── apac_osint.py                # 亚太社区（巴哈姆特/DC Inside）
│   ├── cis_osint.py                 # 俄罗斯/CIS（VK + detector404.ru）
│   │                                #   DETECTOR404_MAP: 46 游戏 + 9 平台 = 55 条
│   │                                #   DETECTOR404_PLATFORMS: 平台名称集合（防重复检测用）
│   │                                #   get_detector404_game_only_names(): 仅返回游戏条目
│   ├── downdetector_osint.py        # 全球故障聚合（IsTheServiceDown）
│   ├── platform_status_monitor.py   # 14 个平台/通讯工具状态（独占 detector404 平台检测）
│   ├── game_calendar_monitor.py     # 新游上线 + 热游更新（官方 API + Reddit 兜底 + AI 摘要）
│   └── russia_event_monitor.py      # 俄罗斯大型活动日历 + 网络管控预警
│
├── competitor_radar/
│   ├── run_all.py                   # ★ 聚合入口（Discord 24h + 定价），合并为一条消息
│   ├── discord_listener.py          # 竞品 Discord 公告 + Qwen AI 翻译提炼
│   └── exitlag_pricing.py           # 多竞品定价追踪（Playwright + stealth 三层降级）
│                                    #   降级顺序：Playwright headless Chromium > cloudscraper 单例 > requests
│
├── brand_monitor/
│   ├── run_all.py                   # ★ 聚合入口（9 地区舆情），合并为一条消息
│   ├── trustpilot_monitor.py        # Trustpilot 评分（GearUP + 5 竞品）
│   ├── gearup_reddit.py             # Reddit 全站舆情
│   ├── gearup_youtube.py            # YouTube 多语言舆情（每天 1 次）
│   ├── taiwan_monitor.py            # 巴哈姆特 / PTT
│   ├── japan_monitor.py             # 5ch / Google JP
│   ├── korea_monitor.py             # Naver Search API / DC Inside
│   ├── russia_monitor.py            # VK / Google 俄语搜索（Otzovik 已废弃，CAPTCHA）
│   ├── mideast_monitor.py           # Reddit MENA / Google AR
│   └── southeast_asia_monitor.py    # Tinhte / Reddit SEA / Google 多语
│
├── utils/
│   ├── notifier.py                  # 通知发送（5 种标题分组 + 超 4000 字自动分割 + 3 次重试 + UTC+8）
│   │                                #   反爬状态码集合: (403, 429, 507)
│   │                                #   专属 _SCRAPE_ADVICE 优先于泛化状态码逻辑
│   ├── reddit_client.py             # Reddit 共享客户端（OAuth2 可选 + 2s 限流 + 429 重试）
│   ├── google_client.py             # Google 搜索共享客户端（5-8s 随机延迟 + 多语言含 ru）
│   └── alert_dedup.py               # 🔴 报警合并（游戏名+地区）+ 跨运行去重
│
└── .github/workflows/
    ├── monitor.yml                  # 每 2 小时：游戏故障 + 平台 + 俄罗斯预警 + 新游更新
    │                                #   continue-on-error: true（三个步骤均已设置）
    ├── brand_monitor.yml            # 每天 UTC 00:00（北京 08:00）：品牌舆情聚合
    └── competitor_radar.yml         # 每天 UTC 01:00（北京 09:00）：竞品情报聚合
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
| Fortnite / CoD / Wuthering Waves / Roblox / Aion 2 | Reddit | `check_non_steam_updates()` | 无可靠官方 API，继续用 Reddit |

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
| `run_all.py` | 聚合 Discord + 定价，**合并一条消息**发出 | 每天北京时间 09:00 |
| `discord_listener.py` | Discord 公告监听 + Qwen AI 翻译提炼 | 竞品 Discord 频道 |
| `exitlag_pricing.py` | 多竞品定价变动追踪，Playwright + stealth 绕 Cloudflare | ExitLag 9 地区 + LagoFast 10 地区 = 19 个 |

**定价抓取降级链**: Playwright headless Chromium (playwright-stealth) → cloudscraper 单例会话复用 → requests

多竞品架构：`COMPETITORS` 字典配置，新增竞品只需加一条配置。

---

## 六、品牌舆情 (`brand_monitor/`)

| 渠道 | 模块 | 覆盖地区 | 语言 | 备注 |
|------|------|---------|------|------|
| Trustpilot | `trustpilot_monitor.py` | 全球 | 英文 | 同时监控 GearUP + 5 竞品评分 |
| Reddit | `gearup_reddit.py` | 全球 | 英文 | |
| YouTube | `gearup_youtube.py` | 全球 | 8 语 | 每天 1 次（配额限制） |
| 巴哈姆特 / PTT | `taiwan_monitor.py` | 台湾 | 繁中 | |
| 5ch / Google JP | `japan_monitor.py` | 日本 | 日语 | |
| Naver Search API / DC Inside | `korea_monitor.py` | 韩国 | 韩语 | 需配置 `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` |
| VK / Google 俄语搜索 | `russia_monitor.py` | 俄罗斯/CIS | 俄语 | Otzovik 已废弃（全站 CAPTCHA），改用 Google RU 间接索引 |
| Reddit MENA / Google AR | `mideast_monitor.py` | 中东 | 阿拉伯语 | |
| Tinhte / Reddit SEA / Google 多语 | `southeast_asia_monitor.py` | 东南亚 | 越/菲/印尼/泰 | |

所有地区通过 `run_all.py` 聚合为**一条消息**，每天北京时间 08:00 发送。

---

## 七、基础设施

| 组件 | 功能 | 关键细节 |
|------|------|---------|
| `utils/notifier.py` | 5 种报警标题分组 + 超 4000 字自动分割 + 3 次重试指数退避 + UTC+8 | 反爬码 (403/429/507)；专属 `_SCRAPE_ADVICE` 优先 |
| `utils/reddit_client.py` | OAuth2 可选（600 req/min）+ 2s 限流 + 429 自动重试 | 全项目统一入口 |
| `utils/google_client.py` | 5-8s 随机延迟 + 多语言 Accept-Language（含 ru） | CAPTCHA 三重检测 |
| `utils/alert_dedup.py` | 🔴 报警合并（保留游戏名+地区）+ 跨运行去重 | 仅作用于 🔴 类型 |
| `game_monitor/game_registry.py` | 56 款游戏统一配置 | 唯一修改游戏配置的文件 |
| GitHub Actions cache | 6 个快照文件持久化（日历/平台事件/无效报警去重/俄罗斯活动/定价/评分） | 去重跨运行生效的前提 |

---

## 八、GitHub Actions 工作流

| 工作流 | 触发时间 | 执行内容 | 特殊步骤 |
|--------|---------|---------|---------|
| `monitor.yml` | 每 2 小时 | monitor.py + russia_event_monitor.py + game_calendar_monitor.py | `continue-on-error: true`（三步均设） |
| `brand_monitor.yml` | 每天北京 08:00 | `brand_monitor/run_all.py`，自动 push 舆情报告到 `reports/` | `permissions: contents: write` |
| `competitor_radar.yml` | 每天北京 09:00 | `competitor_radar/run_all.py` | `playwright install chromium` |

---

## 九、GitHub Secrets 配置

| Secret | 必填 | 用途 |
|--------|------|------|
| `POPO_WEBHOOK_URL` | ✅ | 所有报警发送目标（网易 POPO 机器人） |
| `QWEN_API_KEY` | ✅ | Qwen AI 摘要（玩家反馈/更新内容/加速需求/新游介绍/竞品公告翻译/俄罗斯风险评估） |
| `REDDIT_CLIENT_ID` | ✅ | Reddit OAuth2（未配置时自动降级为匿名，60 req/min） |
| `REDDIT_CLIENT_SECRET` | ✅ | Reddit OAuth2 |
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
4. **竞品定价 Cloudflare** — `exitlag_pricing.py` 必须用 Playwright + stealth 作为首选；cloudscraper 单例（`_cs_session`）和浏览器单例（`_pw_browser`）不得在每次请求时重新创建
5. **快照持久化** — 本地运行快照文件不提交；GitHub Actions 通过 `actions/cache` 持久化，`restore-keys` 保证跨 run 读到历史数据
6. **报警时间** — 所有报警时间统一 UTC+8，在 `notifier.py` 内处理，下游模块不需要转换时区
7. **级联失败防护** — `monitor.py` 中每款游戏的检测已被 `try/except` 包裹；新增检测模块时应遵循相同模式

---

## 十一、数字总结

| 维度 | 数量 |
|------|------|
| Python 脚本 | **26 个** |
| 监控游戏 | **56 款** |
| 游戏故障渠道 | **8 个** |
| 平台/通讯工具 | **14 个** |
| detector404 监控条目 | **55 条**（46 游戏 + 9 平台） |
| 品牌舆情渠道 | **9 个** |
| 竞品定价地区 | **19 个** |
| 覆盖地区 | **8 个**（欧美/台湾/日本/韩国/俄罗斯-CIS/中东/东南亚/拉美部分） |
| 覆盖语言 | **9 种** |
| AI 接入点 | **6 个**（玩家反馈总结/更新摘要/加速需求/新游介绍/俄罗斯风险评估/竞品公告翻译） |
| 快照文件 | **6 个**（跨运行持久化） |
| 运行频率 | 故障监控每 **2 小时**；品牌舆情/竞品情报每天 **1 次** |
| 报警标题 | **6 种**（商机雷达/新游上线/热游更新/平台状态/品牌舆情/竞品情报） |

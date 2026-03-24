# GearUP Monitors - 监控脚本总览

## 项目结构

```
gearup_monitors/ (v4.0.0)
│
├── game_monitor/                    # 游戏网络故障 + 平台状态 + 新游日历 + 俄罗斯预警
│   ├── game_registry.py             # 统一游戏配置（15 款游戏，改游戏只改这一个文件）
│   ├── monitor.py                   # 主入口：15 款游戏 × 8 渠道 + AI 玩家反馈总结
│   ├── steam_osint.py               # Steam 差评监控（9 语种关键词）
│   ├── apac_osint.py                # 亚太社区（巴哈姆特/Yahoo JP/DC Inside）
│   ├── cis_osint.py                 # 俄罗斯/CIS（VK + detector404.ru）
│   ├── downdetector_osint.py        # 全球故障聚合（IsTheServiceDown）
│   ├── platform_status_monitor.py   # 14 个平台/通讯工具状态
│   ├── game_calendar_monitor.py     # 新游上线 + 热游更新（6 平台 + AI 摘要/加速需求/热度）
│   └── russia_event_monitor.py      # 俄罗斯大型活动日历 + 网络管控预警
│
├── competitor_radar/                # 竞品情报
│   ├── discord_listener.py          # 竞品 Discord 公告 + AI 翻译提炼
│   └── exitlag_pricing.py           # 多竞品定价追踪（ExitLag 9 地区 + LagoFast 10 地区）
│
├── brand_monitor/                   # 品牌舆情（9 渠道）
│   ├── trustpilot_monitor.py        # Trustpilot 评分（GearUP + 5 竞品）
│   ├── gearup_reddit.py             # Reddit 全站舆情
│   ├── gearup_youtube.py            # YouTube 多语言舆情（每天 1 次）
│   ├── taiwan_monitor.py            # 巴哈姆特 / PTT
│   ├── japan_monitor.py             # 5ch / Google JP
│   ├── korea_monitor.py             # Naver / DC Inside
│   ├── russia_monitor.py            # VK / Otzovik
│   ├── mideast_monitor.py           # Reddit MENA / Google AR
│   └── southeast_asia_monitor.py    # Tinhte / Reddit SEA / Google 多语
│
└── utils/                           # 共享工具
    ├── notifier.py                  # 通知发送（分组标题 + 重试 + 消息分割 + UTC+8）
    ├── reddit_client.py             # Reddit 共享客户端（OAuth2 可选 + 2s 限流 + 429 重试）
    ├── google_client.py             # Google 搜索共享客户端（5-8s 随机延迟）
    └── alert_dedup.py               # 🔴 加速器无效报警合并去重
```

---

## 一、游戏网络故障监控 (`monitor.py`)

| 维度 | 数据 |
|------|------|
| 监控游戏 | **15 款**：Valorant, LOL, Apex, CS2, Fortnite, PUBG, OW2, R6S, Dota 2, CoD, Where Winds Meet, Aion 2, Tarkov, Arena Breakout, PoE2 |
| 监控渠道 | **8 个**：Reddit OSINT, Steam 差评, 巴哈姆特, Yahoo JP, DC Inside, VK, detector404.ru, IsTheServiceDown |
| 关键词语种 | **9 种**：英/繁中/日/韩/俄/阿拉伯/越南/菲律宾/印尼 |
| 报警标签 | 🟢 加速器可解决 / 🔴 加速器无效 / 🟡 待确认 |
| AI 能力 | Qwen 总结玩家反馈核心内容 |
| 🔴 报警处理 | 合并为一条摘要（保留游戏名+地区），跨运行去重（报过不再报） |
| detector404.ru | 中等投诉量合并成一条只列游戏名，大量及以上逐条详细（含区域+故障类型） |
| 运行频率 | 每 2 小时 |

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
| 10 | Ubisoft Connect | 游戏平台 | Reddit | R6 Siege |
| 11 | FACEIT | 对战平台 | incident.io API + Reddit | CS2 第三方对战 |
| 12 | Xbox Live | 主机 | Reddit | 主机联机 |
| 13 | PSN | 主机 | Reddit | 主机联机 |
| 14 | Garena | 地区平台 | Reddit | 东南亚 LOL/Free Fire |

事件 ID 去重：Discord/Epic/FACEIT 事件不重复报。detector404.ru 中等投诉量合并汇报。

---

## 三、新游上线 + 热游更新 (`game_calendar_monitor.py`)

| 检测内容 | 数据源 | 报警标题 |
|---------|--------|---------|
| 已追踪游戏大版本更新/预告 | Steam News API（9 款有 AppID） | 【热游版本更新预告】 |
| 非 Steam 游戏更新/预告 | Reddit（Valorant/LOL/Fortnite/OW2/CoD/Aion2） | 【热游版本更新预告】 |
| Battle.net 游戏更新 | Reddit（OW2/WoW/D4/炉石） | 【热游版本更新预告】 |
| Steam 热门新游上线 | Steam Featured API（Top Sellers + New Releases） | 【新游上线预告】 |
| Steam 即将发售联机热门 | Steam Coming Soon API | 【新游上线预告】 |
| Epic 新游/免费游戏赠送 | Reddit（3 个子版块） | 【新游上线预告】 |
| PlayStation 新游 | Reddit（PS5/PS4） | 【新游上线预告】 |
| Xbox / Game Pass 上新 | Reddit | 【新游上线预告】 |
| Game Pass 即将上新 | Reddit r/XboxGamePass | 【新游上线预告】 |

**新游上线报警字段**：上线时间 → 热度预估(0-100) → 加速需求(1-5星) → 头部地区 TOP5 → AI 玩法介绍，按热度从高到低排序。

**热游更新报警字段**：加速需求(1-5星) → AI 更新时间/内容摘要/加速器影响，按综合优先级排序。

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
| `discord_listener.py` | Discord 公告监听 + Qwen AI 翻译提炼 | 竞品 Discord 频道 |
| `exitlag_pricing.py` | 多竞品定价变动追踪 | ExitLag 9 地区 + LagoFast 10 地区 = 19 个 |

多竞品架构：`COMPETITORS` 字典配置，新增竞品只需加一条配置。

---

## 六、品牌舆情 (`brand_monitor/`)

| 渠道 | 模块 | 覆盖地区 | 语言 |
|------|------|---------|------|
| Trustpilot | `trustpilot_monitor.py` | 全球 | 英文 |
| Reddit | `gearup_reddit.py` | 全球 | 英文 |
| YouTube | `gearup_youtube.py` | 全球 | 8 语 |
| 巴哈姆特 / PTT | `taiwan_monitor.py` | 台湾 | 繁中 |
| 5ch / Google JP | `japan_monitor.py` | 日本 | 日语 |
| Naver / DC Inside | `korea_monitor.py` | 韩国 | 韩语 |
| VK / Otzovik | `russia_monitor.py` | 俄罗斯/CIS | 俄语 |
| Reddit MENA / Google AR | `mideast_monitor.py` | 中东 | 阿拉伯语 |
| Tinhte / Reddit SEA | `southeast_asia_monitor.py` | 东南亚 | 越/菲/印尼/泰 |

Trustpilot 同时监控 GearUP + 5 家竞品（ExitLag/LagoFast/NoPing/Hone.gg/wtfast）评分变动。

---

## 七、基础设施

| 组件 | 功能 |
|------|------|
| `utils/notifier.py` | 5 种报警标题分组 + 消息超 4000 字自动分割 + 3 次重试指数退避 + UTC+8 时间 |
| `utils/reddit_client.py` | OAuth2 可选（600 req/min）+ 2s 限流 + 429 自动重试 |
| `utils/google_client.py` | 5-8s 随机延迟 + 多语言 Accept-Language |
| `utils/alert_dedup.py` | 🔴 报警合并（保留游戏名+地区）+ 跨运行去重 |
| `game_registry.py` | 15 款游戏统一配置（AppID/subreddit/VK/ITSD/巴哈/Yahoo JP/DC Inside） |
| GitHub Actions cache | 6 个快照文件持久化（日历/平台事件/无效报警去重/俄罗斯活动/定价/评分） |

---

## 数字总结

| 维度 | 数量 |
|------|------|
| Python 脚本 | **27 个** |
| 监控游戏 | **15 款** |
| 游戏故障渠道 | **8 个** |
| 平台/通讯工具 | **14 个** |
| 品牌舆情渠道 | **9 个** |
| 竞品定价地区 | **19 个** |
| 覆盖地区 | **8 个**（欧美/台湾/日本/韩国/俄罗斯-CIS/中东/东南亚/拉美部分） |
| 覆盖语言 | **9 种** |
| AI 接入点 | **6 个**（玩家反馈总结/更新摘要/加速需求/新游介绍/俄罗斯风险评估/竞品公告翻译） |
| 快照文件 | **6 个**（跨运行持久化） |
| 运行频率 | 每 **2 小时**（YouTube 每天 1 次） |
| 报警标题 | **5 种**（商机雷达/新游上线/热游更新/平台状态/品牌舆情/竞品情报） |

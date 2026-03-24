# GearUP Monitors - 更新日志

> **项目目标**: 为全球化游戏加速器 (GPN/VPN) 产品打造一站式自动化情报体系，涵盖游戏网络商机雷达、竞品动态追踪与品牌舆情监控。

---

## [v4.0.0] - 基础设施大修 + 俄罗斯深度覆盖 (Current)

### 🔧 基础设施大修 (Critical Fixes)
- **快照持久化**: GitHub Actions 新增 `actions/cache`，6 个快照文件跨运行持久化，去重和变动检测在线上真正生效。
- **Reddit 共享客户端 (`utils/reddit_client.py`)**: OAuth2 可选（600 req/min）+ 2s 限流 + 429 自动重试。7 个文件迁移至统一入口。
- **Google 搜索共享客户端 (`utils/google_client.py`)**: 5-8s 随机延迟防 CAPTCHA。4 个文件迁移至统一入口。
- **统一游戏配置 (`game_registry.py`)**: 15 款游戏配置集中管理（AppID/subreddit/VK/ITSD/巴哈/Yahoo JP/DC Inside），新增游戏只改一个文件。
- **通知系统增强 (`notifier.py`)**: 消息超 4000 字自动分割 + 3 次重试指数退避 + 报警时间统一 UTC+8。

### 🎯 报警质量优化
- **ISP 短关键词误报修复**: BT/SK/DU 等 2-3 字母 ISP 名改用词边界匹配 + 网络关键词共现要求。
- **平台事件去重**: Discord/Epic/FACEIT 事件 ID 快照去重，同一事件不重复报。
- **YouTube 配额优化**: 搜索词从 15 个精简到 8 个，仅 UTC 00:00-02:00 运行（每天 1 次），配额从 18,000 降到 ~1,600 单位/天。
- **APAC 误报降低**: 巴哈姆特/DC Inside 阈值从 3 提高到 5，且要求匹配 2+ 个不同关键词。
- **🔴 加速器无效报警合并去重 (`utils/alert_dedup.py`)**: 合并成一条摘要（保留游戏名+地区），跨运行去重（报过不再报）。🟢/🟡 报警不受影响。
- **OW2 Steam AppID 补齐** (2357570)。

### 🇷🇺 俄罗斯深度覆盖
- **detector404.ru 接入 (`cis_osint.py`)**: 俄罗斯版 Downdetector，覆盖 10 款游戏 + 4 个平台。投诉量级/区域名/故障类型全部中文翻译。中等投诉量合并成一条，大量及以上逐条详细报告。
- **VK 全覆盖**: 从 6 款扩到 15 款游戏（通过 game_registry 自动生效）。
- **俄罗斯大型活动预警 (`russia_event_monitor.py`)**: 8 个已知年度活动提前 14 天预警（SPIEF/EEF/BRICS/SCO/胜利日等），Reddit 动态检测 Roskomnadzor 封锁 + AI 风险评估。

### 🏷️ 竞品定价扩展
- **LagoFast 加入竞品定价监控**: 10 个地区版本（EN/繁中/JP/KR/PT-BR/TH/VI/ID/AR/TR），多竞品架构重构。

---

## [v3.4.0] - 报警体系全面优化

### 📊 报警标题分离
- 新游上线和热游更新不再混在同一个报警标题下，拆分为独立的 `【新游上线预告】` 和 `【热游版本更新预告】`。
- 通知系统（notifier.py）支持按 alert_type 分组输出，共 5 种标题：商机雷达、新游上线、热游更新、平台状态、品牌舆情、竞品情报。
- 新游/热游更新报警不再显示无意义的 `地区: Global`。

### 🆕 新游上线报警增强
- **上线时间**: 从 Steam 数据提取具体发售日期，放在报警首行。
- **热度预估**: 基于榜单排名、评论数、是否免费、游戏类型、联机类型 5 维度综合打分（0-100），标签为 🔥🔥🔥 热度极高 / 🔥🔥 热度较高 / 🔥 热度中等。
- **加速需求分析**: 通过 Qwen AI 从联网类型、延迟敏感度、跨区服务器、地区封锁、玩家涌入 5 个角度分析，给出 1-5 星评级。
- **头部地区 TOP5**: 基于 Steam 支持语言（全语音权重 1.5x）和各国分级机构推算玩家地区分布占比。
- **AI 玩法介绍**: Qwen 生成 2-3 句中文新游核心玩法和联机模式说明。
- **Steam 排名 + 游戏类型**: 明确标注 `Top Sellers #1` 或 `New Releases #3` 及游戏类型（如 Action, RPG）。
- 报警按热度从高到低排序。

### 🎮 热游更新报警增强
- **加速需求分析**: 同上，基于更新内容分析加速需求星级，放在内容摘要上方。
- **AI 内容摘要**: 提取更新时间 + 内容概括 + 加速器影响判断。
- **AI 玩家反馈概要**: Reddit/巴哈姆特故障报警接入 Qwen 总结玩家反馈核心内容。
- 报警按综合优先级（Reddit 热度 + 加速需求星级）从高到低排序。

---

## [v3.3.0] - AI 驱动的更新内容摘要

### 🤖 游戏日历报警接入通义千问 AI 摘要
- 每条游戏更新报警现在包含 AI 生成的**中文内容摘要**，包括：
  - **更新时间**: 从公告中提取具体的上线/维护日期时间
  - **内容摘要**: 2-3 句话概括核心更新内容
  - **加速器影响**: 判断更新是否带来加速需求（新地图/新赛季 = 需提前准备；反作弊/UI = 无直接影响）
- Steam News 拉取内容长度从 300 字提升到 **2000 字**，为 AI 提供更充分的上下文。
- Reddit 帖子正文（selftext）也会传给 AI 做摘要。
- AI 未配置时自动退化为截取原文前 200 字。
- GitHub Actions 新增 `QWEN_API_KEY` 环境变量（复用已有 Secret）。

### 📊 报警效果对比
改前:
```
[APEX Legends] 🎮 [大版本更新] An Update from the Anti Cheat Team 03/19/2026
```
改后:
```
[APEX Legends] 🎮 [大版本更新] An Update from the Anti Cheat Team 03/19/2026
    更新时间: 2026年3月19日
    内容摘要: Apex Legends 反作弊团队发布最新更新，加强了服务器端检测机制，新增硬件指纹识别，并对近期作弊高发的排位赛段进行了重点打击。
    加速器影响: 反作弊更新对加速器无直接影响，但可能导致短期内服务器负载变化。
```

---

## [v3.2.0] - 提前预警：预告/即将更新检测

### 📢 游戏日历监控转向"提前获知"
将检测重心从"已上线通知"转向"提前 1-4 周预警"：

**预告检测增强**:
- Steam News 和 Reddit 检测新增预告类关键词：`COMING SOON`, `UPCOMING`, `PREVIEW`, `TEASER`, `ROADMAP`, `DEV UPDATE`, `COUNTDOWN`, `NEXT SEASON`, `PBE`, `PTR` 等。
- 报警区分两种标签：`📢 [预告/即将更新]` vs `🎮 [大版本更新]`，一眼看出是提前预警还是已上线。
- Reddit 搜索时间窗口从 `t=day` (1天) 扩大到 `t=week` (7天)，确保提前一周的预告不被遗漏。

**新增检测维度**:
- **Steam Coming Soon 联机热门**: 检查 Steam 即将发售列表，过滤有联机标签的游戏，报告预计发售日期。
- **Game Pass 即将上新**: 通过 Reddit r/XboxGamePass 检测提前公布的 Game Pass 上新名单（通常提前 1-2 周）。

### 📊 预警时间线
| 信息类型 | 提前时间 | 数据源 |
|---------|---------|--------|
| Steam 即将发售 | 1-4 周 | Steam Coming Soon API |
| Game Pass 即将上新 | 1-2 周 | Reddit r/XboxGamePass |
| 官方预告/Roadmap | 1-7 天 | Steam News + Reddit |
| 维护公告 | 1-3 天 | Steam News + Reddit |
| 已上线更新 | 实时 | Steam News + Reddit + 各平台 |

---

## [v3.1.0] - 全平台新游/更新覆盖

### 🎮 游戏日历监控扩展至全平台
在 v3.0.0 Steam 基础上新增 4 个非 Steam 平台的新游上线和热游更新检测：

- **Epic Games Store**: 通过 Reddit r/EpicGamesPC、r/FreeGameFindings、r/GameDeals 检测新游独占、免费游戏赠送。Epic 免费送联机大作时加速需求暴增。
- **PlayStation (PS5/PS4)**: 通过 Reddit r/PS5、r/PS4 检测主机新游首发和重大更新。
- **Xbox / Game Pass**: 通过 Reddit r/XboxGamePass、r/XboxSeriesX 检测 Game Pass 上新和 Xbox 新游。Game Pass Day One 上新 = 大量玩家零成本涌入。
- **Battle.net (暴雪系)**: 通过 Reddit r/Overwatch、r/wow、r/diablo4、r/hearthstone 检测 OW2/WoW/Diablo 4/炉石的赛季更新、大版本补丁和新扩展包。

### 📊 游戏日历监控覆盖总览
| 平台 | 数据源 | 检测内容 |
|------|--------|---------|
| Steam | Steam News API + Featured API | 大版本更新 + 热门新游上线 |
| Epic Games Store | Reddit (3 个子版块) | 新游独占 + 免费游戏赠送 |
| PlayStation | Reddit (PS5/PS4) | 主机新游首发 + 更新 |
| Xbox / Game Pass | Reddit (2 个子版块) | Game Pass 上新 + Xbox 新游 |
| Battle.net | Reddit (4 款暴雪游戏) | 赛季更新 + 扩展包 + 大版本补丁 |
| Riot / 非 Steam 游戏 | Reddit (6 款游戏) | 赛季/版本更新 |

---

## [v3.0.0] - 新游上线与热游更新监控

### 🎮 新增游戏日历监控模块 (`game_monitor/game_calendar_monitor.py`)
- **已追踪游戏大版本更新检测**:
  - 通过 Steam News API 检测 9 款有 AppID 的游戏的官方公告（patch notes、新赛季、大版本更新）。
  - 通过 Reddit 检测 6 款非 Steam 游戏的更新（Valorant/LOL/Fortnite/OW2/CoD/Aion2），基于 flair 和热度过滤。
  - 快照去重机制，同一条新闻只报一次。
- **Steam 热门新游上线检测**:
  - 自动抓取 Steam Top Sellers 和 New Releases 榜单。
  - 通过 appdetails API 过滤出有联机需求的游戏（Multi-player/Online PvP/Online Co-op/MMO）。
  - 最多推送 5 条，避免刷屏。
- **商业价值**:
  - 大版本更新当天 = 用户量暴增 = 营销推送最佳窗口。
  - 热门新游上线 = 提前准备加速支持 = 抢占先机。

---

## [v2.9.0] - 平台监控扩充至 13 个

### 🌐 平台状态监控扩充
新增 7 个平台/通讯工具，`platform_status_monitor.py` 总覆盖从 6 个扩充至 **13 个**：

**游戏平台 (新增 4 个)**:
- **Riot Games (Valorant/LOL)**: 官方 CDN Status API，分区域（AP/EU/NA/KR/JP/SG/EUW）检测事件和维护。
- **Xbox Live / PSN**: Reddit 社区间接检测主机联机服务状态。
- **EA App**: Reddit 间接检测 EA 服务器连接问题（影响 Apex Legends/FIFA 等）。
- **Ubisoft Connect**: Reddit 间接检测（影响 Rainbow Six Siege 等）。

**通讯工具 (新增 2 个)**:
- **WhatsApp**: Reddit 间接检测中东/东南亚 VoIP 封锁和全球故障。
- **LINE**: Reddit 间接检测日本/泰国/台湾连接问题（日语/泰语关键词）。

**地区平台 (新增 1 个)**:
- **Garena**: Reddit 间接检测东南亚游戏平台状态（LOL 东南亚/Free Fire）。

---

## [v2.8.0] - 通讯与游戏平台全球连接监控

### 🌐 新增平台状态监控模块 (`game_monitor/platform_status_monitor.py`)
- **Discord 全球状态监控**:
  - 官方 Status API，监控 15 个区域 Voice 服务器状态（含俄罗斯、日本、新加坡、香港、韩国等）。
  - 核心服务状态（API、Gateway、Push Notifications）。
  - 活跃事件实时报警。
  - 俄罗斯区域异常时特殊标注 `🚨 [俄罗斯受影响]`。
- **Telegram 俄罗斯连接监控**:
  - 通过 Reddit 搜索（英文 + 俄语关键词）间接检测 Telegram 在俄罗斯/CIS 的封锁或干扰。
- **Steam 全球状态监控**:
  - steamstat.us API 检测 Steam CM 和 Store 服务状态。
  - Reddit r/Steam 辅助检测连接问题讨论激增。
- **Epic Games 平台状态监控**:
  - 官方 Status API，监控 EGS、Epic Online Services、Rocket League、Fall Guys 等。
  - 活跃事件实时报警。
- **Battle.net 状态监控**:
  - Reddit 间接检测 Battle.net/Blizzard 服务器连接问题。

---

## [v2.7.0] - 监控游戏扩充至 15 款

### 🎮 新增 5 款监控游戏
- **Where Winds Meet (燕云十六声)**: Steam AppID 1928380, Reddit r/WhereWindsMeet, 巴哈姆特, Yahoo JP, DC Inside。国产武侠 MMO，跨服需求强。
- **Aion 2 (永恒之塔2)**: 不在 Steam，Reddit r/aion, Yahoo JP, DC Inside。韩服为主，加速器刚需。
- **Escape from Tarkov (逃离塔科夫)**: Steam AppID 1422440, Reddit r/EscapefromTarkov, 巴哈姆特, Yahoo JP, DC Inside。硬核射击，网络敏感度极高。
- **Arena Breakout: Infinite (暗区突围)**: Steam AppID 2073620, Reddit r/ArenaBreakoutInfinite, Yahoo JP, DC Inside。腾讯出品，对标塔科夫。
- **Path of Exile 2 (流亡黯道)**: Steam AppID 2694490 (台港澳版), Reddit r/pathofexile, 巴哈姆特, Yahoo JP, DC Inside。

### 📊 覆盖统计
- 监控游戏总数从 10 款扩充至 **15 款**。
- 其中 9 款有 Steam 差评监控（新增 3 款），6 款不在 Steam 靠 Reddit + 亚太社区覆盖。
- 新增游戏均重点关注非大陆地区服务器问题（亚太、欧美、中东）。

---

## [v2.6.0] - 日本区覆盖补齐

### 🇯🇵 日本区覆盖补齐 (Japan Coverage)
- **新增日本品牌舆情监控模块 (`brand_monitor/japan_monitor.py`)**:
  - 5ch（旧2ch）: 通过 Google site search 间接搜索日本最大匿名论坛。
  - Google 日语搜索: 覆盖 4Gamer、GameWith、Price.com 等日本本土游戏媒体和评价网站。
  - Reddit 日本 subreddit（r/japan, r/japanlife, r/japangaming）。
  - 加速器通用日语搜索词（VPN おすすめ、ping下げる ツール 等）。
  - 日语情感分析关键词库（詐欺/ゴミ/最悪 vs おすすめ/神/最高）。

### 🔤 日语覆盖增强
- **亚太故障监控 (`apac_osint.py`)**: 日语关键词从 6 个扩充至 **15 个**，与 steam_osint.py 对齐（新增 ラグ、回線落ち、切断、ピング、パケロス 等）。
- **YouTube 舆情 (`gearup_youtube.py`)**: 新增日语情感分析关键词（正面 8 个 + 负面 8 个），补齐了之前的日语情感分析空白。

---

## [v2.5.0] - 东南亚区域覆盖

### 🌏 东南亚区域覆盖 (SEA Coverage)
- **新增东南亚品牌舆情监控模块 (`brand_monitor/southeast_asia_monitor.py`)**:
  - 越南: Tinhte.vn 科技论坛搜索 + Google 越南语搜索。
  - 菲律宾: Reddit r/Philippines, r/PHGamers + Google 菲律宾语搜索。
  - 印尼: Reddit r/indonesia, r/IndoGaming + Google 印尼语搜索（覆盖 Kaskus 等论坛）。
  - 泰国: Reddit r/Thailand + Google 泰语搜索。
  - 马来西亚/新加坡: Reddit r/Malaysia, r/MalaysianGamers, r/singapore。
  - 越南语/菲律宾语/印尼语/泰语 4 语种情感分析关键词库。

### 🔤 东南亚语言关键词扩充
- **Steam 差评监控 (`steam_osint.py`)**: 新增越南语、菲律宾语（他加禄语）、印尼语网络故障关键词，语言覆盖从 6 种扩充至 **9 种**。
- **YouTube 舆情监控 (`gearup_youtube.py`)**: 新增越南语、印尼语、菲律宾语搜索词和情感分析关键词。

---

## [v2.4.0] - 中东/阿拉伯语区覆盖补齐

### 🌍 中东区域覆盖 (MENA Coverage)
- **新增中东品牌舆情监控模块 (`brand_monitor/mideast_monitor.py`)**:
  - 搜索 10 个中东国家 subreddit（沙特、阿联酋、埃及、约旦、科威特、巴林、卡塔尔、阿曼、伊拉克、黎巴嫩）中的加速器讨论。
  - Reddit 全站阿拉伯语关键词搜索。
  - Google 阿拉伯语搜索（间接覆盖阿拉伯本土论坛和博客）。
  - 阿拉伯语情感分析关键词库。

### 🔤 阿拉伯语关键词扩充
- **Steam 差评监控 (`steam_osint.py`)**: 新增阿拉伯语网络故障关键词（لاق, تأخير, بنق, تقطيع, السيرفر طاح 等），语言覆盖从 5 种扩充至 **6 种**。
- **YouTube 舆情监控 (`gearup_youtube.py`)**: 新增阿拉伯语搜索词和情感分析关键词。

---

## [v2.3.0] - 全球品牌舆情多渠道覆盖

### 🚀 新增功能 (New Features)
- **新增 Trustpilot 品牌评价监控 (`brand_monitor/trustpilot_monitor.py`)**:
  - 同时监控 GearUP 及 5 家竞品（ExitLag, LagoFast, NoPing, Hone.gg, wtfast）的 Trustpilot 评分和评论。
  - 自动快照对比，检测评分变动、新增评论数和 1 星差评占比变化。
- **新增台湾区品牌舆情监控 (`brand_monitor/taiwan_monitor.py`)**:
  - 搜索巴哈姆特和 PTT 上关于 GearUP 及竞品的讨论，繁体中文情感分析。
- **新增韩国区品牌舆情监控 (`brand_monitor/korea_monitor.py`)**:
  - 搜索 Naver 和 DC Inside 上关于加速器的讨论，韩语情感分析。
- **新增俄语区品牌舆情监控 (`brand_monitor/russia_monitor.py`)**:
  - 搜索 VK 和 Otzovik（俄罗斯最大评价网站）上的加速器讨论，俄语情感分析。

### 🌍 小语种覆盖增强
- **YouTube 搜索关键词多语言扩展**: 新增繁体中文、日语、韩语、俄语搜索词，覆盖非英语区的视频评测。

---

## [v2.2.0] - 竞品定价监控 + 品牌舆情体系

### 🚀 新增功能 (New Features)
- **新增 ExitLag 多地区定价监控 (`competitor_radar/exitlag_pricing.py`)**:
  - 抓取 ExitLag 官网 9 个语言/地区版本的定价页面（EN, 繁中, JP, KR, PT, RU, ES, AR, DE）。
  - 自动保存定价快照，每次运行与上次对比，检测价格变动、折扣调整和套餐结构变化。
  - 首次运行保存基线，不触发报警。
- **新增 GearUP Booster Reddit 全站舆情监控 (`brand_monitor/gearup_reddit.py`)**:
  - 通过 Reddit 全站搜索（绕过已封禁的 r/GearUPBooster），抓取所有提及 GearUP Booster 的帖子。
  - 内置正面/负面关键词情感分析（中英双语），输出最热帖子和负面帖子预警。
- **新增 GearUP Booster YouTube 舆情监控 (`brand_monitor/gearup_youtube.py`)**:
  - 通过 YouTube Data API v3 搜索 GearUP Booster 相关视频（7 天窗口）。
  - 获取视频播放量、点赞数、评论数等统计数据。
  - 情感分析分类，输出最热视频和负面视频预警。

### 📁 项目结构扩充
- 新增 `brand_monitor/` 目录，用于品牌舆情监控模块。
- `competitor_radar/` 目录新增 ExitLag 定价监控。
- GitHub Actions 工作流新增 3 个 step，集成所有新模块。
- 新增环境变量: `YOUTUBE_API_KEY`（需在 GitHub Secrets 中配置）。

---

## [v2.1.0] - Steam 差评渠道接入

### 🌍 监控渠道扩充 (Channel Expansions)
- **新增 Steam 近期差评监控模块 (`steam_osint.py`)**:
  - 通过 Steam Store Reviews API 拉取指定游戏的近期差评，无需 API Key。
  - 多语言关键词匹配（英文、中文、俄语），覆盖全球 Steam 玩家的网络投诉。
  - 支持热度飙升检测：当差评被大量点赞时，降低阈值强制触发警报。
  - 自动跳过不在 Steam 上架的游戏（Valorant、LOL、Fortnite、OW2）。
- 监控渠道总数从 7 个扩充至 **8 个**。

---

## [v2.0.0] - 商业化雷达与全区域补齐

本次更新是该项目诞生以来最大的一次重构，彻底将脚本从单纯的“宕机检测”升级为**加速器产品的专属商机雷达**。

### 🚀 新增功能 (New Features)
- **商机情报分类 (Commercial Intent Classification)**: 
  - 能够智能区分“官方宕机 (Down)”和“路由故障 (Routing)”。
  - 当命中官方宕机时，报警提示 `❌ 疑似官方宕机/维护 (加速器可能无效)`，避免无效广告投放。
  - 当命中高 Ping / 丢包等路由问题时，报警提示 `⭐⭐⭐ 绝佳营销时机 (路由/高Ping故障)`。
- **全球 ISP (运营商) 自动提取**:
  - 内置了庞大的全球主流运营商词库（覆盖北美、欧洲、南美、东南亚及独联体）。
  - 支持提取母语宽带名称（如中华电信、NURO、Ростелеком）。
  - 报警时直接输出“涉及 ISP”，辅助定向广告投放。
- **热度飙升与病毒式传播预测 (Velocity Tracking)**:
  - 新增帖子热度评估逻辑。当 Reddit 讨论帖在短时间内“点赞数 > 20”或“评论数 > 10”时，无视发帖量阈值直接触发最高优先级警报 `🔥 [热度飙升]`。

### 🌍 监控渠道扩充 (Channel Expansions)
- **新增 5 款核心竞技游戏**: 监控库扩充至 10 款全球最热门的 PC 游戏（新增 PUBG, Overwatch 2, Rainbow Six Siege, Dota 2, Call of Duty）。
- **新增独联体/俄语区专属模块 (`cis_osint.py`)**: 
  - 突破了 Reddit 的盲区，利用免登录方案抓取俄罗斯最大社交网络 **VKontakte (VK)** 各游戏大群的实况。
  - 支持俄语特定故障词汇的侦测（如 пинг, лаги）。
- **新增全球故障聚合网站模块 (`downdetector_osint.py`)**: 
  - 成功绕过 Downdetector 严格的 Cloudflare 防火墙。
  - 采用 IsTheServiceDown 替代方案，侦测全局曲线的瞬间飙升。
  - **精准过滤了轻微网络波动**，仅在出现严重大面积宕机时告警。

---

## [v1.1.0] - 亚太地区与中东本地化深耕

本次更新解决了严重依赖英文社区（Reddit）导致的非英语区监控盲点问题。

### 🚀 新增功能 (New Features)
- **新增亚太核心区专属模块 (`apac_osint.py`)**:
  - **台湾 (TW)**: 接入巴哈姆特 (Bahamut) 游戏哈啦板爬虫，支持繁体中文故障词匹配（如：爆ping、卡頓）。
  - **日本 (JP)**: 接入 Yahoo! 实时搜索（间接获取 Twitter/X 上的趋势），监控日语玩家的核心吐槽（如：鯖落ち）。
  - **韩国 (KR)**: 接入 DC Inside 各游戏画廊的抓取。
- **中东与小语种区域动态阈值**:
  - 在原有的 Reddit 扫描引擎中，大幅扩充了地理映射表（补充了 MENA 大区、沙特、巴林等节点）。
  - 针对中东、南美、亚太等发帖量较小的区域，将报警阈值从 5 篇/4小时 **智能下调**至 3 篇/4小时，防止漏报。

### ⚙️ 代码优化
- 封装了主程序入口，解决了并发抓取亚太社区时的代码冗余。
- 修复了因为抓取到海外 Emoji 符号导致的 Windows 控制台 `gbk codec` 崩溃问题，强制接管 `utf-8` 编码。

---

## [v1.0.0] - 核心引擎与自动化部署发布 (Initial Release)

项目的初始版本，确立了“绝不使用主动 Ping，只看玩家真实反馈”的核心理念。

### 🚀 核心功能
- **Reddit OSINT 引擎**: 利用 Reddit 的公开搜索接口，抓取最近 4 小时内特定游戏板块关于 "server, ping, lag, packet loss" 的高频讨论。
- **Epic Games Status API**: 直接集成 Fortnite 的官方状态 JSON 解析。
- **网易 POPO Webhook 整合**: 将复杂的报错数据清洗并转化为结构化的 Markdown 表格，通过飞书/POPO 机器人发送实时警报。
- **0 成本云端挂机**: 编写并提供 GitHub Actions `.yml` 模板，支持纯免费、免服务器的 24 小时 Cron 定时扫描。

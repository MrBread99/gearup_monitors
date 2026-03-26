# ==========================================
# 统一游戏注册表 (Game Registry)
# ==========================================
# 所有模块共享的游戏配置，新增/修改游戏只需改这一个文件。
# ==========================================

GAME_REGISTRY = {
    # === 原始 10 款游戏 ===
    'Valorant': {
        'steam_appid': None,
        'subreddit': 'VALORANT',
        'vk_group': 'valorant_ru',
        'itsd_slug': 'valorant',
        'tw_bsn': '36322',
        'jp_search': 'ヴァロラント',
        'kr_dc': 'valorant',
    },
    'League of Legends': {
        'steam_appid': None,
        'subreddit': 'leagueoflegends',
        'vk_group': 'leagueoflegends',
        'itsd_slug': 'league-of-legends',
        'tw_bsn': '17532',
        'jp_search': 'LoL',
        'kr_dc': 'lol',
    },
    'APEX Legends': {
        'steam_appid': 1172470,
        'subreddit': 'apexlegends',
        'vk_group': 'apexlegendsru',
        'itsd_slug': 'apex-legends',
        'tw_bsn': '36276',
        'jp_search': 'Apex',
        'kr_dc': 'apexlegends',
    },
    'CS2': {
        'steam_appid': 730,
        'subreddit': 'GlobalOffensive',
        'vk_group': 'csgo',
        'itsd_slug': 'counter-strike',
        'tw_bsn': '4212',
        'jp_search': 'CS2',
        'kr_dc': 'cs2',
    },
    'Fortnite': {
        'steam_appid': None,
        'subreddit': 'FortNiteBR',
        'vk_group': 'fortnite',
        'itsd_slug': 'fortnite',
        'tw_bsn': '33703',
        'jp_search': 'フォートナイト',
        'kr_dc': 'fortnite',
    },
    'PUBG': {
        'steam_appid': 578080,
        'subreddit': 'PUBATTLEGROUNDS',
        'vk_group': 'pubg',
        'itsd_slug': 'playerunknown-s-battlegrounds-pubg',
        'tw_bsn': '33700',
        'jp_search': 'PUBG',
        'kr_dc': 'pubg',
    },
    'Overwatch 2': {
        'steam_appid': 2357570,
        'subreddit': 'Overwatch',
        'vk_group': 'overwatchrus',
        'itsd_slug': 'overwatch',
        'tw_bsn': '29220',
        'jp_search': 'オーバーウォッチ2',
        'kr_dc': 'overwatch',
    },
    'Rainbow Six Siege': {
        'steam_appid': 359550,
        'subreddit': 'Rainbow6',
        'vk_group': 'rainbow6russia',
        'itsd_slug': 'tom-clancy-s-rainbow-six-siege',
        'tw_bsn': '28498',
        'jp_search': 'R6S',
        'kr_dc': 'rainbow6',
    },
    'Dota 2': {
        'steam_appid': 570,
        'subreddit': 'DotA2',
        'vk_group': 'dota2',
        'itsd_slug': 'dota-2',
        'tw_bsn': '22901',
        'jp_search': 'Dota2',
        'kr_dc': 'dota2',
    },
    'Call of Duty': {
        'steam_appid': None,
        'subreddit': 'CallOfDuty',
        'vk_group': 'callofdutyru',
        'itsd_slug': 'call-of-duty',
        'tw_bsn': '5371',
        'jp_search': 'CoD',
        'kr_dc': 'callofduty',
    },

    # === 新增 5 款游戏 ===
    'Where Winds Meet': {
        'steam_appid': 1928380,
        'subreddit': 'WhereWindsMeet',
        'vk_group': 'wherewindsmeet',
        'itsd_slug': None,
        'tw_bsn': '77498',
        'jp_search': '燕雲十六声',
        'kr_dc': 'wherewindsmeet',
    },
    'Aion 2': {
        'steam_appid': None,
        'subreddit': 'aion',
        'vk_group': 'aion2ru',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'AION2',
        'kr_dc': 'aion',
    },
    'Escape from Tarkov': {
        'steam_appid': 1422440,
        'subreddit': 'EscapefromTarkov',
        'vk_group': 'eft_ru',
        'itsd_slug': 'escape-from-tarkov',
        'tw_bsn': '35405',
        'jp_search': 'タルコフ',
        'kr_dc': 'tarkov',
    },
    'Arena Breakout Infinite': {
        'steam_appid': 2073620,
        'subreddit': 'ArenaBreakoutInfinite',
        'vk_group': 'arenabreakout',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'ArenaBreakout',
        'kr_dc': 'arenabreakout',
    },
    'Path of Exile 2': {
        'steam_appid': 2694490,
        'subreddit': 'pathofexile',
        'vk_group': 'pathofexile_ru',
        'itsd_slug': 'path-of-exile',
        'tw_bsn': '18966',
        'jp_search': 'POE2',
        'kr_dc': 'pathofexile',
    },

    # === 新增 14 款游戏 ===
    'Dead by Daylight': {
        'steam_appid': 381210,
        'subreddit': 'deadbydaylight',
        'vk_group': 'deadbydaylight_ru',
        'itsd_slug': 'dead-by-daylight',
        'tw_bsn': '32603',
        'jp_search': 'デッドバイデイライト',
        'kr_dc': 'deadbydaylight',
    },
    'Rust': {
        'steam_appid': 252490,
        'subreddit': 'playrust',
        'vk_group': 'rust_game',
        'itsd_slug': 'rust',
        'tw_bsn': None,
        'jp_search': 'Rust',
        'kr_dc': 'rust',
    },
    'GTA Online': {
        'steam_appid': 271590,
        'subreddit': 'gtaonline',
        'vk_group': 'gtaonline',
        'itsd_slug': 'grand-theft-auto-online',
        'tw_bsn': '25196',
        'jp_search': 'GTAオンライン',
        'kr_dc': 'gta',
    },
    'Destiny 2': {
        'steam_appid': 1085660,
        'subreddit': 'DestinyTheGame',
        'vk_group': 'destiny2_ru',
        'itsd_slug': 'destiny-2',
        'tw_bsn': '33689',
        'jp_search': 'Destiny2',
        'kr_dc': 'destiny2',
    },
    'Monster Hunter Wilds': {
        'steam_appid': 2246340,
        'subreddit': 'MonsterHunter',
        'vk_group': 'monsterhunter',
        'itsd_slug': None,
        'tw_bsn': '5786',
        'jp_search': 'モンハンワイルズ',
        'kr_dc': 'monsterhunter',
    },
    'The Finals': {
        'steam_appid': 2073850,
        'subreddit': 'thefinals',
        'vk_group': 'thefinals',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'THE FINALS',
        'kr_dc': 'thefinals',
    },
    'Marvel Rivals': {
        'steam_appid': 2767030,
        'subreddit': 'marvelrivals',
        'vk_group': 'marvelrivals',
        'itsd_slug': None,
        'tw_bsn': '79940',
        'jp_search': 'マーベルライバルズ',
        'kr_dc': 'marvelrivals',
    },
    'Rocket League': {
        'steam_appid': 252950,  # Steam 下架但 AppID 仍有效
        'subreddit': 'RocketLeague',
        'vk_group': 'rocketleague',
        'itsd_slug': 'rocket-league',
        'tw_bsn': '29089',
        'jp_search': 'ロケットリーグ',
        'kr_dc': 'rocketleague',
    },
    'Palworld': {
        'steam_appid': 1623730,
        'subreddit': 'Palworld',
        'vk_group': 'palworld',
        'itsd_slug': None,
        'tw_bsn': '71458',
        'jp_search': 'パルワールド',
        'kr_dc': 'palworld',
    },
    'Naraka Bladepoint': {
        'steam_appid': 1203220,
        'subreddit': 'NarakaBladePoint',
        'vk_group': 'narakabladepoint',
        'itsd_slug': None,
        'tw_bsn': '38832',
        'jp_search': 'ナラカ',
        'kr_dc': 'naraka',
    },
    'Lost Ark': {
        'steam_appid': 1599340,
        'subreddit': 'lostarkgame',
        'vk_group': 'lostark_ru',
        'itsd_slug': 'lost-ark',
        'tw_bsn': '27410',
        'jp_search': 'ロストアーク',
        'kr_dc': 'lostark',
    },
    'EA FC': {
        'steam_appid': 2669320,
        'subreddit': 'EASportsFC',
        'vk_group': 'eafc',
        'itsd_slug': 'ea-sports-fc',
        'tw_bsn': None,
        'jp_search': 'EA FC',
        'kr_dc': 'fifa',
    },
    'Warframe': {
        'steam_appid': 230410,
        'subreddit': 'Warframe',
        'vk_group': 'warframe_ru',
        'itsd_slug': 'warframe',
        'tw_bsn': '23498',
        'jp_search': 'Warframe',
        'kr_dc': 'warframe',
    },

    # === 非 Steam 热门游戏 ===
    'Genshin Impact': {
        'steam_appid': None,
        'subreddit': 'Genshin_Impact',
        'vk_group': 'genshinimpact_ru',
        'itsd_slug': 'genshin-impact',
        'tw_bsn': '36730',
        'jp_search': '原神',
        'kr_dc': 'genshinimpact',
    },
    'Honkai Star Rail': {
        'steam_appid': None,
        'subreddit': 'HonkaiStarRail',
        'vk_group': 'honkaistarrail',
        'itsd_slug': None,
        'tw_bsn': '73498',
        'jp_search': '崩壊スターレイル',
        'kr_dc': 'honkaistarrail',
    },
    'Wuthering Waves': {
        'steam_appid': None,
        'subreddit': 'WutheringWaves',
        'vk_group': 'wutheringwaves',
        'itsd_slug': None,
        'tw_bsn': '74934',
        'jp_search': '鳴潮',
        'kr_dc': 'wutheringwaves',
    },
    'Zenless Zone Zero': {
        'steam_appid': None,
        'subreddit': 'ZenlessZoneZero',
        'vk_group': 'zenlesszonezero',
        'itsd_slug': None,
        'tw_bsn': '74860',
        'jp_search': 'ゼンレスゾーンゼロ',
        'kr_dc': 'zenlesszonezero',
    },
    'Roblox': {
        'steam_appid': None,
        'subreddit': 'roblox',
        'vk_group': 'roblox',
        'itsd_slug': 'roblox',
        'tw_bsn': None,
        'jp_search': 'Roblox',
        'kr_dc': 'roblox',
    },

    # === 补充热门联机游戏 ===
    'Path of Exile': {
        'steam_appid': 238960,
        'subreddit': 'pathofexile',
        'vk_group': 'pathofexile_ru',
        'itsd_slug': 'path-of-exile',
        'tw_bsn': '18966',
        'jp_search': 'POE',
        'kr_dc': 'pathofexile',
    },
    'Marathon': {
        'steam_appid': 3065800,  # 2026.3.5 已发售，PvPvE 提取射击
        'subreddit': 'Marathon',
        'vk_group': 'marathon_bungie',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'マラソン Bungie',
        'kr_dc': 'marathon',
    },
    'Albion Online': {
        'steam_appid': 761890,
        'subreddit': 'albiononline',
        'vk_group': 'albiononline_ru',
        'itsd_slug': 'albion-online',
        'tw_bsn': None,
        'jp_search': 'アルビオンオンライン',
        'kr_dc': 'albiononline',
    },
    'The Quinfall': {
        'steam_appid': 2294660,
        'subreddit': 'TheQuinfall',
        'vk_group': 'thequinfall',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'Quinfall',
        'kr_dc': 'thequinfall',
    },
    'ARC Raiders': {
        'steam_appid': 1808500,
        'subreddit': 'ARC_Raiders',
        'vk_group': 'arcraiders',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'ARC Raiders',
        'kr_dc': 'arcraiders',
    },

    # === Tier 1: 高玩家量 + 高加速需求 ===
    'Crimson Desert': {
        'steam_appid': 2550430,
        'subreddit': 'CrimsonDesert',
        'vk_group': 'crimsondesert',
        'itsd_slug': None,
        'tw_bsn': '37615',
        'jp_search': 'クリムゾンデザート',
        'kr_dc': 'crimsondesert',
    },
    'Delta Force': {
        'steam_appid': 2612680,
        'subreddit': 'DeltaForce',
        'vk_group': 'deltaforce',
        'itsd_slug': None,
        'tw_bsn': '78342',
        'jp_search': 'デルタフォース',
        'kr_dc': 'deltaforce',
    },
    'War Thunder': {
        'steam_appid': 236390,
        'subreddit': 'Warthunder',
        'vk_group': 'warthunder',
        'itsd_slug': 'war-thunder',
        'tw_bsn': '20947',
        'jp_search': 'WarThunder',
        'kr_dc': 'warthunder',
    },
    'HELLDIVERS 2': {
        'steam_appid': 553850,
        'subreddit': 'Helldivers',
        'vk_group': 'helldivers2',
        'itsd_slug': None,
        'tw_bsn': '24827',
        'jp_search': 'ヘルダイバー2',
        'kr_dc': 'helldivers',
    },
    'DayZ': {
        'steam_appid': 221100,
        'subreddit': 'dayz',
        'vk_group': 'dayz_ru',
        'itsd_slug': 'dayz',
        'tw_bsn': None,
        'jp_search': 'DayZ',
        'kr_dc': 'dayz',
    },
    'Street Fighter 6': {
        'steam_appid': 1364780,
        'subreddit': 'StreetFighter',
        'vk_group': 'streetfighter',
        'itsd_slug': None,
        'tw_bsn': '38124',
        'jp_search': 'スト6',
        'kr_dc': 'streetfighter',
    },
    'Hunt Showdown': {
        'steam_appid': 594650,
        'subreddit': 'HuntShowdown',
        'vk_group': 'huntshowdown',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'HuntShowdown',
        'kr_dc': 'huntshowdown',
    },

    # === Tier 2: 稳定玩家群 / 区域热门 ===
    'Final Fantasy XIV': {
        'steam_appid': 39210,
        'subreddit': 'ffxiv',
        'vk_group': 'ffxiv_ru',
        'itsd_slug': 'final-fantasy-xiv',
        'tw_bsn': '23137',
        'jp_search': 'FF14',
        'kr_dc': 'ff14',
    },
    'Black Desert Online': {
        'steam_appid': 582660,
        'subreddit': 'blackdesertonline',
        'vk_group': 'blackdesert_ru',
        'itsd_slug': 'black-desert-online',
        'tw_bsn': '29095',
        'jp_search': '黒い砂漠',
        'kr_dc': 'blackdesert',
    },
    'Throne and Liberty': {
        'steam_appid': 2429640,
        'subreddit': 'throneandliberty',
        'vk_group': 'throneandliberty',
        'itsd_slug': None,
        'tw_bsn': '33317',
        'jp_search': 'ThroneAndLiberty',
        'kr_dc': 'throneandliberty',
    },
    'Tekken 8': {
        'steam_appid': 2573770,
        'subreddit': 'Tekken',
        'vk_group': 'tekken',
        'itsd_slug': None,
        'tw_bsn': '161',
        'jp_search': '鉄拳8',
        'kr_dc': 'tekken',
    },
    'ARK Survival Ascended': {
        'steam_appid': 2399830,
        'subreddit': 'ARK',
        'vk_group': 'ark_survival',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'ARK',
        'kr_dc': 'ark',
    },
    'Elden Ring Nightreign': {
        'steam_appid': 2584040,
        'subreddit': 'EldenRingNightreign',
        'vk_group': 'eldenring',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'エルデンリング ナイトレイン',
        'kr_dc': 'eldenring',
    },
    'STALCRAFT X': {
        'steam_appid': 1818450,
        'subreddit': 'Stalcraft',
        'vk_group': 'stalcraft',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'STALCRAFT',
        'kr_dc': 'stalcraft',
    },
    'Dont Starve Together': {
        'steam_appid': 322330,
        'subreddit': 'dontstarve',
        'vk_group': 'dontstarve',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'ドンスタ',
        'kr_dc': 'dontstarve',
    },
    'Once Human': {
        'steam_appid': 2388800,
        'subreddit': 'OnceHumanOfficial',
        'vk_group': 'oncehuman',
        'itsd_slug': None,
        'tw_bsn': None,
        'jp_search': 'OnceHuman',
        'kr_dc': 'oncehuman',
    },
    'Team Fortress 2': {
        'steam_appid': 440,
        'subreddit': 'tf2',
        'vk_group': 'tf2',
        'itsd_slug': 'team-fortress-2',
        'tw_bsn': None,
        'jp_search': 'TF2',
        'kr_dc': 'tf2',
    },

    # === 非 Steam 顶级 MMO ===
    'World of Warcraft': {
        'steam_appid': None,  # Battle.net 独占
        'subreddit': 'wow',
        'vk_group': 'wow_ru',
        'itsd_slug': 'world-of-warcraft',
        'tw_bsn': '5219',
        'jp_search': 'WoW',
        'kr_dc': 'wow',
    },
}


def get_all_game_names():
    """返回所有游戏名列表"""
    return list(GAME_REGISTRY.keys())


def get_steam_app_map():
    """返回 {游戏名: steam_appid} 映射，兼容 steam_osint.py"""
    return {name: cfg['steam_appid'] for name, cfg in GAME_REGISTRY.items()}


def get_vk_game_map():
    """返回 {游戏名: vk_group} 映射，兼容 cis_osint.py"""
    return {name: cfg['vk_group'] for name, cfg in GAME_REGISTRY.items()
            if cfg.get('vk_group')}


def get_itsd_game_map():
    """返回 {游戏名: itsd_slug} 映射，兼容 downdetector_osint.py"""
    return {name: cfg['itsd_slug'] for name, cfg in GAME_REGISTRY.items()
            if cfg.get('itsd_slug')}


def get_apac_configs():
    """返回 {游戏名: {tw_bsn, jp_search, kr_dc}} 映射，兼容 monitor.py"""
    return {name: {
        'tw_bsn': cfg.get('tw_bsn'),
        'jp_search': cfg.get('jp_search'),
        'kr_dc': cfg.get('kr_dc'),
    } for name, cfg in GAME_REGISTRY.items()}


def get_game_config(game_name):
    """获取单个游戏的完整配置"""
    return GAME_REGISTRY.get(game_name, {})

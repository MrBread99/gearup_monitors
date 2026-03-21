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

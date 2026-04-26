import requests
import time
import os

# ==========================================
# Reddit API 共享客户端
# ==========================================
# 提供 OAuth2 认证（提升限流从 60 -> 600 请求/分钟）
# 和全局请求限流（每次请求间隔 1 秒）
#
# 环境变量:
#   REDDIT_CLIENT_ID     - Reddit App Client ID
#   REDDIT_CLIENT_SECRET - Reddit App Client Secret
#
# 申请方式: https://www.reddit.com/prefs/apps
# 选择 "script" 类型，redirect uri 填 http://localhost
# ==========================================

REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET', '')

_access_token = None
_token_expires = 0
_last_request_time = 0
_REQUEST_INTERVAL = 4.0  # 匿名模式 4 秒间隔，GitHub Actions 共享 IP 需要更保守
_REQUEST_INTERVAL_OAUTH = 1.0  # OAuth 模式 1 秒间隔（600 req/min 限额）
_consecutive_403 = 0
_circuit_open = False  # 熔断器：连续 403 过多时停止所有 Reddit 调用
_CIRCUIT_BREAKER_THRESHOLD = 3  # 连续 3 次 403 触发熔断
_last_request_meta = {
    'mode': 'anonymous',
    'token_state': 'unknown',
    'request_state': 'idle',
    'status_code': None,
    'request_url': '',
    'final_url': '',
}


def _set_last_request_meta(**kwargs):
    _last_request_meta.update(kwargs)


def get_last_reddit_request_meta():
    return dict(_last_request_meta)


def _get_oauth_token():
    """获取 Reddit OAuth2 access token（Application Only 模式）"""
    global _access_token, _token_expires

    if _access_token and time.time() < _token_expires:
        _set_last_request_meta(token_state='cached_token')
        return _access_token

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        _set_last_request_meta(token_state='missing_credentials')
        return None

    try:
        auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
        data = {'grant_type': 'client_credentials'}
        headers = {'User-Agent': 'OSINT-Monitor/3.0'}

        response = requests.post(
            'https://www.reddit.com/api/v1/access_token',
            auth=auth,
            data=data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            token_data = response.json()
            _access_token = token_data.get('access_token')
            _token_expires = time.time() + token_data.get('expires_in', 3600) - 60
            _set_last_request_meta(token_state='oauth_token_ok')
            print("[Reddit] OAuth2 认证成功，限流提升至 600 请求/分钟")
            return _access_token
        else:
            _set_last_request_meta(
                token_state='oauth_token_failed',
                status_code=response.status_code,
                request_url='https://www.reddit.com/api/v1/access_token',
                final_url='https://www.reddit.com/api/v1/access_token',
            )
            print(f"[Reddit] OAuth2 认证失败: {response.status_code}")
            return None
    except Exception as e:
        _set_last_request_meta(
            token_state='oauth_token_exception',
            request_state='token_exception',
            status_code=None,
            request_url='https://www.reddit.com/api/v1/access_token',
            final_url='https://www.reddit.com/api/v1/access_token',
        )
        print(f"[Reddit] OAuth2 认证异常: {e}")
        return None


def _throttle():
    """全局限流：根据认证模式调整间隔"""
    global _last_request_time
    token = _access_token  # 快速检查当前是否有 token
    interval = _REQUEST_INTERVAL_OAUTH if token else _REQUEST_INTERVAL
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request_time = time.time()


def reddit_get(url, timeout=10):
    """
    统一的 Reddit GET 请求方法。
    - 自动使用 OAuth2（如已配置）
    - 无凭证时直接跳过（不发请求、不触发熔断）
    - 自动限流（匿名 4s / OAuth 1s 间隔）
    - 自动重试 429（1 次）
    - 熔断器：连续 3 次 403 后停止本轮所有 Reddit 调用
    """
    global _consecutive_403, _circuit_open

    # 熔断器检查
    if _circuit_open:
        return None

    # 无凭证时直接跳过，避免必定 403 的匿名请求产生噪音
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        _set_last_request_meta(mode='skipped', token_state='missing_credentials',
                               request_state='skipped', status_code=None,
                               request_url=url, final_url='')
        return None

    _throttle()

    token = _get_oauth_token()

    if token:
        # 使用 OAuth2 认证请求 oauth.reddit.com
        oauth_url = url.replace('https://www.reddit.com/', 'https://oauth.reddit.com/')
        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': 'windows:gearup.monitors:v4.0 (by /u/GearUPMonitor)'
        }
        mode = 'oauth'
    else:
        # 无认证，用浏览器 User-Agent 降低被拦概率
        oauth_url = url
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        mode = 'anonymous'

    _set_last_request_meta(
        mode=mode,
        request_state='requesting',
        status_code=None,
        request_url=url,
        final_url=oauth_url,
    )

    try:
        response = requests.get(oauth_url, headers=headers, timeout=timeout)
        _set_last_request_meta(
            mode=mode,
            request_state='response',
            status_code=response.status_code,
            request_url=url,
            final_url=oauth_url,
        )

        # 429 限流时等待后重试一次
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 5))
            print(f"[Reddit] 被限流，等待 {retry_after} 秒后重试...")
            time.sleep(retry_after)
            _throttle()
            response = requests.get(oauth_url, headers=headers, timeout=timeout)
            _set_last_request_meta(
                mode=mode,
                request_state='response_after_retry',
                status_code=response.status_code,
                request_url=url,
                final_url=oauth_url,
            )

        if response.status_code == 403:
            _consecutive_403 += 1
            print(
                f"[Reddit] 403 Forbidden ({_consecutive_403}/{_CIRCUIT_BREAKER_THRESHOLD}) | mode={mode} | "
                f"token_state={get_last_reddit_request_meta().get('token_state')} | "
                f"url={oauth_url[:120]}"
            )
            if _consecutive_403 >= _CIRCUIT_BREAKER_THRESHOLD:
                _circuit_open = True
                print(f"[Reddit] 熔断器触发：连续 {_consecutive_403} 次 403，本轮停止所有 Reddit 调用")
        else:
            _consecutive_403 = 0  # 非 403 重置计数

        return response

    except Exception as e:
        _set_last_request_meta(
            mode=mode,
            request_state='request_exception',
            status_code=None,
            request_url=url,
            final_url=oauth_url,
        )
        print(f"[Reddit] 请求失败 {url}: {e}")
        return None

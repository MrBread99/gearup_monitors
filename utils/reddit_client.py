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
_REQUEST_INTERVAL = 1.0  # 每次请求最少间隔 1 秒


def _get_oauth_token():
    """获取 Reddit OAuth2 access token（Application Only 模式）"""
    global _access_token, _token_expires

    if _access_token and time.time() < _token_expires:
        return _access_token

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
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
            print("[Reddit] OAuth2 认证成功，限流提升至 600 请求/分钟")
            return _access_token
        else:
            print(f"[Reddit] OAuth2 认证失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"[Reddit] OAuth2 认证异常: {e}")
        return None


def _throttle():
    """全局限流：确保每次请求间隔至少 1 秒"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def reddit_get(url, timeout=10):
    """
    统一的 Reddit GET 请求方法。
    - 自动使用 OAuth2（如已配置）
    - 自动限流（1 秒间隔）
    - 自动重试 429（1 次）
    """
    _throttle()

    token = _get_oauth_token()

    if token:
        # 使用 OAuth2 认证请求 oauth.reddit.com
        oauth_url = url.replace('https://www.reddit.com/', 'https://oauth.reddit.com/')
        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': 'OSINT-Monitor/3.0'
        }
    else:
        # 无认证，使用原始 URL
        oauth_url = url
        headers = {'User-Agent': 'OSINT-Monitor/3.0'}

    try:
        response = requests.get(oauth_url, headers=headers, timeout=timeout)

        # 429 限流时等待后重试一次
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 5))
            print(f"[Reddit] 被限流，等待 {retry_after} 秒后重试...")
            time.sleep(retry_after)
            _throttle()
            response = requests.get(oauth_url, headers=headers, timeout=timeout)

        return response

    except Exception as e:
        print(f"[Reddit] 请求失败 {url}: {e}")
        return None

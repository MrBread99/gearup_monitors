"""
共享 Playwright 无头浏览器客户端
==========================================
提供懒初始化的 Chromium 浏览器单例，支持 playwright-stealth 隐身补丁
和 context 轮换（403 时清除 cookie/storage 重建干净会话）。

用法:
    from utils.playwright_client import pw_fetch, pw_close

    html, status = pw_fetch("https://example.com")
    # ... 解析 html ...
    pw_close()  # 进程结束前调用

设计原则:
- 整个进程生命周期只启动一个 Chromium 实例
- 403 时自动轮换 context（销毁 cookie/storage）并重试一次
- Playwright 未安装时所有调用静默返回 (None, 0)，不影响 fallback 逻辑
"""

import time
import random

# ==========================================
# 浏览器会话管理（进程级单例）
# ==========================================
_pw_driver = None
_pw_browser = None
_pw_context = None
_pw_page = None
_pw_available = None  # None=未检测, True/False=已确认


def _new_context():
    """创建统一配置的浏览器上下文。"""
    if _pw_browser is None:
        return None
    return _pw_browser.new_context(
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        extra_http_headers={
            'Accept-Language': 'en-US,en;q=0.9',
            'Upgrade-Insecure-Requests': '1',
        },
    )


def _new_stealth_page(context):
    """在指定 context 下创建 page，并尽量注入 stealth。"""
    page = context.new_page()
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        pass
    return page


def _rotate_context():
    """
    关闭当前 context/page，在同一 browser 上重建全新 context。
    用于 403 后清掉 cookie / storage / page state。
    """
    global _pw_context, _pw_page

    if _pw_browser is None:
        return None

    try:
        if _pw_page:
            _pw_page.close()
    except Exception:
        pass
    try:
        if _pw_context:
            _pw_context.close()
    except Exception:
        pass

    _pw_context = _new_context()
    if _pw_context is None:
        _pw_page = None
        return None

    _pw_page = _new_stealth_page(_pw_context)
    return _pw_page


def _ensure():
    """
    懒初始化 Playwright 浏览器（整个进程生命周期只启动一次）。
    返回 page 对象；不可用时返回 None。
    """
    global _pw_driver, _pw_browser, _pw_context, _pw_page, _pw_available

    if _pw_available is False:
        return None
    if _pw_page is not None:
        return _pw_page

    try:
        from playwright.sync_api import sync_playwright
        _pw_driver = sync_playwright().start()
        _pw_browser = _pw_driver.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
        )
        _pw_context = _new_context()
        _pw_page = _new_stealth_page(_pw_context)

        _pw_available = True
        print("[Playwright] 共享浏览器已启动")
        return _pw_page

    except Exception as e:
        print(f"[Playwright] 不可用，将使用 fallback: {e}")
        _pw_available = False
        return None


def pw_fetch(url, wait_until='networkidle', timeout=30000, wait_selector=None):
    """
    用 Playwright 访问 URL 并返回渲染后的 HTML。

    - 首次 403 时自动轮换 context（销毁 cookie/storage）重试一次
    - 每次请求前 2-4s 随机延迟
    - wait_selector: 可选 CSS 选择器，导航完成后额外等待该元素出现
      （用于 Cloudflare challenge 页面 — challenge 通过后真正内容才包含此元素）

    返回: (html_text, status_code)
        成功: (str, 200)
        失败: (None, status_code) 或 (None, 0)
    """
    page = _ensure()
    if page is None:
        return None, 0

    def _navigate_and_wait(p, target_url):
        """导航并等待内容，返回 (html | None, status)。"""
        response = p.goto(target_url, wait_until=wait_until, timeout=timeout)
        status = response.status if response else 0

        # Cloudflare challenge 通常返回 403 或 200（challenge 页面本身）
        # 如果指定了 wait_selector，无论 status 如何都尝试等待真正内容出现
        if wait_selector:
            try:
                p.wait_for_selector(wait_selector, timeout=15000)
                # selector 出现 = Cloudflare challenge 已通过，取真正内容
                return p.content(), 200
            except Exception:
                # selector 未出现 — challenge 未通过或页面结构变化
                if status == 200:
                    # 初始响应 200 但等不到内容 = challenge 页面
                    return None, 403
                return None, status

        if status == 200:
            return p.content(), 200
        return None, status

    try:
        time.sleep(random.uniform(2.0, 4.0))
        html, status = _navigate_and_wait(page, url)
        if html is not None:
            return html, status

        # 403: context 可能被标记，轮换后重试一次
        if status == 403 and _pw_browser is not None:
            print(f"[Playwright] 403，重建 context 重试: {url}")
            try:
                retry_page = _rotate_context()
                if retry_page is None:
                    return None, 403
                time.sleep(random.uniform(3.0, 6.0))
                html2, status2 = _navigate_and_wait(retry_page, url)
                if html2 is not None:
                    return html2, status2
                return None, status2
            except Exception as e:
                print(f"[Playwright] 重试失败: {e}")
                return None, 403

        return None, status

    except Exception as e:
        print(f"[Playwright] 访问 {url} 失败: {e}")
        return None, 0


def pw_close():
    """关闭 Playwright 浏览器（进程结束前调用）。"""
    global _pw_driver, _pw_browser, _pw_context, _pw_page, _pw_available
    try:
        if _pw_page:
            _pw_page.close()
        if _pw_context:
            _pw_context.close()
        if _pw_browser:
            _pw_browser.close()
        if _pw_driver:
            _pw_driver.stop()
    except Exception:
        pass
    _pw_driver = _pw_browser = _pw_context = _pw_page = None
    _pw_available = None


def pw_available():
    """检查 Playwright 是否可用（不触发初始化）。"""
    return _pw_available is not False

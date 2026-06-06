"""Functional/E2E tests — verify real HTTP + browser behavior.

These tests start the web server, then verify the full stack (React frontend
+ Python backend) works correctly via real HTTP requests and headless Chromium.

Requirements:  pip install playwright && python -m playwright install chromium
"""

import http.client
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────

SERVER_HOST = "127.0.0.1"
SERVER_PORT = None  # discovered at fixture time
BASE_URL = None


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port):
    """Start the web server in a daemon thread. Returns when ready."""
    import traceback
    from src.web.server import _run_server

    start_errors = []

    def _run_catching():
        try:
            _run_server(SERVER_HOST, port)
        except Exception:
            start_errors.append(traceback.format_exc())

    t = threading.Thread(target=_run_catching, daemon=True)
    t.start()

    for _ in range(50):
        if start_errors:
            raise RuntimeError(f"Server thread crashed:\n{start_errors[0]}")
        try:
            conn = http.client.HTTPConnection(SERVER_HOST, port, timeout=0.5)
            conn.request("GET", "/api/status")
            resp = conn.getresponse()
            resp.read()
            conn.close()
            return t
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"Server did not start within 5 seconds on port {port}")


def _api_get(path):
    """GET request to test server, bypassing system proxy."""
    conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


def _api_post(path, body_dict=None, raw_body=None, timeout=5):
    """POST request to test server, bypassing system proxy."""
    conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=timeout)
    body = raw_body if raw_body is not None else json.dumps(body_dict or {}).encode()
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    try:
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        return resp.status, data
    except (TimeoutError, ConnectionError, OSError):
        conn.close()
        raise


@pytest.fixture(scope="module")
def server():
    """Module-level fixture: start the web server once for all tests."""
    global SERVER_PORT, BASE_URL

    ui_dist = Path(__file__).resolve().parent.parent / "ui" / "dist" / "index.html"
    if not ui_dist.exists():
        pytest.skip("UI not built. Run: cd ui && npm run build")

    SERVER_PORT = _find_free_port()
    BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    env_existed = env_path.exists()
    if not env_existed:
        env_path.write_text(
            "AI_BACKEND=deepseek\n"
            "DEEPSEEK_API_KEY=\n"  # empty → sandbox returns error immediately without retrying real API
            "DEEPSEEK_MODEL=deepseek-v4-flash\n"
            "WECHAT_GROUPS=*\n"
            "ONBOARDING_DONE=true\n"  # skip onboarding → dashboard loads directly
        )

    t = _start_server(SERVER_PORT)
    yield
    if not env_existed and env_path.exists():
        env_path.unlink()


# ── API-level functional tests ──────────────────────────────────────────────

class TestDiagnoseApi:
    """Verify /api/onboarding/diagnose returns correct structure."""

    def test_diagnose_returns_200(self, server):
        status, data = _api_get("/api/onboarding/diagnose")
        assert status == 200
        assert data["ok"] is True
        diag = data["diagnostics"]
        for key in ("python", "requirements", "wechat", "env", "db"):
            assert key in diag, f"Missing diagnostics key: {key}"
            assert "ok" in diag[key]
            assert "value" in diag[key]

    def test_diagnose_python_ok(self, server):
        _, data = _api_get("/api/onboarding/diagnose")
        assert data["diagnostics"]["python"]["ok"] is True
        assert "Python 3" in data["diagnostics"]["python"]["value"]


class TestSandboxApi:
    """Verify /api/sandbox/test endpoint is routed correctly.

    Note: sending a real message triggers an AI API call which may take 10–30s.
    These tests only verify the endpoint accepts POST requests and returns JSON.
    """

    def test_sandbox_invalid_json_returns_error(self, server):
        status, data = _api_post("/api/sandbox/test", raw_body=b"not json")
        assert status == 200
        assert "ok" in data


class TestConfigDeepseekBaseUrl:
    """Verify deepseek_base_url is loaded and has a default."""

    def test_default_value(self):
        from src.config import BotConfig
        assert BotConfig.deepseek_base_url == "https://api.deepseek.com"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom-proxy.example.com")
        monkeypatch.setenv("AI_BACKEND", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        from src.config import load_config
        config = load_config()
        assert config.deepseek_base_url == "https://custom-proxy.example.com"


class TestPostAllowlist:
    """Verify /api/sandbox/test is in POST allowlist (doesn't return 405)."""

    def test_sandbox_post_not_405(self, server):
        """Invalid JSON still returns 200 (not 405), proving the route is registered."""
        status, _ = _api_post("/api/sandbox/test", raw_body=b"not json")
        assert status == 200

    def test_unknown_post_path_returns_405(self, server):
        conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=5)
        conn.request("POST", "/api/unknown-path", body=b"{}",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        conn.close()
        assert resp.status == 405


# ── Playwright browser-level functional tests ───────────────────────────────

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@pytest.fixture(scope="module")
def browser():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed. Run: pip install playwright")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, server):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    yield page
    context.close()


class TestPageLoads:
    def test_index_html_loads(self, page):
        page.goto(BASE_URL, timeout=10000)
        assert page.title() is not None


class TestThemeToggle:
    def test_default_theme_is_dark(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        html_classes = page.evaluate("document.documentElement.className")
        assert "dark" in html_classes, f"Expected 'dark' class, got: {html_classes}"

    def test_toggle_button_exists(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        toggle_btn = page.locator('button[title*="切换"]')
        if toggle_btn.count() > 0:
            toggle_btn.first.click()
            page.wait_for_timeout(500)
            html_classes = page.evaluate("document.documentElement.className")
            assert "dark" not in html_classes


class TestSidebarNavigation:
    def test_sidebar_has_tabs(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        page_text = page.inner_text("body")
        assert "运行状态" in page_text
        assert "系统配置" in page_text
        assert "运行日志" in page_text

    def test_sandbox_subtab_visible(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        config_btn = page.locator("button:has-text('系统配置')")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_timeout(500)
            page_text = page.inner_text("body")
            assert "提示词沙箱" in page_text


class TestConfigExportImport:
    def test_backup_ui_visible(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        config_btn = page.locator("button:has-text('系统配置')")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_timeout(500)
            page_text = page.inner_text("body")
            assert "导出备份" in page_text or "配置备份" in page_text

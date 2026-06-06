# macOS Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an experimental macOS WeChat backend and launcher without changing the existing Windows `wcdb` service flow.

**Architecture:** Keep `wcdb` as the default Windows backend. Add `mac_ui` as a separate `AbstractWeChatBackend` implementation driven by macOS Accessibility and AppleScript/JXA. Keep macOS dependencies in `requirements-macos.txt`.

**Tech Stack:** Python 3.10+, stdlib `subprocess`, AppleScript/JXA via `osascript`, existing HTTP server, existing React dashboard.

---

### Task 1: Backend Selection Tests

**Files:**
- Create: `tests/test_macos_adaptation.py`
- Modify: `src/bot.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest
from pathlib import Path

from src.config import BotConfig
from src.bot import Bot


class MacOSAdaptationTests(unittest.TestCase):
    def test_bot_selects_mac_ui_backend_without_importing_wcdb(self):
        cfg = BotConfig(
            ai_backend="deepseek",
            deepseek_api_key="sk-test",
            wechat_backend="mac_ui",
            wechat_groups="*",
            bot_display_name="群聊小助手",
        )

        backend = Bot(cfg)._create_wechat_backend(store=None)

        self.assertEqual(backend.__class__.__name__, "MacUIBackend")

    def test_requirements_macos_omits_windows_only_packages(self):
        text = Path("requirements-macos.txt").read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertNotIn("pywin32", lowered)
        self.assertNotIn("uiautomation", lowered)
        self.assertNotIn("comtypes", lowered)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `/opt/homebrew/bin/python3.12 -m unittest tests.test_macos_adaptation -v`

Expected: fails because `mac_ui` is unsupported and `requirements-macos.txt` does not exist.

- [ ] **Step 3: Implement minimal backend selection**

Add `src/wechat/mac_ui_backend.py` with a minimal `MacUIBackend` class implementing `start`, `send_text`, and `stop`. Update `src/bot.py` to instantiate it when `config.wechat_backend == "mac_ui"`.

- [ ] **Step 4: Add macOS requirements file**

Create `requirements-macos.txt` with cross-platform dependencies only.

- [ ] **Step 5: Verify tests pass**

Run: `/opt/homebrew/bin/python3.12 -m unittest tests.test_macos_adaptation -v`

Expected: both tests pass.

### Task 2: macOS UI Automation Adapter

**Files:**
- Modify: `src/wechat/mac_ui_backend.py`
- Modify: `tests/test_macos_adaptation.py`

- [ ] **Step 1: Write failing tests for visible text polling**

Add a fake automation object that returns visible text lines and captures sent messages. Assert that `MacUIBackend.poll_once(callback)` emits standardized messages once and deduplicates repeated lines.

- [ ] **Step 2: Run tests and verify failure**

Run: `/opt/homebrew/bin/python3.12 -m unittest tests.test_macos_adaptation -v`

Expected: fails because `poll_once` and parsing are missing.

- [ ] **Step 3: Implement minimal polling**

Implement `MacUIAutomation` for real macOS commands and `MacUIBackend.poll_once(callback)` for testable one-cycle polling.

- [ ] **Step 4: Verify tests pass**

Run: `/opt/homebrew/bin/python3.12 -m unittest tests.test_macos_adaptation -v`

Expected: all macOS adaptation tests pass.

### Task 3: macOS Launcher and Diagnostics

**Files:**
- Create: `desktop_mac.py`
- Modify: `src/web/server.py`
- Modify: `tests/test_macos_adaptation.py`

- [ ] **Step 1: Write failing tests for platform diagnostics**

Add a test that imports the diagnostics helper on macOS without requiring Windows-only modules.

- [ ] **Step 2: Implement launcher**

Create `desktop_mac.py` to start the existing Web server and open `http://127.0.0.1:7327` in the default browser.

- [ ] **Step 3: Make diagnostics platform-aware**

Move requirement checks into a helper that returns Windows checks on Windows and macOS checks on Darwin.

- [ ] **Step 4: Verify tests pass**

Run focused unit tests and ensure `desktop_mac.py` imports on macOS.

### Task 4: Documentation and Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document macOS experimental setup**

Add commands for Python 3.12 venv, `requirements-macos.txt`, `npm run build`, and `python desktop_mac.py`.

- [ ] **Step 2: Verify Windows default remains unchanged**

Search for default `WECHAT_BACKEND=wcdb`, unchanged `requirements.txt`, and unchanged `desktop.py` Windows launch path.

- [ ] **Step 3: Run verification**

Run:

```bash
/opt/homebrew/bin/python3.12 -m unittest tests.test_macos_adaptation -v
cd ui && npm run build
```

If full Windows packaging cannot run on macOS, record that limitation explicitly.


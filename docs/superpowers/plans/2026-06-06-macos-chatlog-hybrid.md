# macOS Chatlog Hybrid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS backend that reads WeChat messages from a local chatlog HTTP service and sends replies through the existing Accessibility automation.

**Architecture:** Keep `wcdb` as the Windows default and keep `mac_ui` as the UI-only fallback. Add `mac_hybrid` as a separate backend: `ChatlogClient` polls `GET /api/v1/new_messages?format=json&state=...`, normalizes rows into the existing message dict, and `MacUIAutomation` opens the chat and sends replies.

**Tech Stack:** Python stdlib `urllib.request`, existing `AbstractWeChatBackend`, existing `MacUIAutomation`, unit tests with fake clients.

---

### Task 1: Failing Tests

**Files:**
- Modify: `tests/test_macos_adaptation.py`

- [ ] Add tests that `WECHAT_BACKEND=mac_hybrid` creates `MacHybridBackend`.
- [ ] Add tests that `MacHybridBackend.poll_once()` turns chatlog rows into standardized messages, deduplicates them, and sends callback replies through Accessibility.
- [ ] Add tests that frontend and README expose the new backend label and setup notes.

### Task 2: Backend Implementation

**Files:**
- Create: `src/wechat/mac_hybrid_backend.py`
- Modify: `src/bot.py`
- Modify: `desktop_mac.py`

- [ ] Implement `ChatlogClient` with `get_new_messages(state, limit)`.
- [ ] Implement `MacHybridBackend` with stateful polling, group filtering, deduplication, message normalization, and send-through-Accessibility.
- [ ] Route `WECHAT_BACKEND=mac_hybrid` in `Bot._create_wechat_backend`.
- [ ] Default `desktop_mac.py` to `mac_hybrid`.

### Task 3: UI And Docs

**Files:**
- Modify: `ui/src/components/ConfigPanel.jsx`
- Modify: `ui/src/components/Dashboard.jsx`
- Modify: `README.md`

- [ ] Add a `mac_hybrid` option and dashboard label.
- [ ] Document the macOS read path: extract per-DB keys once, run chatlog service, then start `desktop_mac.py`.

### Task 4: Verification

**Commands:**
- `.venv/bin/python -m unittest tests.test_macos_adaptation tests.test_config tests.test_trigger tests.test_web_api -v`
- `cd ui && npm run build`
- `pyinstaller build.spec`

- [ ] Commit locally after tests/build/package attempt.

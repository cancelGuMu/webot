# Auto Chatlog Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source and packaged macOS starts automatically bring up the local chatlog service for `mac_hybrid`.

**Architecture:** Add a focused `MacChatlogServiceManager` that owns binary resolution, environment construction, process launch, and health waiting. `MacHybridBackend` delegates service startup to it before reading messages.

**Tech Stack:** Python stdlib, existing `ChatlogClient`, PyInstaller `build-macos.spec`, pytest/unittest.

---

### Task 1: Service Manager Tests

**Files:**
- Create: `src/wechat/mac_chatlog_service.py`
- Modify: `tests/test_macos_adaptation.py`

- [ ] Add tests for healthy no-op, launch env/log path, missing binary failure, and backend startup delegation.
- [ ] Run targeted tests and verify they fail because the module and delegation do not exist.

### Task 2: Service Manager Implementation

**Files:**
- Create: `src/wechat/mac_chatlog_service.py`
- Modify: `src/wechat/mac_hybrid_backend.py`

- [ ] Implement resource/app-home path resolution that works for source and PyInstaller.
- [ ] Implement `ensure_running()` with health no-op, binary lookup, `Popen`, and health wait.
- [ ] Wire `MacHybridBackend.start()` to call `ensure_running()` before `_prime_chatlog_state()`.
- [ ] Run targeted tests and verify they pass.

### Task 3: Packaging And Docs

**Files:**
- Modify: `build-macos.spec`
- Modify: `README.md`

- [ ] Bundle `tools/macos_chatlog/chatlog-alpha` into macOS app when present.
- [ ] Update README startup text so manual `start-chatlog` is optional, not part of normal launch.
- [ ] Run full tests, build frontend, run PyInstaller packaging, and commit.

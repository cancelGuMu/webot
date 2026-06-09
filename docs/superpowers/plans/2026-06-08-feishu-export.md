# Feishu Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual WeChat trigger that summarizes recent group chat and writes the result to Feishu/Lark Docs, Sheets, or Bitable.

**Architecture:** Keep Feishu as a focused integration package under `src/integrations/feishu`. `MessageRouter` detects export commands, reuses `MessageStore` and `AbstractSummarizer`, then delegates all remote writes to `FeishuExportService`.

**Tech Stack:** Python stdlib HTTP (`urllib.request`), SQLite-backed message store, existing summarizer abstractions, React config panel, PyInstaller.

---

### Task 1: Feishu Client And Config

**Files:**
- Create: `src/integrations/__init__.py`
- Create: `src/integrations/feishu/__init__.py`
- Create: `src/integrations/feishu/client.py`
- Modify: `src/config.py`
- Test: `tests/test_feishu_export.py`

- [ ] Write failing tests for loading Feishu config and token caching.
- [ ] Implement minimal config fields, validation, tenant token fetch, Sheets append, and Bitable create-record calls.
- [ ] Run `python -m pytest tests/test_feishu_export.py -v`.

### Task 2: Export Service

**Files:**
- Create: `src/integrations/feishu/exporter.py`
- Test: `tests/test_feishu_export.py`

- [ ] Write failing tests for command parsing, message window selection, summary formatting, and disabled/missing-target errors.
- [ ] Implement service methods for spreadsheet, bitable, and placeholder document mode.
- [ ] Run `python -m pytest tests/test_feishu_export.py -v`.

### Task 3: Router Integration

**Files:**
- Modify: `src/router.py`
- Test: `tests/test_feishu_export.py`

- [ ] Write failing router tests proving `@bot 同步到飞书` calls the export service and returns a user-facing reply.
- [ ] Inject optional export service into `MessageRouter` and route manual export commands before normal chat.
- [ ] Run `python -m pytest tests/test_feishu_export.py -v`.

### Task 4: Runtime Wiring And UI Config

**Files:**
- Modify: `src/bot.py`
- Modify: `src/web/server.py`
- Modify: `ui/src/App.jsx`
- Modify: `ui/src/components/ConfigPanel.jsx`
- Test: `tests/test_config.py`
- Test: `tests/test_web_api.py`
- Test: `tests/test_functional.py`

- [ ] Write failing config/API tests for Feishu fields round-tripping.
- [ ] Wire `FeishuExportService` in `Bot`, expose config through load/save/export/import, and add a Feishu config section in the UI.
- [ ] Run targeted backend tests and frontend build.

### Task 5: Verification, Packaging, Commit

**Files:**
- Modify: `build.spec` if hidden imports need adjustment.

- [ ] Run `python -m pytest tests/ -v`.
- [ ] Run `cd ui && npm run build && cd ..`.
- [ ] Run `pyinstaller build.spec`.
- [ ] Run targeted browser verification for config UI if local server is available.
- [ ] Commit all changes locally with a descriptive message and do not push.

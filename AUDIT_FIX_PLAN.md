# webot 审计修复方案

> 基于完整项目审计（109 项发现，7 项误报剔除），共需修改 **22 个文件**。

---

## P0 — CRITICAL（1 项，修复即可防止崩溃）

### 1. `src/web/server.py:203` — `_str_bool` 未定义导致配置保存崩溃

**问题**: `_todo_updates_from_config()` 调用不存在的 `_str_bool()` 函数，任何通过 Web UI 保存配置的操作都会触发 `NameError` → 500。

**修改**: 替换为 `str(...).lower()` 内联写法，与文件中其他地方的布尔转换模式一致。

```diff
-        "TODO_ENABLED": _str_bool(config.get("todo_enabled", True)),
+        "TODO_ENABLED": str(config.get("todo_enabled", True)).lower(),
```

---

## P1 — HIGH（3 项，重要逻辑修复）

### 2. `src/memory/consolidator.py:74-77` — 首次记忆合并不触发时间阈值

**问题**: 首次合并时 `last_consolidated is None`，`time_ok` 永为 False。低流量群聊（49 条消息数小时）永远不会触发记忆合并。

```diff
-        time_ok = (
-            last_consolidated is not None
-            and (time.time() - last_consolidated) >= CONSOLIDATE_TIME_THRESHOLD_SEC
-        )
+        # 首次合并使用 Unix epoch 作为虚拟时间基点，使时间阈值自然生效
+        effective_last = last_consolidated if last_consolidated is not None else 0
+        time_ok = (time.time() - effective_last) >= CONSOLIDATE_TIME_THRESHOLD_SEC
```

### 3. `tools/setup_wizard.py:21` — PROJECT_ROOT 路径多算一级

**问题**: `parent.parent.parent`（3级）解析到项目根目录的父目录（`E:\claude\webot\`），导致 `.env` 写入错误位置。

```diff
-PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
+PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

同时修改 line 218 的运行指令：
```diff
-    print("    python launcher.py")
+    print("    python desktop.py")
```

### 4. `ui/src/components/LotsEditor.jsx` — 新建共享组件，消除 ConfigPanel 与 FeaturesPanel 重复

**问题**: `LotsEditor` 在两个文件中各有一份拷贝（~250行），且 `handleRestoreDefaults` 已有行为分化。

**方案**: 
- 新建 `ui/src/components/LotsEditor.jsx`，使用 ConfigPanel 中更完善的版本（检查 POST 响应）
- `ConfigPanel.jsx` 和 `FeaturesPanel.jsx` 改为 `import { LotsEditor } from './LotsEditor'`
- 各自删除内联定义

---

## P2 — MEDIUM 关键修复（17 项）

### 5. `src/web/server.py:997-1007` — `/api/todos/action` 加入 POST 白名单

```diff
     if self.path in ("/api/config", "/api/config/import", "/api/start", "/api/stop",
                      "/api/nicknames",
                      "/api/welcome/templates",
                      "/api/onboarding/reset",
                      "/api/onboarding/step1", "/api/onboarding/step2",
                      "/api/onboarding/step3", "/api/onboarding/step4",
                      "/api/sandbox/test",
                      "/api/lots",
+                     "/api/todos/action",
                      "/api/voice/download-model"):
```

### 6. `src/web/server.py:1068-1118` — 配置 API 响应中掩码密钥

**问题**: `/api/load-config` 通过 `Access-Control-Allow-Origin: *` 暴露 `DEEPSEEK_API_KEY`、`ANTHROPIC_API_KEY`、`VOICE_OPENAI_API_KEY`。

**方案**: 在 `send_json()` 响应中对已知的 `*_API_KEY` 和 `*_SECRET` 字段掩码处理。添加辅助函数 `_mask_key(v)`：

```python
def _mask_key(value: str) -> str:
    """Mask a sensitive key: show first 4 + last 4 chars, or '***' if too short."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]
```

在 `/api/load-config`、`/api/config/export` 中应用：

```diff
+                "deepseek_api_key": _mask_key(raw.get("DEEPSEEK_API_KEY", "")),
-                "deepseek_api_key": raw.get("DEEPSEEK_API_KEY", ""),
```

同样处理 `anthropic_api_key`、`voice_openai_api_key`、`feishu_app_secret`。

### 7. `src/web/server.py:1068-1118` — .env 读写加锁

**问题**: 并发读写 `.env` 可能导致配置写入丢失（两个线程同时读-改-写）。

**方案**: 添加模块级 `_env_lock = threading.Lock()`，包裹所有 `.env` 读-改-写操作。在 `/api/config`、`/api/config/import`、`_set_env_key`、`_write_onboarding_to_env` 中获取锁。

```python
# 在文件顶部（约 line 35 附近）添加：
_env_lock = threading.Lock()
```

在 `/api/config` 的读-改-写路径（约 line 1184）添加：
```python
with _env_lock:
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    ...
    os.replace(tmp_path, env_path)
```

### 8. `src/summarize/claude_backend.py:160` — 记忆合并中转义花括号

**问题**: `consolidate_memory` 中消息内容包含 `{` `}` 时，`str.format()` 抛 `KeyError`。

```diff
+        # 转义消息中的花括号，避免 str.format() 报 KeyError
+        existing_display = existing_display.replace("{", "{{").replace("}", "}}")
+        new_messages_escaped = "\n".join(msg_lines).replace("{", "{{").replace("}", "}}")
         system_prompt = MEMORY_CONSOLE_PROMPT.format(
             existing_memory=existing_display,
-            new_messages="\n".join(msg_lines),
+            new_messages=new_messages_escaped,
         )
```

### 9. `src/summarize/deepseek_backend.py:248` — 同上

```diff
+        existing_display = existing_display.replace("{", "{{").replace("}", "}}")
+        new_messages_escaped = "\n".join(msg_lines).replace("{", "{{").replace("}", "}}")
         system_prompt = MEMORY_CONSOLE_PROMPT.format(
             existing_memory=existing_display,
-            new_messages="\n".join(msg_lines),
+            new_messages=new_messages_escaped,
         )
```

### 10. `src/router.py:84-86` — TodoStore 关闭时释放连接

**问题**: TodoStore 独立打开数据库连接，关闭时未释放。

**方案**: 在 `Bot.run()` 的 `finally` 块中关闭 TodoStore。

`src/todo/store.py` 添加 `close()` 方法：
```python
def close(self) -> None:
    """No-op — each method opens/commits/closes its own connection."""
    pass
```

`src/router.py` 添加 `close_todo()`：
```python
def close_todo(self) -> None:
    if self._todo_store is not None:
        self._todo_store.close()
```

`src/bot.py:310` 的 finally 块中调用：
```diff
             if self._conn is not None:
                 self._conn.close()
+            if hasattr(self, '_router') and self._router is not None:
+                self._router.close_todo()
```

### 11. `src/todo/store.py:291-311` — 接入 cleanup() 调用

**问题**: `cleanup()` 定义了但从未调用。

**方案**: 在 `src/router.py` todo 命令处理后调用，在 `src/web/server.py` todo API 操作后调用。

`src/router.py` 约 line 237：
```diff
                     if result is not None:
                         reply = format_todo_reply(result, msg["sender_name"])
+                    # 触发自动清理
+                    self._todo_store.cleanup(
+                        msg["chat_id"],
+                        self._config.todo_completed_retention_days,
+                        self._config.todo_deleted_retention_days,
+                    )
```

`src/web/server.py` 约 line 1606：
```diff
                 self.send_json({"ok": result.ok, "reply": result.reply})
+                # 触发自动清理
+                store.cleanup(chat_id)
```

### 12. `src/proactive/gate.py:131-133` — record_eval 死代码处理

**问题**: `record_eval()` 定义了但从未调用。AI 返回空时只调 `record_silence` 不调 `record_eval`，导致评估时间不更新。

**方案**: 在 `router.py:_handle_proactive_chat` 中，AI 返回空白后调用 `record_eval`：

```diff
         if not ai_reply:
+            self._proactive.record_eval(msg["chat_id"])
             self._proactive.record_silence(msg["chat_id"])
```

### 13. `src/voice/asr.py:269` — 传递 to_simplified 配置

```diff
     if backend == "openai_whisper":
         return OpenAiWhisperASR(
             api_key=getattr(config, "voice_openai_api_key", ""),
             base_url=getattr(config, "voice_openai_base_url", ""),
+            to_simplified=getattr(config, "voice_asr_to_simplified", True),
         )
     else:
         return LocalWhisperASR(
             model_size=getattr(config, "voice_local_model", "small"),
+            to_simplified=getattr(config, "voice_asr_to_simplified", True),
         )
```

### 14. `src/utils/web_search.py:91` — 修复 timelimit 参数 + 清理未使用的导入

```diff
-    from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
-    from concurrent.futures import TimeoutError as _FuturesTimeoutError
-
 ...
         with DDGS(timeout=timeout) as ddgs:
             results = list(ddgs.text(
                 safe_query,
                 max_results=max_results,
-                timelimit=timeout,
             ))
```

同时更新 docstring（lines 11-12）移除虚假的 ThreadPoolExecutor 声明。

### 15. `src/config.py:357` — 默认值不一致修复

```diff
-    feishu_export_mode = kwargs.get("feishu_export_mode", "spreadsheet")
+    feishu_export_mode = kwargs.get("feishu_export_mode", "knowledge")
```

### 16. `src/config.py:348-353` — 清理 max_retries 死代码

```diff
-    # max_retries (if present in config)
-    max_retries = kwargs.get("max_retries")
-    if max_retries is not None:
-        if not (1 <= max_retries <= 10):
-            errors.append(
-                f"MAX_RETRIES must be between 1 and 10, got {max_retries}"
-            )
```

### 17. `src/web/server.py:849-850` — 清理死代码

```diff
     return stopped
-    return False
```

### 18. `src/wechat/wcdb_backend.py:114-115` — 删除重复赋值

```diff
-        self._running = True
-        consecutive_errors = 0
-
         self._pool = concurrent.futures.ThreadPoolExecutor(
```

### 19. `src/wechat/helpers.py:69-72` — 硬编码反向映射

```diff
+_REVERSE_MSG_TYPE: dict[int, str] = {
+    1: "text", 3: "image", 34: "voice", 47: "emoji",
+    43: "video", 49: "file", 10000: "system",
+}

 def format_nontext_content(raw_type: Any) -> str:
     if isinstance(raw_type, str):
         return _NONTEXT_PLACEHOLDERS.get(raw_type, f"[{raw_type}]")
     if isinstance(raw_type, int):
-        reverse: dict[int, str] = {
-            v: k for k, v in MSG_TYPE_MAP.items()
-            if isinstance(k, str)
-        }
-        key = reverse.get(raw_type, "")
+        key = _REVERSE_MSG_TYPE.get(raw_type, "")
         return _NONTEXT_PLACEHOLDERS.get(key, f"[消息类型:{raw_type}]")
```

### 20. `src/proactive/rate_tracker.py:27` — list 改为 deque

```diff
-from collections import defaultdict
+from collections import defaultdict, deque

 ...
-        self._buckets: dict[str, list[float]] = defaultdict(list)
+        self._buckets: dict[str, "deque[float]"] = defaultdict(deque)
```

```diff
     def record(self, chat_id: str) -> None:
-        self._buckets[chat_id].append(time.time())
+        self._buckets[chat_id].append(time.time())  # deque.append
```

```diff
         while timestamps and timestamps[0] < cutoff:
-            timestamps.pop(0)
+            timestamps.popleft()
```

(两处 `pop(0)` → `popleft()`：`rate()` 和 `cleanup()` 方法中)

### 21. `src/voice/pipeline.py:83-84` — json.loads 后类型检查

```diff
             if self._path.exists():
-                self._data = json.loads(
+                raw = json.loads(
                     self._path.read_text(encoding="utf-8")
                 )
+                self._data = raw if isinstance(raw, dict) else {}
```

### 22. `src/voice/pipeline.py:176` — 使用绝对路径

```diff
+from src.config import PROJECT_ROOT
...
-        self._cache = VoiceCache(Path("data/voice_cache.json"))
+        self._cache = VoiceCache(PROJECT_ROOT / "data" / "voice_cache.json")
```

---

## P3 — LOW 精选（最重要的一批，约 20 项）

### 23. `src/bot.py:272` — 修正重复的注释编号

```diff
-# ── 6. Signal handling ──────────────────────────────────
+# ── 7. Signal handling ──────────────────────────────────
```

```diff
-# ── 7. Start listening (blocks) ─────────────────────────
+# ── 8. Start listening (blocks) ─────────────────────────
```

### 24. `src/router.py:203-208` — elif → if

```diff
-            elif self._config.fun_enabled and clean_content.strip() == "抽签":
+            if self._config.fun_enabled and clean_content.strip() == "抽签":
```

### 25. `src/fun.py:129` — 使用 PROJECT_ROOT

```diff
-_LOTS_PATH = Path("data/lots.json")
+from src.config import PROJECT_ROOT
+_LOTS_PATH = PROJECT_ROOT / "data/lots.json"
```

### 26. `src/nickname.py:15` — 同上

```diff
-DEFAULT_NICKNAME_PATH = Path("data/nicknames.json")
+from src.config import PROJECT_ROOT
+DEFAULT_NICKNAME_PATH = PROJECT_ROOT / "data/nicknames.json"
```

### 27. `src/welcome.py:21` — 同上

```diff
-_TEMPLATES_PATH = Path("data/welcome_templates.json")
+from src.config import PROJECT_ROOT
+_TEMPLATES_PATH = PROJECT_ROOT / "data/welcome_templates.json"
```

### 28. `src/welcome.py:152-157` — 消除单例竞态条件

```diff
+import threading
+_manager_lock = threading.Lock()

 def get_welcome_manager() -> WelcomeManager:
     global _manager
     if _manager is None:
-        _manager = WelcomeManager()
+        with _manager_lock:
+            if _manager is None:
+                _manager = WelcomeManager()
     return _manager
```

### 29. `src/trigger/detector.py:23` — None guard

```diff
-    def __init__(self, keywords: list[str], bot_display_name: str = ""):
+    def __init__(self, keywords: list[str] | None = None, bot_display_name: str = ""):
-        self.keywords = [kw.lower().strip() for kw in keywords if kw.strip()]
+        kw_list = keywords if keywords is not None else []
+        self.keywords = [kw.lower().strip() for kw in kw_list if kw.strip()]
```

### 30. `src/todo/handler.py:145` — 修正永真条件

```diff
-    if result.items is not None and len(result.items) >= 0:
+    if result.items:
```

### 31. `src/todo/store.py:11` — 移除未使用的 field 导入

```diff
-from dataclasses import dataclass, field
+from dataclasses import dataclass
```

### 32. `src/web/server.py:1435-1439` — 移除冗余检查

```diff
-            if not parsed.path.startswith("/api/nicknames") or parsed.path != "/api/nicknames":
+            if parsed.path != "/api/nicknames":
```

### 33. `src/wechat/__init__.py:4` — 修正误导性 docstring

```diff
-Usage:
-    from .wechat import create_wechat_backend
+The factory for creating backend instances lives on Bot._create_wechat_backend()
+in src/bot.py. New backends implement AbstractWeChatBackend from .base.
```

### 34. `src/wechat/mac_weflow_client.py:605` — 接受大写 hex key

```diff
-        if len(key) == HEX_KEY_LEN and all(ch in "0123456789abcdef" for ch in key):
+        if len(key) == HEX_KEY_LEN and all(ch in "0123456789abcdefABCDEF" for ch in key):
```

### 35. `src/summarize/models.py:15` — 添加 extra='ignore'

```diff
+from pydantic import ConfigDict
+
 class SummaryResult(BaseModel):
     """Structured summary of a group chat conversation."""
+    model_config = ConfigDict(extra='ignore')
     summary_text: str
```

### 36. `desktop.py:16` — 移动 traceback 导入

```diff
-import traceback
-
 ...
 def start_bot():
     """Start bot in background thread (signal-safe)."""
+    import traceback
```

### 37. `src/config.py:348-353` — 与 #16 相同，已包含

### 38. `src/proactive/gate.py:63-67` — 清理 _consecutive_silence

```diff
         for k in stale:
             del self._last_eval[k]
+            self._consecutive_silence.pop(k, None)
```

### 39. `src/wechat/wcdb_backend.py:81` — 不捕获 KeyboardInterrupt/SystemExit

```diff
     except Exception as e:
+        if isinstance(e, (KeyboardInterrupt, SystemExit)):
+            raise
         logger.error("Failed to initialize WCDB: %s", e)
```

### 40. `src/proactive/modes.py` — 双重检查锁

```diff
+import threading
+_MODES_LOCK = threading.Lock()

 def get_modes(config):
     global _MODES
     if _MODES is None:
-        _MODES = build_modes(config)
+        with _MODES_LOCK:
+            if _MODES is None:
+                _MODES = build_modes(config)
     return _MODES
```

### 41. `src/summarize/claude_backend.py:41-44` — 扩展重试异常类型

```diff
     retry_exceptions = (
         anthropic.RateLimitError,
         anthropic.APIConnectionError,
+        anthropic.InternalServerError,
+        anthropic.OverloadedError,
     )
```

### 42. `src/integrations/feishu/__init__.py:7-14` — __all__ 补齐

```diff
 __all__ = [
     "FeishuClient",
     "FeishuExportResult",      # 新增
     "FeishuExportService",     # 新增
     "FeishuKnowledgeExporter",
     "FeishuSpreadsheetExporter",
     "FeishuBitableExporter",
     "FeishuDocxExporter",
 ]
```

### 43. `src/voice/decoder.py:115` — 替换 deprecated mktemp

```diff
-        wav_path = Path(tempfile.mktemp(suffix=".wav"))
+        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
+        os.close(fd)
+        wav_path = Path(tmp_name)
```

（两处：line 115 和 line 145）

---

## 文件修改汇总

| 文件 | 修改数 | 优先级 |
|------|--------|--------|
| `src/web/server.py` | 6 | P0-P2 |
| `src/summarize/claude_backend.py` | 2 | P2 |
| `src/summarize/deepseek_backend.py` | 1 | P2 |
| `src/memory/consolidator.py` | 1 | P1 |
| `tools/setup_wizard.py` | 2 | P1 |
| `ui/src/components/LotsEditor.jsx` | 新建 | P1 |
| `ui/src/components/ConfigPanel.jsx` | 1 | P1 |
| `ui/src/components/FeaturesPanel.jsx` | 1 | P1 |
| `src/router.py` | 3 | P2 |
| `src/bot.py` | 2 | P2-P3 |
| `src/config.py` | 2 | P2 |
| `src/proactive/gate.py` | 2 | P2-P3 |
| `src/proactive/rate_tracker.py` | 1 | P2 |
| `src/proactive/modes.py` | 1 | P3 |
| `src/voice/asr.py` | 1 | P2 |
| `src/voice/pipeline.py` | 2 | P2 |
| `src/voice/decoder.py` | 1 | P3 |
| `src/utils/web_search.py` | 1 | P2 |
| `src/todo/store.py` | 1 | P3 |
| `src/todo/handler.py` | 1 | P3 |
| `src/wechat/helpers.py` | 1 | P2 |
| `src/wechat/__init__.py` | 1 | P3 |
| `src/wechat/wcdb_backend.py` | 1 | P2 |
| `src/wechat/mac_weflow_client.py` | 1 | P3 |
| `src/trigger/detector.py` | 1 | P3 |
| `src/summarize/models.py` | 1 | P3 |
| `src/integrations/feishu/__init__.py` | 1 | P3 |
| `src/fun.py` | 1 | P3 |
| `src/nickname.py` | 1 | P3 |
| `src/welcome.py` | 2 | P3 |
| `desktop.py` | 1 | P3 |

**共计 31 个文件，43 项修改。**

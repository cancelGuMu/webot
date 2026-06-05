# WeChat Bot — 全面审计报告

**日期**: 2026-06-05  
**分支**: master  
**审查文件**: 36 源文件 + build.spec + requirements.txt + UI 组件 + DLL 依赖  
**审查方式**: 23 代理并行审计 + 人工复核全部源码  

---

## 1. 总体健康评分: 7.0/10

项目是一个功能齐全的微信群聊 AI 机器人，包含：WCDB 原生数据库读取、AI 总结（Claude + DeepSeek）、主动发言、低俗内容过滤、群聊记忆整合、WebView2 桌面 UI + WebSocket 推送、多步引导向导。

架构分层清晰，代码文档详尽。但存在几个阻止"发布就绪"的问题。

---

## 2. CRITICAL — 发布前必须修复

### C1. 同步轮询导致头线阻塞
- **文件**: `src/wechat/wcdb_backend.py:96-111`, `src/bot.py:248-272`
- **描述**: `WcdbBackend.start()` 使用 while 循环轮询，一次 AI 调用（5-30秒）期间**所有群**的消息完全停止处理。bot.py 的设计注释已明确承认此问题但未做任何缓解。
- **影响**: 多个群聊时，一个群的总结请求会阻塞所有群的消息处理。

### C2. 循环依赖: web server ↔ key extraction
- **文件**: `src/web/server.py:187` ↔ `src/wechat/extract_key.py:72-76`
- **描述**: `server.py` 在函数内 import `extract_key`；`extract_key.py` 的 `_log_console()` 在 try 块中 import `web.server`。这只是因为 lazy import 才没炸。任何微小的重构都可能触发 ImportError。
- **影响**: 引导流程完全依赖这个脆弱的耦合。

### C3. Monkey-patch 控制后端生命周期
- **文件**: `src/web/server.py:400-407`
- **描述**: `_patch_bot_for_control(bot)` 替换 `Bot._create_wechat_backend` 方法。如果该方法改名或逻辑变化，Web API 的停止 bot 功能会静默失效。
- **影响**: 用户点击「停止」按钮无效，无错误提示。

### C4. 硬编码 DRM 补丁偏移
- **文件**: `src/wechat/wcdb_client.py:19-20, 27-49`
- **描述**: `PATCH_RVA = 0x6e1f6` 和 `EXPECTED_PATCH_BYTE = 0x02` 是硬编码的。微信更新 wcdb_api.dll 后直接崩溃，无版本检查，无优雅降级。

### C5. @mention 无频率限制
- **文件**: `src/router.py:89-224`
- **描述**: 主动发言有复杂的 4 层门控（速率→模式→间隔→概率），但 @mention 触发的总结和聊天没有任何频率限制。多人同时 @bot 会立即触发多个 LLM API 调用，一次 map-reduce 总结可能触发 5-10 次 API 调用。

---

## 3. BUG — 确认的运行时错误

### B1. `require_restart` 未定义 (NameError)
- **文件**: `src/wechat/extract_key.py:82,101`；调用方 `src/web/server.py:195`
- **描述**: `extract_wcdb_key()` 函数签名无参数，但第 101 行引用 `require_restart`（未定义变量），且 server.py 以 `extract_wcdb_key(require_restart=True)` 调用。
- **影响**: 运行时 NameError，引导流程 Step 1 必定崩溃。

### B2. KEY_MISSING 错误静默丢失
- **文件**: `src/wechat/wcdb_backend.py:75-77`, `ui/src/components/Dashboard.jsx:133`
- **描述**: WcdbClient.open() 抛出 KEY_MISSING 时，被 `except Exception: logger.error(...); return` 捕获，**未**将错误信息传给 `update_status()`。Dashboard 的「重新获取密钥」按钮永远不可达（死代码）。
- **影响**: 用户只看到「已停止」，不知道原因，无法恢复。

### B3. API Key 缺失时静默失败
- **文件**: `src/config.py:257-268`, `src/web/server.py:386`, `desktop.py:62`
- **描述**: `load_config()` 在 API Key 缺失时抛出 SystemExit，被 `except SystemExit:` 捕获但**未**传递错误信息给 UI。
- **影响**: Dashboard 显示「已停止」，用户完全不知道是 API Key 缺失导致的。

---

## 4. 高优先级问题

### H1. Web Server 全局可变状态 — 无生命周期
- **文件**: `src/web/server.py:266-304, 324-330, 283-293`
- **描述**: 8 个模块级可变全局变量（`_status`, `_clients`, `_onboarding_data`, `_step1_state`, `_bot_control` 等），无清理函数，线程安全依赖手动锁。

### H2. 微信窗口关闭后 Bot 死锁
- **文件**: `src/wechat/wcdb_backend.py:96-111`
- **描述**: 微信窗口关闭后，轮询循环遇错→指数退避→永远重试，但从不重新初始化 WCDB 客户端、HWND 或群组解析。

### H3. .env 解析逻辑重复
- **文件**: `src/config.py:46-66`, `src/web/server.py:26-88`
- **描述**: 两个模块独立搜索和解析 .env，逻辑相似但不相同，搜索顺序不同。

### H4. MessageRouter.handle() 过大
- **文件**: `src/router.py:89-224`
- **描述**: 135 行方法混合了：自消息过滤、持久化、记忆整合、低俗扫描、粘性提及、admin 命令、fun 命令、关键词触发、AI 聊天、主动聊天、后生成 guard、markdown 剥离。

### H5. 线程无协调关闭
- **文件**: `src/bot.py:47-51, 223-230`, `desktop.py:83-88`
- **描述**: 多个 daemon 线程创建，无中央注册，无 `threading.Event` 信号。daemon 线程被强制杀死可能导致 SQLite WAL 损坏。

---

## 5. EXE 打包完备度: 7.5/10

| 检查项 | 状态 | 备注 |
|--------|------|------|
| build.spec 完整性 | ✅ | 覆盖所有当前模块 |
| 二进制依赖 | ✅ | 6 个 DLL 全部打包 |
| WebView2 运行时 | ✅ | WebView2Loader.dll + WebBrowserInterop.x64.dll |
| UI dist 文件 | ✅ | ui/dist/ 包含 |
| requirements.txt | ⚠️ | **缺少 `webview`** |
| hiddenimports | ⚠️ | 缺少 `src.guard` (package)；新增 JSX 文件待验证 |
| 硬编码路径 | ❌ | `C:/Users/GuMu/...` 绝对路径 |
| data/ 目录 | ⚠️ | 运行时文件（messages.db 等 6MB+）被打包进 EXE |
| console 模式 | ✅ | console=False |
| icon | ✅ | logo.ico 存在 |

---

## 6. 功能完备度矩阵

| 功能 | 状态 | 备注 |
|------|------|------|
| WCDB 原生消息读取 | ✅ 完成 | DRM 补丁 ctypes |
| WCDB 密钥提取 (wx_key.dll) | ✅ 完成 | 自动 + 重启流程 |
| WCDB 密钥提取 (DLL 注入) | ✅ 完成 | 挂起进程注入 |
| AI 总结 — Claude | ✅ 完成 | 原生结构化输出 |
| AI 总结 — DeepSeek | ✅ 完成 | Tool-calling 兼容 |
| AI 聊天 (@mention) | ✅ 完成 | 聊天上下文 |
| 主动发言 | ✅ 完成 | 4 层门控系统 |
| 主动沉默退避 | ✅ 完成 | 指数退避 最高 16x |
| 粘性提及 | ✅ 完成 | TTL 过期 + 重注册 |
| 低俗内容过滤 (pre) | ✅ 完成 | 100+ 正则模式 |
| 低俗内容过滤 (post) | ✅ 完成 | 扫描 AI 输出 |
| 群聊记忆整合 | ✅ 完成 | 数量/时间触发 |
| 管理命令 | ✅ 完成 | 改名/删除昵称/刷新 |
| 趣味命令 (抽签) | ✅ 完成 | 加权随机 |
| 昵称解析 | ✅ 完成 | WCDB + 文件缓存 |
| Web Dashboard (React) | ✅ 完成 | Dashboard/Config/LogViewer/Onboarding |
| WebSocket 状态推送 | ✅ 完成 | 实时指标 |
| REST API | ✅ 完成 | /api/start, /stop, /config, /status, /logs, /onboarding/* |
| 多步引导向导 | ✅ 完成 | 密钥→群组→AI→功能 |
| WebView2 原生窗口 | ✅ 完成 | 浏览器回退 |
| 健康监控 | ✅ 完成 | 5 分钟心跳 + JSON + WebSocket |
| 联网搜索 | ✅ 完成 | DuckDuckGo + PII 脱敏 |
| @mention 频率限制 | ❌ 缺失 | 费用风险 |
| 微信崩溃自动恢复 | ❌ 缺失 | 死锁 |
| Headless CLI 模式 | ❌ 缺失 | 无法独立运行 |
| 自动化测试 | ❌ 0 个 | 无任何测试 |
| 日志轮转 | ❌ 缺失 | 无限增长 |

---

## 7. 建议修复优先级

### P0 — 发布前必须

1. 修复 `extract_key.py:101` 的 `require_restart` 未定义 bug
2. 修复 KEY_MISSING / API Key 错误的静默丢失
3. 给 @mention 加基本频率限制
4. 修复 build.spec 硬编码路径
5. 消除 server.py ↔ extract_key.py 循环依赖

### P1 — 高优先级

6. 消除 monkey-patch（server.py:400-407）
7. 拆分 MessageRouter.handle()
8. 添加协调关闭协议（threading.Event）
9. 统一 .env 解析逻辑
10. 审查并更新 build.spec hiddenimports

### P2 — 中优先级

11. SQLite 连接池或 context manager
12. 魔法数字提取到 BotConfig
13. 日志轮转 (RotatingFileHandler)
14. headless CLI 模式
15. Chat/System prompt 移到 prompts 模块

### P3 — 低优先级

16. 单元测试 (TriggerDetector, NicknameService, AdminCommandHandler, RateTracker, ProactiveGate)
17. 集成测试 (summarize pipeline + mock API)
18. 微信 DLL 版本检查
19. 拆分 ChatHandler / SummaryHandler / ProactiveHandler

---

## 8. 系统提醒 — 未提交的更改

当前工作区有大量未提交更改（20 个文件），在修复 bug 前建议先检查是否需要提交或暂存当前状态。

```
Modified: build.spec, desktop.py, src/bot.py, src/config.py,
          src/summarize/base.py, src/web/server.py,
          src/wechat/extract_key.py, src/wechat/helpers.py,
          src/wechat/wcdb_backend.py, src/wechat/wcdb_client.py,
          ui/dist/index.html, ui/index.html, ui/src/App.jsx,
          ui/src/components/ConfigPanel.jsx, Dashboard.jsx, LogViewer.jsx
Deleted:  launcher.py, tools/debug_sessions.py, tools/extract_key.py
New:     logo.png, src/wechat/native/, ui/public/,
         ui/src/components/Onboarding.jsx, OnboardingSteps.jsx,
         SharedComponents.jsx
```

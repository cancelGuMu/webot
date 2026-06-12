# CLAUDE.md

## 每次修改必须提交 Git

每次对代码的修改完成后，必须执行 `git add` 和 `git commit`，写清楚改动内容和原因。

**只提交到本地，不推送到远端。** 只有用户明确要求时才执行 `git push`。

```bash
git add -A
git commit -m "<描述做了什么，为什么>"
```

## 每次修改必须重新打包

前端代码或 Python 代码修改后，必须重新构建并打包 EXE，确保 `dist/webot.exe` 包含最新改动。

```bash
# 1. 构建前端（如有前端改动）
cd ui && npm run build

# 2. 打包 EXE
pyinstaller build.spec

# 3. 复制到正确位置（如 PyInstaller 输出到了 ui/dist/）
cp ui/dist/webot.exe dist/webot.exe
```

## 每次修改必须进行功能测试

每次修改完成后，必须运行完整测试套件，并对修改涉及的功能做针对性验证。

### 运行全部测试

```bash
python -m pytest tests/ -v
```

测试分两层：
- **单元测试** (`test_config.py`, `test_trigger.py`, `test_web_api.py`, `test_window_controller.py`) — 毫秒级，验证逻辑正确性
- **功能测试** (`test_functional.py`) — 启动真实 HTTP 服务器 + Playwright 无头浏览器，模拟用户点击操作

### 功能测试覆盖要求

每次修改后，必须验证被修改功能在实际浏览器中可用：

| 测试类别 | 覆盖功能 |
|---------|---------|
| API 端点 | Diagnose 返回结构、Sandbox 路由注册、POST allowlist、配置字段默认值 |
| 页面加载 | 前端 SPA 正常渲染，不出现空白页或连接错误 |
| 主题系统 | 暗色模式默认启用、Sun/Moon 切换按钮可用、localStorage 持久化 |
| 侧边栏导航 | 运行状态/系统配置/运行日志 标签页渲染、沙箱子标签可见 |
| 配置功能 | 导入导出按钮可见 |

### 手动验证清单

部分功能无法自动化测试（需要微信客户端或真实 API Key），修改这些模块后需手动验证：

1. **AI 聊天/总结** — 需要真实 API Key + 微信运行
2. **密钥提取** — 需要微信客户端运行
3. **主动发言** — 需要微信客户端 + 真实群聊
4. **昵称管理** — 需要 data/messages.db 有数据
5. **消息发送** — 需要微信窗口可见

## 项目概述

webot — 微信消息总结机器人，支持 WCDB 直读数据库、AI 自动总结/聊天/主动发言。

## 技术栈

- 后端：Python 3.13
- 前端：React + Vite (ui/)
- 桌面：PyWebView (WebView2)
- 打包：PyInstaller (build.spec)
- 数据库：WCDB (微信加密数据库)，通过 wcdb_api.dll + DRM patch 直读

## 项目结构

```
src/bot.py              - Bot 主控
src/config.py           - 配置加载 (.env)
src/router.py           - 消息路由
src/summarize/          - AI 后端 (DeepSeek/Claude)
src/wechat/             - 微信后端
  wcdb_backend.py       - WCDB 直读后端
  wcdb_client.py        - WCDB DLL 封装 (wcdb_api.dll)
  extract_key.py        - 密钥提取 (wx_key.dll Hook)
  window_controller.py  - 微信窗口操控 (键盘导航 + 消息发送)
  helpers.py            - 去重等工具
src/web/server.py       - Web UI 服务器 + WebSocket + API
src/memory/             - 聊天记忆
src/proactive/          - 主动发言
desktop.py              - 桌面入口 (PyWebView)
ui/                     - React 前端
lib/                    - DLL 文件
dist/                   - 打包输出
```

## 构建命令

```bash
# 构建前端
cd ui && npm run build

# 打包 EXE
pyinstaller build.spec

# 输出: dist/webot.exe
```

## 日志位置

- 源码运行: `data/bot.log`
- EXE 运行: `dist/data/bot.log`

## 代码参考手册同步更新

项目根目录下有 `CODEBASE_REFERENCE.md`（代码参考手册），包含所有函数、参数、调用关系的完整文档。每次修改代码后，**必须同步更新该文档**，确保文档与代码保持一致。

### 何时需要更新

| 代码变更 | 文档需要更新的内容 |
|---|---|
| 新增/删除函数 | §2 函数清单 — 添加/删除函数条目 |
| 修改函数签名（参数、返回值） | §2 函数清单 — 更新参数列表和返回值 |
| 新增/删除/重命名参数或环境变量 | §1 全局变量/参数清单 — 更新对应条目 |
| 修改函数间调用关系 | §3 模块间关系图 — 更新调用链 |
| 新增功能模块 | §4 功能模块展开 — 新增功能小节 |
| 修改现有功能逻辑 | §4 对应功能小节 — 更新调用链和参数表 |
| 新增/修改配置项 | §5 配置文件和环境变量 — 更新配置表 |
| 新增/修改数据库表结构 | §4 对应功能小节 — 更新 DDL 语句 |
| 新增源文件 | §1、§2、§3 — 添加新文件的函数和依赖关系 |

### 更新原则

1. **以代码为准**：文档必须反映代码的实际状态，不要凭记忆写
2. **函数签名精确匹配**：参数名、类型、默认值必须与源码一致
3. **调用链保持 ASCII 图的风格**：新增调用关系使用 `│ ├ └ →` 等字符
4. **交叉引用完整**：修改函数时，同时更新"调用了哪些函数"和"被哪些函数调用"
5. **环境变量表严格对齐**：名称、类型、默认值、定义位置、消费位置五列不缺

### 快速定位

修改代码时，用以下方式在文档中定位需要更新的位置：

```bash
# 查找某个函数在文档中的所有出现位置
grep "函数名" CODEBASE_REFERENCE.md

# 查找某个参数在文档中的所有出现位置
grep "参数名" CODEBASE_REFERENCE.md

# 查找某个文件在文档中的所有出现位置
grep "文件名" CODEBASE_REFERENCE.md
```

# CLAUDE.md

## 每次修改必须提交 Git

每次对代码的修改完成后，必须执行 `git add` 和 `git commit`，写清楚改动内容和原因。

```bash
git add -A
git commit -m "<描述做了什么，为什么>"
```

## 项目概述

WeChat Summarizer Bot — 微信消息总结机器人，支持 WCDB 直读数据库、AI 自动总结/聊天/主动发言。

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
src/guard/              - 不良内容检测
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

# 输出: dist/WeChatBot.exe
```

## 日志位置

- 源码运行: `data/bot.log`
- EXE 运行: `dist/data/bot.log`

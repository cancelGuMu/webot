# WeChatBot

> 微信群聊 AI 助手 —— 原生 WCDB 数据库直读，零 Hook 零注入，安全不封号。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.10%2B-green?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/AI-Claude%20%7C%20DeepSeek-purple?style=flat-square" alt="AI Backend" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/ui-React%20%2B%20Tailwind-cyan?style=flat-square&logo=react" alt="UI" />
</p>

---

## 概述

WeChatBot 是一个运行在 Windows 上的微信群聊 AI 机器人。它通过 **原生读取微信加密数据库（WCDB）** 获取消息，利用键盘模拟发送回复，全程不注入微信进程、不 Hook、不 Mock 网络协议。

你可以把它当成一个**群聊私人助理**：

- 错过几百条消息？对群里说一句「总结一下」，立刻得到结构化的话题摘要。
- 想查资料？**@机器人**提问，AI 结合联网搜索（DuckDuckGo，免费免 Key）回答。
- 群里聊嗨了？它能感知聊天节奏，主动接梗插话，自然不突兀。
- 有人开车？自动发出文明提醒，维护群聊氛围。

内置 **React + Tailwind CSS** 仪表盘，WebSocket 实时推送运行状态。支持打包为单个 EXE，双击即用。

---

## 核心特性

| 模块 | 功能 | 说明 |
|------|------|------|
| 🔍 **智能总结** | 关键词触发 / @提及触发 | 自动定位请求者的上一条消息，将之后的所有聊天内容交给 AI 生成结构化总结（按话题分类、参与人贡献、群聊气象） |
| 💬 **AI 对话** | @机器人 + 问题 | 支持 Claude 和 DeepSeek 两大模型后端，可选 DuckDuckGo 联网搜索增强，自动注入最近 10 分钟群聊上下文 |
| 📊 **三级 Map-Reduce** | 超长对话自动分块 | ≤200 条直接总结；200~2000 条 Map-Reduce；>2000 条多级 Map-Reduce（分块→批合并→最终合并），安全处理 999+ 条消息 |
| 🎯 **主动发言** | 5 种速率模式 × 概率门控 | SLEEP → QUIET → CASUAL → LIVELY → BURST，根据群聊活跃度自动切换，含指数退避沉默机制 |
| 🧠 **长期记忆** | 群聊记忆整合 | 每 20 条消息自动触发，以第一人称日记形式整合群聊印象，注入 AI 上下文，越聊越懂群 |
| 🛡️ **低俗内容过滤** | 前后双向检测 | 40+ 正则规则 + 15 种文明提醒模板，扫描用户消息和 AI 输出，双向保障 |
| 📌 **粘性提及** | 免重复 @ | 发送空 @ 后，下一条消息自动视为 @提及（60 秒 TTL，含防无限重注册保护） |
| 🏷️ **昵称系统** | wxid ↔ 显示名映射 | 支持手动管理（改名/删除）、WCDB 自动解析、JSON 文件持久化，AI 输出自动替换 |
| 🖥️ **Web 仪表盘** | React + Tailwind CSS | WebSocket 实时推送：运行状态、消息处理量、AI 延迟、数据库健康；配置面板；日志查看器 |
| ⚙️ **管理命令** | 管理员 wxid 鉴权 | 改名 / 删除昵称 / 刷新昵称 / 帮助 |
| 🎲 **趣味功能** | 抽签 | 5 级运势 + 加权概率 + 幽默解读 |
| 🔄 **异常恢复** | 自动重连 | 连续 5 次轮询失败自动重建 WCDB 连接、重新解析群组、重新查找微信窗口 |
| ⏱️ **健康监控** | 心跳 + 状态文件 | 每 30 秒推送仪表盘指标，每 5 分钟写入 JSON 状态文件 + 日志心跳 |
| 📦 **EXE 打包** | PyInstaller | 单个 EXE 包含所有依赖，WebView2 原生窗口，无控制台 |

---

## 与同类项目对比

| 维度 | WeChatBot | 其他微信机器人方案 |
|------|-----------|-------------------|
| **消息获取** | WCDB 原生数据库直读 | Hook 注入 / 网页协议模拟 / OCR |
| **封号风险** | 极低（只读数据库文件） | 中—高（注入 / 协议特征检测） |
| **外部依赖** | 零外部运行时依赖 | 常驻进程 / Docker / 特定微信版本 |
| **用户界面** | 原生桌面窗口 + Web 仪表盘 | 通常仅命令行 |
| **多群支持** | ✅ 自动发现或手动指定 | 部分支持 |
| **AI 后端** | Claude / DeepSeek 双选 | 通常单一 |
| **消息发送** | Win32 键盘模拟 | 协议发送 / Hook / OCR 点击 |

---

## 快速开始

### 前置条件

- **Windows 10 或 11**
- **Python 3.10+**（仅源码运行需要）
- **微信桌面版** 已登录

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/cancelGuMu/wechat-group-bot/releases) 下载 `WeChatBot.exe`，双击运行。

首次运行会弹出配置向导，引导你完成：密钥提取 → 机器人身份 → AI 后端 → 功能开关，四步即可开始使用。

### 方式二：从源码运行

```bash
git clone https://github.com/cancelGuMu/wechat-group-bot.git
cd wechat-group-bot
pip install -r requirements.txt
python desktop.py
```

### 方式三：自行打包

```bash
pip install pyinstaller
pyinstaller build.spec
# 输出: dist/WeChatBot.exe
```

---

## 配置参考

所有配置通过项目根目录的 `.env` 文件管理。首次运行会自动从 `.env.example` 创建模板。完整配置项如下：

### AI 后端

```env
# 后端选择：claude 或 deepseek
AI_BACKEND=deepseek

# DeepSeek（AI_BACKEND=deepseek 时生效）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek-v4-flash          # v4-flash (推荐) | v4-pro (1M 上下文旗舰)

# Claude（AI_BACKEND=claude 时生效）
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
SUMMARIZE_MODEL=claude-haiku-4-5-20251001 # haiku (快速廉价) | sonnet (更高质量)
```

### 机器人身份

```env
# 机器人在群里的显示名（用于 @ 检测）
BOT_DISPLAY_NAME=群聊小助手

# 管理员 wxid（可执行管理命令）
ADMIN_WXID=

# 监控的群聊，逗号分隔。留空 / * = 自动发现所有群聊
WECHAT_GROUPS=
```

### 功能开关

```env
# 主动发言：机器人根据聊天节奏自动插话
PROACTIVE_ENABLED=false

# 低俗内容过滤：前后双向检测
VULGAR_GUARD_ENABLED=true

# 粘性提及：空 @ 后下一条消息自动作为 @处理
STICKY_MENTION_ENABLED=true

# 联网搜索增强：DuckDuckGo 免费搜索
ENABLE_WEB_SEARCH=true
```

### 触发关键词

```env
# 逗号分隔，发送这些关键词触发总结（不区分大小写）
TRIGGER_KEYWORDS=总结一下,之前发了什么,错过了什么,summarize,what did i miss,聊天总结,帮我总结,前面说了什么,说了啥,发生了什么
```

### 调优参数

```env
# 轮询间隔（秒），默认 1.0，增大可降低 CPU 占用
POLL_INTERVAL_SEC=1.0

# 去重窗口（秒），同一群聊两次触发之间的最小间隔
DEDUP_WINDOW_SEC=60

# 总结最大消息数（群聊 999+ 时可增大）
MAX_MESSAGES_FOR_SUMMARY=5000

# Map-Reduce 每块消息数
CHUNK_SIZE=400

# 兜底总结窗口（小时），请求者无历史消息时使用
FALLBACK_WINDOW_HOURS=8
```

### 主动发言调参

```env
# 速率计算窗口（秒）
PROACTIVE_RATE_WINDOW_SEC=120

# 各模式速率阈值（条/分钟），必须严格递增
PROACTIVE_RATE_QUIET=1.5    # SLEEP → QUIET 边界
PROACTIVE_RATE_CASUAL=4.0   # QUIET → CASUAL 边界
PROACTIVE_RATE_LIVELY=6.5   # CASUAL → LIVELY 边界
PROACTIVE_RATE_BURST=8.5    # LIVELY → BURST 边界
```

建议先用 `python tools/analyze_chat_rhythm.py` 分析群聊节奏后再校准。

### 日志

```env
LOG_LEVEL=INFO
LOG_FILE=data/bot.log
```

---

## 使用指南

### 基础用法

| 操作 | 方式 |
|------|------|
| **群聊总结** | 发送 `总结一下` / `前面说了什么` / `聊天总结` 等关键词 |
| **AI 问答** | `@机器人 <你的问题>` |
| **空 @ 粘性** | 发送 `@机器人`（不带文字），60 秒内发送你的问题即自动关联 |
| **Web 仪表盘** | 启动后自动打开 `http://127.0.0.1:7327` |

### 管理命令

发送 `@机器人 <命令>`（需配置 `ADMIN_WXID`）：

| 命令 | 说明 |
|------|------|
| `改名 wxid 新昵称` | 为指定 wxid 绑定昵称 |
| `删除昵称 wxid` | 删除指定 wxid 的昵称 |
| `刷新昵称` | 从 JSON 文件重新加载昵称缓存 |
| `帮助` / `help` / `命令` | 查看可用命令列表 |

### 主动发言模式详解

开启 `PROACTIVE_ENABLED=true` 后，机器人根据群聊消息速率自动切换行为模式：

| 模式 | 速率阈值 | 评估间隔 | 回复概率 | 最大字数 | 上下文条数 | 行为 |
|------|----------|----------|----------|----------|------------|------|
| SLEEP | < 1.5/min | — | 0% | 0 | 0 | 完全沉默 |
| QUIET | 1.5~4.0 | 300s | 10% | 30 | 30 | 偶尔参与，低频克制 |
| CASUAL | 4.0~6.5 | 120s | 25% | 50 | 50 | 正常聊天节奏 |
| LIVELY | 6.5~8.5 | 60s | 50% | 35 | 60 | 活跃参与 |
| BURST | > 8.5 | 30s | 70% | 20 | 80 | 高频插话，极短回复 |

当 AI 连续多次选择沉默时，系统会指数退避（最高 16× 评估间隔），避免在冷场期浪费 API 调用。

---

## 项目结构

```
wechatbot/
├── desktop.py                    # 桌面应用入口（WebView2 原生窗口）
├── build.spec                    # PyInstaller 打包配置
├── requirements.txt              # Python 依赖
├── .env.example                  # 环境变量模板
├── .env                          # 用户配置（不入 git）
├── logo.png                      # 项目 Logo
│
├── src/                          # Python 源码
│   ├── main.py                   # CLI 入口（python -m src.main）
│   ├── bot.py                    # Bot 编排器（组件初始化、生命周期管理）
│   ├── config.py                 # 配置加载与校验（.env → BotConfig）
│   ├── router.py                 # 消息路由器（分发到总结/AI对话/主动发言/管理命令）
│   ├── admin.py                  # 管理命令处理（改名、删除昵称等）
│   ├── fun.py                    # 趣味功能（抽签）
│   ├── nickname.py               # 昵称服务（wxid ↔ 显示名映射）
│   │
│   ├── summarize/                # AI 总结模块
│   │   ├── __init__.py           # 工厂函数 create_summarizer()
│   │   ├── base.py               # 抽象基类 + 对话/主动发言提示词
│   │   ├── claude_backend.py     # Claude 后端（Anthropic SDK + Pydantic 结构化输出）
│   │   ├── deepseek_backend.py   # DeepSeek 后端（OpenAI SDK + Tool Calling）
│   │   ├── models.py             # Pydantic 数据模型（SummaryResult）
│   │   └── prompts.py            # 提示词模板（总结/分块/合并/记忆整合）
│   │
│   ├── wechat/                   # 微信集成模块
│   │   ├── base.py               # 抽象后端接口（AbstractWeChatBackend）
│   │   ├── wcdb_backend.py       # WCDB 后端实现（消息轮询、群组解析、消息标准化）
│   │   ├── wcdb_client.py        # WCDB 原生客户端（ctypes 调用 wcdb_api.dll）
│   │   ├── extract_key.py        # 密钥提取（wx_key.dll Hook + 微信重启流程）
│   │   ├── window_controller.py  # 微信窗口控制（查找/激活/导航/发送消息）
│   │   ├── keyboard.py           # 键盘模拟（keybd_event 封装）
│   │   └── helpers.py            # 共享工具（消息类型映射、去重集合）
│   │
│   ├── proactive/                # 主动发言模块
│   │   ├── gate.py               # 4 层门控（速率→模式→间隔→概率）
│   │   ├── modes.py              # 5 种速率模式定义与查找
│   │   ├── rate_tracker.py       # 滑动窗口消息速率追踪
│   │   └── sticky.py             # 粘性提及追踪器
│   │
│   ├── memory/                   # 群聊记忆模块
│   │   └── consolidator.py       # 记忆整合触发器（阈值检查 + 异步执行）
│   │
│   ├── guard/                    # 安全过滤模块
│   │   └── vulgar_detector.py    # 低俗内容检测（40+ 正则 + 双语种）
│   │
│   ├── trigger/                  # 触发检测模块
│   │   └── detector.py           # 关键词匹配 + @提及检测
│   │
│   ├── db/                       # 数据库模块
│   │   ├── schema.py             # DDL 建表语句 + 初始化
│   │   └── store.py              # MessageStore（增删改查 + 记忆操作）
│   │
│   ├── web/                      # Web 服务模块
│   │   └── server.py             # HTTP + WebSocket 服务器（零第三方依赖）
│   │
│   └── utils/                    # 工具模块
│       ├── logging_config.py     # 日志配置
│       └── web_search.py         # DuckDuckGo 联网搜索（含 PII 脱敏）
│
├── ui/                           # React 前端
│   ├── src/
│   │   ├── App.jsx               # 应用入口（路由、WebSocket 连接）
│   │   └── components/
│   │       ├── Dashboard.jsx     # 运行状态仪表盘
│   │       ├── ConfigPanel.jsx   # 系统配置面板
│   │       ├── LogViewer.jsx     # 运行日志查看器
│   │       ├── Onboarding.jsx    # 新用户引导流程
│   │       ├── OnboardingSteps.jsx # 引导步骤组件
│   │       └── SharedComponents.jsx # 共享 UI 组件
│   ├── dist/                     # 构建产物（供 EXE 打包使用）
│   └── index.html                # HTML 入口
│
├── lib/                          # 二进制依赖（不入 git）
│   ├── wcdb_api.dll              # WCDB 数据库读取接口（ctypes 调用）
│   ├── WCDB.dll                  # WCDB 运行时库
│   ├── wx_key.dll                # 微信密钥提取 Hook
│   ├── MSVCP140.dll              # VC++ 运行时
│   ├── VCRUNTIME140.dll          # VC++ 运行时
│   └── VCRUNTIME140_1.dll        # VC++ 运行时
│
├── data/                         # 运行时数据（不入 git）
│   ├── messages.db               # 消息持久化数据库（SQLite WAL）
│   ├── bot_status.json           # 健康状态 JSON
│   ├── nicknames.json            # 昵称映射文件
│   └── bot.log                   # 运行日志
│
├── image/                        # 项目图片资源
│   └── logo_assets/              # Logo 多尺寸素材
│
└── tools/                        # 辅助脚本
    └── analyze_chat_rhythm.py    # 群聊节奏分析工具
```

---

## 技术架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      desktop.py (入口)                       │
│  ┌─────────────────┐  ┌──────────────────────────────────┐  │
│  │   WebView2 窗口   │  │  Web Server (HTTP + WebSocket)  │  │
│  │  (Edge Chromium) │  │  http://127.0.0.1:7327          │  │
│  └────────┬────────┘  └────────────┬─────────────────────┘  │
│           │                        │                         │
│           └────────┬───────────────┘                         │
│                    ▼                                         │
│           ┌──────────────┐                                  │
│           │   Bot 编排器   │                                  │
│           └──────┬───────┘                                  │
│                  │                                           │
│     ┌────────────┼────────────┐                             │
│     ▼            ▼            ▼                             │
│  ┌──────┐  ┌──────────┐  ┌─────────┐                       │
│  │Config│  │ Message  │  │ Health  │                       │
│  │ 加载  │  │ Router   │  │ Monitor │                       │
│  └──────┘  └────┬─────┘  └─────────┘                       │
│                 │                                            │
│     ┌───────────┼───────────┐                               │
│     ▼           ▼           ▼                               │
│  ┌──────┐  ┌─────────┐  ┌──────────┐                       │
│  │Summary│  │AI Chat  │  │Proactive │                       │
│  │Handler│  │Handler  │  │ Handler  │                       │
│  └──┬───┘  └────┬────┘  └────┬─────┘                       │
│     │           │            │                               │
│     └───────────┼────────────┘                               │
│                 ▼                                            │
│     ┌─────────────────────┐                                 │
│     │  AI Backend Factory  │                                 │
│     │  ├─ ClaudeSummarizer │                                 │
│     │  └─ DeepSeekSummarizer│                                │
│     └──────────┬──────────┘                                 │
│                │                                              │
│  ┌─────────────┴─────────────┐                              │
│  ▼                           ▼                              │
│ ┌─────────────────┐  ┌──────────────────┐                   │
│ │ WeChat Backend   │  │  MessageStore    │                   │
│ │ ├─ WcdbBackend  │  │  (SQLite WAL)    │                   │
│ │ │  ├─ WcdbClient│  └──────────────────┘                   │
│ │ │  └─ WindowCtrl│                                          │
│ │ └─ [extensible] │                                          │
│ └────────┬────────┘                                          │
│          ▼                                                   │
│ ┌──────────────────┐                                        │
│ │ wcdb_api.dll     │  ← 原生读取 WeChat session.db          │
│ │ (ctypes 调用)    │                                        │
│ └──────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
微信消息 ──WCDB读取──▶ WcdbBackend._poll_cycle()
                          │
                          ├─ 去重 (DedupSet)
                          ├─ 标准化 (_standardize)
                          │
                          ▼
                   ThreadPoolExecutor
                    (fire-and-forget)
                          │
                          ▼
                   MessageRouter.handle()
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    总结请求          AI 对话          主动发言
    (关键词匹配)     (@提及)        (速率门控通过)
          │               │               │
          ▼               ▼               ▼
    Summarizer      Summarizer       Summarizer
    .summarize()    .chat()          .proactive_chat()
          │               │               │
          ▼               ▼               ▼
    Anthropic SDK    OpenAI SDK      同 chat()
    或 OpenAI SDK    (DeepSeek)
          │               │               │
          ▼               ▼               ▼
    生成回复 ──────── 生成回复 ─────── 生成回复（或空白）
          │               │               │
          └───────────────┼───────────────┘
                          │
                          ▼
                  VulgarDetector (后置扫描)
                          │
                          ▼
                 NicknameService (wxid → 昵称)
                          │
                          ▼
                Markdown 剥离 (WeChat 不支持)
                          │
                          ▼
              WeChatWindowController.send_to_chat()
                (Ctrl+F → 搜索群 → Ctrl+V → Enter)
```

### 关键技术决策

| 决策 | 理由 |
|------|------|
| **WCDB 直读而非 Hook** | 不注入微信进程，封号风险极低。只需要文件读权限。 |
| **键盘模拟发送而非协议** | 微信协议加密且频繁变动，模拟键盘是最稳定可靠的发送方式。 |
| **ThreadPoolExecutor 解耦轮询与回复** | 单群 AI 调用（5~30 秒）不会阻塞其他群的消息轮询。 |
| **SQLite WAL 模式** | 支持读写并发，适合高频消息写入 + 低频查询的场景。 |
| **零依赖 Web 服务器** | `http.server` + 自实现 WebSocket，减少打包体积和依赖冲突。 |
| **三级 Map-Reduce** | 单次调用适配 200 条，多级处理安全覆盖 999+ 条消息。 |
| **指数退避沉默机制** | AI 连续选择沉默时自动降低主动发言频率，避免浪费 API 调用。 |
| **Pydantic 结构化输出（Claude）** | 使用 `client.messages.parse()` 原生解析，比 Tool Calling 更可靠。 |
| **Tool Calling 兼容（DeepSeek）** | DeepSeek 无原生结构化输出，用 Tool Calling + 三种回退策略实现兼容。 |

---

## 依赖说明

### Python 依赖

| 包名 | 用途 |
|------|------|
| `python-dotenv` | .env 配置文件解析 |
| `anthropic` | Claude API 客户端 |
| `openai` | DeepSeek API 客户端（OpenAI 兼容接口） |
| `ddgs` / `duckduckgo_search` | 联网搜索（DuckDuckGo，免费免 Key） |
| `pydantic` | 数据模型（SummaryResult 结构化输出） |
| `uiautomation` | Windows UI Automation（窗口标题验证备用方案） |
| `pywin32` | Win32 API 封装（窗口查找、键盘模拟、剪贴板） |
| `comtypes` | COM 类型库（pywin32 依赖） |
| `pywebview` | WebView2 原生桌面窗口 |
| `Pillow` | 图片处理（微信窗口白屏检测） |
| `psutil` | 进程监控 |
| `pyperclip` | 剪贴板操作 |

### 二进制依赖

| 文件 | 来源 | 用途 |
|------|------|------|
| `wcdb_api.dll` | 本项目 | WCDB 数据库读取接口（ctypes 调用） |
| `WCDB.dll` | 本项目 | WCDB 数据库引擎运行时 |
| `wx_key.dll` | 本项目 | 微信内存密钥提取 Hook（ctypes 调用） |
| `MSVCP140.dll` | Microsoft | Visual C++ 2015-2022 运行时 |
| `VCRUNTIME140.dll` | Microsoft | Visual C++ 运行时 |
| `VCRUNTIME140_1.dll` | Microsoft | Visual C++ 运行时 |

### 前端依赖

| 框架/库 | 用途 |
|------|------|
| React 18 | UI 框架 |
| Tailwind CSS 3 | 样式系统 |
| Framer Motion | 页面过渡动画 |
| Phosphor Icons | 图标库 |

---

## 开发指南

### 环境搭建

```bash
# 克隆仓库
git clone https://github.com/cancelGuMu/wechat-group-bot.git
cd wechat-group-bot

# 安装 Python 依赖
pip install -r requirements.txt

# 构建前端（如需修改 UI）
cd ui
npm install
npm run build
cd ..

# 复制 .env 模板并编辑
copy .env.example .env
notepad .env  # 填入 API Key 等配置

# 启动
python desktop.py
```

### 打包

```bash
pyinstaller build.spec
# 输出: dist/WeChatBot.exe
```

`build.spec` 已配置好所有二进制依赖和隐式导入。打包前请确保：
- `ui/dist/` 已构建（`cd ui && npm run build`）
- `lib/*.dll` 文件已就位
- 已安装 `pywebview`

### 添加新的 AI 后端

1. 在 `src/summarize/` 创建新文件（如 `openai_backend.py`）
2. 继承 `AbstractSummarizer` 并实现所有抽象方法
3. 在 `src/summarize/__init__.py` 的 `create_summarizer()` 添加分支

### 添加新的微信后端

1. 在 `src/wechat/` 创建新文件
2. 继承 `AbstractWeChatBackend` 并实现 `start()`, `send_text()`, `stop()`
3. 在 `src/bot.py` 的 `_create_wechat_backend()` 添加分支

### 代码风格

- Python: 4 空格缩进，Google 风格 docstring
- JSX: 2 空格缩进，函数组件 + Hooks
- 提交信息: 中文或英文，简洁描述变更内容

---

## 常见问题

<details>
<summary><strong>DLL 文件从哪里来？</strong></summary>

`wcdb_api.dll` 和 `WCDB.dll` 提取自微信客户端，由本项目内置的 `wx_key.dll` 完成数据库密钥提取，全程不需要任何第三方工具。所有 DLL 文件在打包时自动包含进 EXE。

</details>

<details>
<summary><strong>会被封号吗？</strong></summary>

WeChatBot 只读取微信本地的加密数据库文件，通过键盘模拟发送消息。整个过程：
- **不注入**微信进程（无 DLL 注入，无代码修改）
- **不 Hook**微信函数
- **不模拟**微信网络协议

这是一种非常安全的只读方式，目前没有已知的封号案例。但任何第三方工具都有理论风险，请自行评估。

</details>

<details>
<summary><strong>支持哪些 AI 模型？</strong></summary>

- **DeepSeek**：`deepseek-v4-flash`（推荐，极速低价，1M 上下文）、`deepseek-v4-pro`（旗舰）
- **Claude**：`claude-haiku-4-5-20251001`（快速廉价）、`claude-sonnet-4-5-20250929`（更高质量）

切换模型只需修改 `.env` 中的 `AI_BACKEND` 和对应 Model 配置。

</details>

<details>
<summary><strong>API 调用费用高吗？</strong></summary>

不高。默认使用 DeepSeek V4 Flash（约 ¥0.001/千 tokens），普通群聊一天的总结和对话费用通常不到 ¥0.10。你也可以切换为 Claude Haiku，同样以低成本和低延迟著称。联网搜索使用 DuckDuckGo，完全免费。

</details>

<details>
<summary><strong>如何停止机器人？</strong></summary>

点击仪表盘中的停止按钮，或在终端按 `Ctrl+C`。

</details>

<details>
<summary><strong>微信窗口最小化后能正常工作吗？</strong></summary>

消息读取（WCDB 数据库）不受影响。消息发送需要微信窗口可见并处于前台——发送时会自动尝试激活微信窗口。建议不要最小化微信窗口，或将其放在虚拟桌面上保持打开状态。

</details>

<details>
<summary><strong>支持 macOS / Linux 吗？</strong></summary>

目前仅支持 Windows。macOS 和 Linux 版本的微信使用了完全不同的数据库加密方案，暂无支持计划。

</details>

<details>
<summary><strong>消息去重 / 幂等性如何保证？</strong></summary>

每个消息通过 `(chat_id, sender_id, content, timestamp)` 生成 MD5 作为唯一 ID。`DedupSet`（内存）和 `UNIQUE` 约束（数据库）双重保障。DedupSet 超过 5000 条自动裁剪到最近一半。

</details>

<details>
<summary><strong>机器人会漏消息吗？</strong></summary>

标准轮询间隔 1 秒，每次拉取每个群最近 50 条消息。在正常群聊节奏下不会漏消息。如果群聊在 1 秒内产生超过 50 条消息（极少见），可能会有遗漏，可通过减小 `POLL_INTERVAL_SEC` 缓解。

</details>

---

## 安全与隐私

- **API Key** 存储在本地 `.env` 文件中，不会上传。
- **联网搜索**使用 DuckDuckGo，查询前自动脱敏：手机号、邮箱、身份证号、长数字序列统一替换为占位符。
- **消息数据**全部存储在本地 `data/messages.db`（SQLite），不经过任何远程服务器（AI API 调用除外）。
- **AI 调用**仅发送必要的上下文消息，不传输完整聊天历史。

---

## 路线图

- [ ] Headless CLI 模式（无 GUI 依赖）
- [ ] 日志轮转（RotatingFileHandler）
- [ ] 单元测试与集成测试
- [ ] 图片消息理解（多模态 AI）
- [ ] 语音消息转文字
- [ ] 插件系统（自定义命令/回复策略）
- [ ] Docker 部署方案
- [ ] 微信版本兼容性自动检测

---

## 许可证

MIT © [cancelGuMu](https://github.com/cancelGuMu)

---

## 致谢

- [DeepSeek](https://platform.deepseek.com/) —— 高性价比 AI 模型
- [Anthropic](https://www.anthropic.com/) —— Claude API

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/cancelGuMu">孤舟99</a></sub>
</p>

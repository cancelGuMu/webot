# WeChat Group Bot —— 微信群聊 AI 助手

基于 AI 的微信群聊智能机器人。支持**错过的消息总结**、**@提问对话**、**Map-Reduce 长文本分段处理**、**主动参与群聊**及**长期记忆**。多 AI 后端（DeepSeek / Claude），通过 WeFlow 本地 HTTP API 或 UIAutomation 读取消息，Win32 `PostMessage` 发送回复，**无需协议逆向、无需 DLL 注入**。

## 功能一览

| 功能 | 说明 |
|---|---|
| 🧠 **智能总结** | 发送"总结一下"/"错过了什么"等关键词，自动定位你上一条消息的时间点，总结之后的所有聊天内容 |
| 💬 **AI 对话** | @机器人 提问，获得基于大模型的对话回复（支持 DeepSeek V4 / Claude） |
| 📚 **Map-Reduce** | 超长对话自动分段提取 → 合并总结，安全处理群聊 999+ 条消息 |
| 🎭 **主动参与** | 根据群聊消息速率自动切换 5 种活跃模式（沉睡→冷清→闲聊→热闹→炸了），无需 @ 也能插话 |
| 📝 **长期记忆** | 每个群聊独立维护第一人称"记忆日记"，定期自动合并，让 AI 越来越懂群里的梗和上下文 |
| 🔍 **联网搜索** | AI 对话前自动搜索 DuckDuckGo，提供实时信息（可关闭） |
| 📌 **粘性提及** | 发一个空的 @机器人，下一条消息自动带上 @效果，不用每次都 @ |
| 🎲 **抽签娱乐** | @机器人 说"抽签"，获取 100 种加权运势签文（大吉~凶） |
| 🛡 **管理命令** | 管理员可通过聊天命令管理 wxid→昵称 映射 |
| 🔌 **多后端** | 可插拔 AI 后端（DeepSeek / Claude）和微信后端（WeFlow / UIA / wx4py） |

## 架构概览

```
┌──────────────────────────────────────────────────┐
│                  WeChat Desktop                   │
│  ┌────────────┐    ┌───────────────────────────┐ │
│  │ WeFlow API │    │  Chat Window (Qt/CEF)     │ │
│  │ (localhost │    │  ← PostMessage keystrokes │ │
│  │   :5031)   │    │  ← UIA tree walking       │ │
│  └─────┬──────┘    └───────────▲───────────────┘ │
└────────┼───────────────────────┼──────────────────┘
         │ read (HTTP / UIA)     │ send (PostMessage)
         ▼                       │
┌─────────────────┐    ┌─────────┴───────────┐
│  WeChat Backend │    │  WindowController    │
│  · WeFlow       │    │  · HWND discovery    │
│  · UIA          │    │  · Keyboard nav      │
│  · wx4py        │    │  · Clipboard send    │
└────────┬────────┘    └─────────────────────┘
         │
         ▼
┌─────────────────┐
│  MessageStore    │     SQLite (WAL mode)
│  · messages      │     · trigger_log
│  · user_last_msg │     · group_memory
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              MessageRouter                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Trigger  │ │ Admin    │ │ Proactive    │ │
│  │ Detector │ │ Commands │ │ Gate + Modes │ │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       │             │              │          │
│       ▼             ▼              ▼          │
│  ┌──────────────────────────────────────┐    │
│  │        Summarizer (AI Backend)       │    │
│  │  · Claude (Anthropic SDK)            │    │
│  │  · DeepSeek (OpenAI-compatible SDK)  │    │
│  └──────────────────────────────────────┘    │
│       │                                       │
│       ▼                                       │
│  MemoryConsolidator → group_memory (日记)     │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
              Reply → WeChat Window
```

## 快速开始

### 环境要求

- **Windows 10/11**（使用了 Win32 API，不支持 macOS/Linux）
- **Python 3.10+**
- **微信桌面版 4.x**（建议使用小号）
- [WeFlow](https://github.com/hicccc77/WeFlow)（推荐，用于读取消息）或使用内置 UIA 后端
- DeepSeek 或 Anthropic API Key

### 安装与启动

```bash
# 1. 进入项目目录
cd wechatbot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建配置文件
cp .env.example .env
# 编辑 .env，填入 API Key、机器人昵称、要监控的群名

# 4. 启动 WeFlow 并开启 HTTP API
#    WeFlow → 设置 → API 服务 → 启动 → 复制 access token
#    将 token 填入 .env 的 WEFLOW_TOKEN

# 5. 启动机器人
python launcher.py
# 或双击 start.bat
```

> **提示**：首次运行 `launcher.py` 会自动检查 Python 版本、安装依赖、帮你创建 `.env` 文件。

### 最小配置

`.env` 中至少需要配置以下项：

```ini
AI_BACKEND=deepseek              # 或 claude
DEEPSEEK_API_KEY=sk-your-key     # 如果用 DeepSeek
ANTHROPIC_API_KEY=sk-ant-your-key # 如果用 Claude
BOT_DISPLAY_NAME=群聊小助手        # 机器人的微信昵称
WECHAT_GROUPS=摸鱼群,工作群        # 要监控的群名（逗号分隔）
WEFLOW_TOKEN=your-weflow-token   # 如果用 WeFlow 后端
```

如果使用 UIA 后端（无需 WeFlow），修改：
```ini
WECHAT_BACKEND=uia
# 不需要 WEFLOW_TOKEN
```

## 使用说明

### 🧠 总结模式

在监控的群聊中发送以下任一关键词，机器人自动总结你错过的消息：

**中文触发词**：`总结一下` `之前发了什么` `错过了什么` `聊天总结` `帮我总结` `前面说了什么` `说了啥` `发生了什么`

**英文触发词**：`summarize` `what did i miss`

也可以 @机器人 并附带总结意图，效果相同。

**工作原理**：机器人找到你在触发时间之前的**最后一条消息**，总结从那条消息到现在之间的所有聊天内容。如果找不到你的历史消息，则回退到最近 N 小时（由 `FALLBACK_WINDOW_HOURS` 控制）。

### 💬 AI 对话模式

@机器人 并提问（非总结类问题），机器人会用大模型回复：

> @群聊小助手 推荐一个深圳周末去处

> @群聊小助手 这段代码为什么会报错：`TypeError: ...`

机器人会自动获取最近聊天上下文（10 分钟 / 20 条消息），并可选择启用联网搜索获取实时信息。

### 🎲 抽签娱乐

@机器人 说"抽签"，获取运势签文：

> @群聊小助手 抽签

返回加权随机结果（大吉 12%、中吉 23%、小吉 30%、末吉 20%、凶 15%），每种签文有 20 条不同的趣味短语。

### 📌 粘性提及

发送一个**空的 @机器人**（只 @ 不加任何文字），机器人进入粘性监听模式。你在**同一群聊**中发送的**下一条消息**会自动被视为 @机器人 的消息。无需每次都手动 @。

默认等待时间 60 秒（可通过 `STICKY_MENTION_TTL_SEC` 调整）。

### 🛡 管理命令

管理员（通过 `ADMIN_WXID` 配置）可以使用以下命令：

| 命令 | 效果 |
|---|---|
| `@bot 改名 wxid_xxx = 昵称` | 添加或更新昵称映射 |
| `@bot 删除昵称 wxid_xxx` | 删除昵称映射 |
| `@bot 刷新昵称` | 从文件重新加载昵称 |
| `@bot 帮助` | 显示可用命令（所有人可用） |

昵称映射保存在 `data/nicknames.json`，用于在 AI 回复中将 `wxid_xxx` 替换为人类可读的昵称。

### 🎭 主动参与模式

开启后，机器人无需 @ 即可根据群聊活跃度自动插话。通过消息速率（条/分钟）自动切换 5 种模式：

| 模式 | 速率阈值 | 评估间隔 | 回复概率 | 最大字数 | 行为描述 |
|---|---|---|---|---|---|
| 😴 沉睡 | < 1.5 | 9999s | 0% | 0 | 群聊几乎没人说话，保持沉默 |
| 🌙 冷清 | ≥ 1.5 | 300s | 10% | 30 | 偶尔有人冒泡，可以简短回应 |
| ☀️ 闲聊 | ≥ 4.0 | 120s | 25% | 50 | 正常聊天节奏，适度参与 |
| 🔥 热闹 | ≥ 6.5 | 60s | 50% | 35 | 讨论热烈，积极加入 |
| 💥 炸了 | ≥ 8.5 | 30s | 70% | 20 | 消息刷屏，快速简短吐槽 |

阈值可通过 `.env` 文件中的 `PROACTIVE_RATE_*` 系列参数调整。使用 `python tools/analyze_chat_rhythm.py` 分析你的群聊节奏，获得推荐阈值。

**启用方法**：在 `.env` 中设置 `PROACTIVE_ENABLED=true`。

### 📝 长期记忆

机器人自动为每个群聊维护一份第一人称"记忆日记"。当新消息达到 20 条或距上次合并超过 1 小时，自动触发记忆合并。

记忆内容包括：
- 群友之间的称呼和关系
- 群内重要的讨论话题
- 有趣的事件和梗

记忆以第一人称视角写就（"我在这个群里已经..."），帮助 AI 在后续对话中提供更个性化的回复。

## 配置参考

### 必填项

| 环境变量 | 说明 |
|---|---|
| `AI_BACKEND` | AI 后端选择：`deepseek` 或 `claude` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（使用 DeepSeek 时必填） |
| `ANTHROPIC_API_KEY` | Anthropic API Key（使用 Claude 时必填） |
| `BOT_DISPLAY_NAME` | 机器人在微信中的昵称（用于 @检测） |
| `WECHAT_GROUPS` | 要监控的群聊名称，逗号分隔。支持 `*` 或 `all` 自动发现所有群聊 |

### AI 模型选择

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `SUMMARIZE_MODEL` | `claude-haiku-4-5-20251001` | Claude 模型 ID |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | DeepSeek 模型 ID |

### 微信后端

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `WECHAT_BACKEND` | `weflow` | 微信后端：`weflow`（推荐）、`uia`、`wx4py` |
| `WEFLOW_URL` | `http://127.0.0.1:5031` | WeFlow API 地址 |
| `WEFLOW_TOKEN` | — | WeFlow API 访问令牌（使用 weflow 后端时必填） |

### 功能开关

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | AI 对话时是否启用 DuckDuckGo 联网搜索 |
| `PROACTIVE_ENABLED` | `false` | 是否启用主动参与群聊 |
| `STICKY_MENTION_ENABLED` | `true` | 是否启用粘性提及 |
| `STICKY_MENTION_TTL_SEC` | `60` | 粘性提及等待时间（10-300 秒） |

### 触发关键词

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `TRIGGER_KEYWORDS` | 10 个中英文关键词 | 逗号分隔的总结触发词 |

默认：「总结一下, 之前发了什么, 错过了什么, summarize, what did i miss, 聊天总结, 帮我总结, 前面说了什么, 说了啥, 发生了什么」

### 主动参与调参

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PROACTIVE_RATE_WINDOW_SEC` | `120` | 速率计算窗口（秒） |
| `PROACTIVE_RATE_QUIET` | `1.5` | SLEEP→QUIET 阈值（条/分钟） |
| `PROACTIVE_RATE_CASUAL` | `4.0` | QUIET→CASUAL 阈值 |
| `PROACTIVE_RATE_LIVELY` | `6.5` | CASUAL→LIVELY 阈值 |
| `PROACTIVE_RATE_BURST` | `8.5` | LIVELY→BURST 阈值 |

### 调优参数

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `POLL_INTERVAL_SEC` | `1.0` | 消息轮询间隔（秒） |
| `DEDUP_WINDOW_SEC` | `60` | 同一群聊触发去重窗口（秒） |
| `MAX_MESSAGES_FOR_SUMMARY` | `5000` | 每次总结拉取的最大消息数 |
| `CHUNK_SIZE` | `400` | Map-Reduce 每段消息数（10-1000） |
| `FALLBACK_WINDOW_HOURS` | `8` | 最小总结窗口（小时） |

### 其他

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ADMIN_WXID` | — | 管理员的微信 wxid |
| `DB_PATH` | `data/messages.db` | SQLite 数据库路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_FILE` | `data/bot.log` | 日志文件路径 |

## 项目结构

```
wechatbot/
├── src/
│   ├── main.py                  # 入口：加载配置，启动 Bot
│   ├── config.py                # BotConfig 数据类 + .env 加载与校验
│   ├── bot.py                   # Bot 编排器：初始化组件，启停生命周期
│   ├── router.py                # MessageRouter：消息分发核心逻辑
│   ├── admin.py                 # 管理命令处理（改名、删昵称、帮助）
│   ├── fun.py                   # 娱乐模块（抽签）
│   ├── nickname.py              # wxid ↔ 昵称 映射服务
│   ├── db/
│   │   ├── schema.py            # SQLite DDL（messages, user_last_message, trigger_log, group_memory）
│   │   └── store.py             # MessageStore：插入、查询、去重、记忆
│   ├── trigger/
│   │   └── detector.py          # 触发检测（关键词 + @提及）
│   ├── summarize/
│   │   ├── models.py            # Pydantic 模型（SummaryResult, ParticipantContribution）
│   │   ├── base.py              # AbstractSummarizer：分块、重试、格式化、chat/proactive 提示词
│   │   ├── claude_backend.py    # ClaudeSummarizer（Anthropic SDK, 原生 Pydantic 解析）
│   │   ├── deepseek_backend.py  # DeepSeekSummarizer（OpenAI SDK, 工具调用解析）
│   │   ├── prompts.py           # 系统提示词 + XML 模板 + token 估算
│   │   └── __init__.py          # 工厂函数 create_summarizer()
│   ├── proactive/
│   │   ├── modes.py             # 5 种主动模式（SLEEP/QUIET/CASUAL/LIVELY/BURST）
│   │   ├── rate_tracker.py      # 滑动窗口速率跟踪器
│   │   ├── gate.py              # 4 级门控：开关→速率→间隔→概率
│   │   └── sticky.py            # 粘性提及跟踪器
│   ├── memory/
│   │   └── consolidator.py      # 长期记忆合并（每群独立日记）
│   ├── wechat/
│   │   ├── base.py              # AbstractWeChatBackend ABC + 统一消息格式
│   │   ├── weflow_backend.py    # WeFlow 后端（HTTP 读 + PostMessage 发）
│   │   ├── uia_backend.py       # UIA 后端（UIAutomation 读 + 键盘导航）
│   │   ├── wx4py_backend.py     # wx4py 后端（微信 4.1.7-4.1.8）
│   │   ├── window_controller.py # 微信窗口控制（HWND 发现/激活/导航/发送）
│   │   ├── keyboard.py          # 键盘模拟（按键/组合键）
│   │   └── helpers.py           # 去重集合、消息 ID 生成、类型标准化
│   └── utils/
│       ├── logging_config.py    # 结构化日志配置
│       └── web_search.py        # DuckDuckGo 联网搜索（PII 擦除 + 超时降级）
├── tools/
│   ├── analyze_chat_rhythm.py   # 分析群聊节奏，推荐主动模式阈值
│   ├── find_weflow_message.py   # 在 WeFlow 中搜索指定消息
│   ├── manual_send_probe.py     # 发送流水线诊断工具
│   └── reconcile_nicknames.py   # 从 Excel 聊天记录协调昵称映射
├── tests/
│   └── test_window_controller.py # 窗口控制器和发送流水线测试
├── data/                        # 运行时数据（数据库、昵称、日志等）
├── launcher.py                  # 一键启动器（环境检查 + 依赖安装 + 启动）
├── start.bat                    # Windows 双击启动
├── start.sh                     # Bash 启动
├── .env.example                 # 配置文件模板
├── requirements.txt             # Python 依赖
└── README.md                    # 本文件
```

## 数据流

### 消息摄取

```
WeFlow API 轮询 (1s 间隔) / UIA 树扫描
    → 解析 JSON / UIA 元素，提取 sender/content/timestamp
    → wxid → 昵称解析（联系人 API + nicknames.json）
    → 内容中 @wxid → @昵称 替换
    → INSERT INTO messages（按 message_id 去重）
    → UPSERT user_last_message 游标
```

### 消息分发

```
收到新消息
    → 自过滤（跳过机器人自己的消息）
    → 持久化到数据库
    → 检查记忆合并触发条件
    → MessageRouter.handle():
        ├── 空 @提及？ → 注册粘性提及
        ├── 管理员 + 命令？ → AdminCommandHandler
        ├── 关键词触发？ → _handle_summary()
        ├── @提及（非总结）？ → _handle_chat()
        ├── 抽签关键词？ → draw_lots()
        └── 都不是 → ProactiveGate.should_speak()
            └── 通过门控 → _handle_proactive_chat()
```

### 总结生成

```
触发检测
    → 去重检查（trigger_log, DEDUP_WINDOW_SEC 窗口）
    → get_user_previous_timestamp(chat, requester, before_ts)
        ├── 找到且非自己 → 使用该时间戳作为起点
        │   └── 跳过 ≤30s 间隔的"爆发"消息，取最早的作为边界
        └── None 或窗口太小 → 回退（FALLBACK_WINDOW_HOURS）
    → get_messages_since(chat, since_ts, limit=MAX_MESSAGES_FOR_SUMMARY)
    → 预解析消息中的 wxid
    → estimate_tokens(messages)
        ├── ≤ 200 条 → summarize_direct（1 次 API 调用）
        ├── 201~2000 条 → summarize_map_reduce（分段 → 合并）
        └── > 2000 条 → 多级 map-reduce（分段 → 批量合并 → 最终合并）
    → resolve_wxids_in_text(output)
    → 去除 Markdown 格式 → 通过 PostMessage 发送回复
```

## 数据库表结构

### `messages`

| 列 | 类型 | 说明 |
|---|---|---|
| message_id | TEXT UNIQUE | MD5(serverId + localId) |
| chat_id | TEXT | 群聊 ID（如 `20968749111@chatroom`） |
| sender_id | TEXT | 发送者 wxid |
| sender_name | TEXT | 解析后的昵称 |
| content | TEXT | 消息文本 |
| msg_type | INTEGER | 1=文本, 3=图片, 34=语音 等 |
| timestamp | INTEGER | Unix 秒 |
| created_at | INTEGER | 插入时间戳 |

索引：`(chat_id, timestamp DESC)`, `(chat_id, sender_id, timestamp DESC)`

### `user_last_message`

每个用户在每个群聊的最后消息时间戳游标。`(chat_id, sender_id)` 联合主键，UPSERT 更新。

### `trigger_log`

触发器事件记录，用于去重。应用程序级 TTL（`DEDUP_WINDOW_SEC`），定期清理 7 天前的旧记录。

### `group_memory`

每个群聊的长期记忆。`chat_id` 主键，存储合并后的记忆文本、消息计数和最后合并时间。

## 微信后端对比

| 后端 | 微信版本 | 消息读取 | 消息发送 | 风险 | 推荐场景 |
|---|---|---|---|---|---|
| **weflow** | 4.x+ | WeFlow HTTP API（读本地数据库） | PostMessage（无需焦点） | 中 | **推荐**，最稳定 |
| uia | 4.x+ | 原生 UIAutomation 树扫描 | PostMessage | 低 | 不想装第三方工具 |
| wx4py | 4.1.7-4.1.8 | wx4py 回调 | wx4py ReplyAction | 低 | 特定微信版本 |

> **注意**：UIA 后端使用显示名称的 MD5 作为 sender_id（而非真实 wxid），因此基于 wxid 的昵称覆盖对其无效。

## AI 模型对比

| 模型 | 上下文窗口 | 输入价格 | 最佳场景 |
|---|---|---|---|
| `deepseek-v4-flash` | 1M | $0.14/M | 日常总结（推荐，性价比最高） |
| `deepseek-v4-pro` | 1M | $0.44/M | 复杂分析 |
| `claude-haiku-4-5` | 200K | $1.00/M | Claude 生态快速总结 |
| `claude-sonnet-4-5` | 200K | $3.00/M | 高质量总结 |

## 常见问题

### WeFlow API 无法连接

```
[ERROR] WeFlow API is not reachable at http://127.0.0.1:5031
```

- 确认 WeFlow 正在运行
- WeFlow → 设置 → API 服务 → 启动
- 验证：浏览器打开 `http://127.0.0.1:5031/health`
- 检查 `.env` 中 `WEFLOW_TOKEN` 是否与 WeFlow 的 access token 一致

### AI 回复中出现 wxid_xxx 而不是昵称

- 手动编辑 `data/nicknames.json` 添加映射
- 或使用管理命令：`@bot 改名 wxid_xxx = 昵称`
- WeFlow 联系人 API 只返回你的个人通讯录，不包含所有群成员
- 也可使用 `python tools/reconcile_nicknames.py` 从导出的聊天记录自动协调

### 回复发到了错误的群

- 确保微信窗口**没有被最小化**（可以被遮挡，但不能最小化）
- 机器人通过 PostMessage 向微信 HWND 发送按键，HWND 在微信重启后会变化，机器人会自动检测

### UIA 后端读取不到消息（UIA 树为空）

- 运行 `python diagnose_wechat.py` 进行诊断
- 微信 4.1.x 需要激活 Qt 无障碍桥：先打开讲述人（Win+Ctrl+Enter），启动微信，再关闭讲述人
- 机器人内置了 UIA 树唤醒机制（COM 级 StructureChanged 事件订阅）

### 机器人发送的消息不见了

- 检查 `data/send_failures.log` 查看发送失败记录
- WeFlow 后端有发送确认机制（发送后 3 秒内轮询确认）
- 如果微信窗口变成了空白渲染表面（白色无内容），机器人会自动检测并拒绝发送

## 法律与合规

| 组件 | 状态 | 说明 |
|---|---|---|
| DeepSeek / Claude API | ✅ 合法 | 官方付费 API 服务 |
| PostMessage（Win32） | ✅ 合法 | 标准 Windows API，等同于键盘输入 |
| SQLite 本地存储 | ✅ 合法 | 数据完全保存在你的设备上 |
| Win32 剪贴板 API | ✅ 合法 | 标准 Windows API |
| WeFlow（数据库读取器） | ⚠️ 灰色 | 读取微信本地加密数据库；类似工具曾收到腾讯法律通知 |

**建议**：本工具设计用于**个人小群日常使用**。请勿商用或大规模部署。建议告知群成员机器人存在。

## 依赖

```
anthropic        # Claude API（可选）
openai            # DeepSeek API（OpenAI 兼容）
python-dotenv     # .env 配置加载
pydantic          # 结构化输出模型
ddgs              # DuckDuckGo 联网搜索
pywin32           # Win32 API（窗口管理、剪贴板）
uiautomation      # UIA 树遍历（UIA 后端）
comtypes          # COM 级 UIA 客户端注册
Pillow            # 截图 / 空白窗口检测
psutil            # 进程健康检查
pyperclip         # 剪贴板工具
```

## License

MIT

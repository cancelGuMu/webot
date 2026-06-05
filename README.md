# WeChatBot

> 微信群聊 AI 助手 —— 原生读取微信数据库，零 Hook 零注入，安全不封号。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.10%2B-green?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/AI-Claude%20%7C%20DeepSeek-purple?style=flat-square" alt="AI Backend" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/ui-React%20%2B%20Tailwind-cyan?style=flat-square&logo=react" alt="UI" />
</p>

---

## 它是什么

WeChatBot 是一个运行在 Windows 上的微信群聊机器人。把它加入你的群聊，它会：

- **帮你总结错过的消息** —— 对群里说一句「总结一下」，立刻告诉你前面聊了什么，按话题分类、附关键人物和时间线。
- **回应你的提问** —— **@机器人** 问任何问题，它会结合群聊上下文和联网搜索来回答。
- **自然参与群聊** —— 感知聊天节奏，在合适的时候自动插话、接梗、吐槽，像个普通群友。

内置 **Web 仪表盘**（React + Tailwind CSS），实时查看运行状态、处理消息量、AI 延迟。可打包为单个 EXE，双击即用。

---

## 功能一览

### 智能总结

发送以下关键词即可触发总结：`总结一下`、`前面说了什么`、`聊天总结`、`说了啥`、`发生了什么`、`summarize` 等。

机器人会自动找到你上一条消息的位置，把之后所有群聊内容交给 AI，生成一份结构化摘要：谁说了什么、讨论了哪些话题、有什么决定和趣事。

对话特别长（999+ 条消息）时，会自动分块处理，不会超出 AI 的上下文限制。

### AI 对话

在群里 **@机器人 + 你的问题**，即可获得 AI 回复。机器人会：

- 自动附上最近 10 分钟的群聊记录作为上下文，让回答更贴合当前话题。
- 可选**联网搜索**（DuckDuckGo，免费免 Key），查询前自动脱敏（手机号、身份证号等）。不需要的可关闭。
- 支持 **Claude** 和 **DeepSeek** 两种 AI 后端，随时切换。

### 主动发言（可开关）

开启后，机器人会根据群聊消息速率自动判断氛围，在合适的时候插话：

| 模式 | 触发条件（条/分钟） | 行为 |
|------|---------------------|------|
| 😴 沉睡 | < 1.5 | 完全沉默 |
| 🌙 冷清 | 1.5 ~ 4.0 | 偶尔参与，保持克制 |
| 💬 闲聊 | 4.0 ~ 6.5 | 正常聊天节奏 |
| 🔥 热闹 | 6.5 ~ 8.5 | 活跃参与 |
| 💥 炸了 | > 8.5 | 高频插话，极短回复 |

AI 连续多次判断"不应该插话"时，会自动延长沉默时间（最高 16 倍），避免浪费 API 调用。遇到群友讨论重大负面事件（疾病、事故、吵架等），机器人会主动保持沉默。

### 长期记忆

机器人会自动记录群聊中的重要信息，形成对群的"印象日记"：群友的特点习惯、群里的固定梗、聊天氛围等。越聊越懂这个群。

### 粘性提及

发了 `@机器人` 但忘了打字？没关系，60 秒内发的下一条消息会自动当作 @了机器人。

### 昵称系统

群友的微信号（wxid_xxx）自动替换为显示名。你也可以手动给群友设昵称（见下方管理命令）。

### 趣味功能

对机器人说「**抽签**」，随机抽取一支运势签（大吉~凶，5 档加权），附带幽默解读。

### Web 仪表盘

机器人启动后自动打开 `http://127.0.0.1:7327`，提供：

- **运行状态**：是否运行中、运行时长、已处理消息数、AI 后端延迟
- **系统配置**：在线修改 AI 后端、API Key、机器人名称、功能开关等
- **运行日志**：实时查看最近 500 条日志

---

## 快速开始

### 前提

- **Windows 10 或 11**
- **微信桌面版** 已登录
- **目标群聊已添加到通讯录** — 机器人通过搜索群名进入群聊，未添加到通讯录的群聊无法搜索到
- Python 3.10+（仅源码运行需要，用 EXE 则不需要）

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/cancelGuMu/wechat-group-bot/releases) 下载 `WeChatBot.exe`，双击运行。

首次运行弹出配置向导，按提示完成四步即可开始使用：密钥提取 → 机器人身份 → AI 后端 → 功能开关。

### 方式二：从源码运行

```bash
git clone https://github.com/cancelGuMu/wechat-group-bot.git
cd wechat-group-bot
pip install -r requirements.txt
python desktop.py
```

---

## 配置说明

所有配置在项目根目录的 `.env` 文件中设置。首次运行会自动创建模板。

### 必填项

```env
# AI 后端：deepseek 或 claude
AI_BACKEND=deepseek

# DeepSeek API Key（AI_BACKEND=deepseek 时必填）
# 免费注册获取：https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# Claude API Key（AI_BACKEND=claude 时必填）
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
```

### AI 模型选择

```env
# DeepSeek 模型
DEEPSEEK_MODEL=deepseek-v4-flash     # v4-flash（推荐）：极速低价
                                      # v4-pro：1M 上下文旗舰

# Claude 模型
SUMMARIZE_MODEL=claude-haiku-4-5-20251001  # haiku（推荐）：快速廉价
                                           # sonnet：更高质量
```

### 机器人身份

```env
# 机器人在群里的显示名（用于 @ 检测，填你给机器人设的群昵称）
BOT_DISPLAY_NAME=群聊小助手

# 监控的群聊，逗号分隔多个群。留空或填 * = 监控所有群
WECHAT_GROUPS=

# 管理员 wxid（可执行管理命令，在聊天记录中查看发消息的人就是 wxid）
ADMIN_WXID=
```

### 触发关键词

```env
# 发送这些词触发总结（逗号分隔，不区分大小写）
TRIGGER_KEYWORDS=总结一下,之前发了什么,错过了什么,summarize,what did i miss,聊天总结,帮我总结,前面说了什么,说了啥,发生了什么
```

### 功能开关

```env
# 联网搜索（DuckDuckGo 免费搜索，发送前自动脱敏可识别隐私）
ENABLE_WEB_SEARCH=true        # true=开启  false=关闭

# 主动发言（机器人在没人 @ 它时也会自动插话）
PROACTIVE_ENABLED=false       # true=开启  false=关闭

# 粘性提及（空 @ 后下一句话自动算 @）
STICKY_MENTION_ENABLED=true  # true=开启  false=关闭
```

### 主动发言调参

以下参数仅在 `PROACTIVE_ENABLED=true` 时生效：

```env
# 速率计算窗口（秒），用多长的时间窗口来判断群聊节奏
PROACTIVE_RATE_WINDOW_SEC=120

# 各模式的速率阈值（条/分钟），必须从小到大严格递增
PROACTIVE_RATE_QUIET=1.5     # 超过此值 → 冷清模式
PROACTIVE_RATE_CASUAL=4.0    # 超过此值 → 闲聊模式
PROACTIVE_RATE_LIVELY=6.5    # 超过此值 → 热闹模式
PROACTIVE_RATE_BURST=8.5     # 超过此值 → 炸了模式
```

不同群的聊天节奏差异很大，建议先用 `python tools/analyze_chat_rhythm.py` 分析群聊数据再调。

### 性能调优

```env
# 消息轮询间隔（秒），默认 1.0。增大可降低 CPU，但消息响应会变慢
POLL_INTERVAL_SEC=1.0

# 去重窗口（秒），同一群聊两次触发之间的最小间隔
DEDUP_WINDOW_SEC=60

# 总结时最多取多少条消息（适用群聊 999+ 的场景）
MAX_MESSAGES_FOR_SUMMARY=5000

# Map-Reduce 分块大小（每条消息约 3~4 字的中文文本）
CHUNK_SIZE=400

# 兜底总结窗口（小时），找不到请求者的上一条消息时，向前看多少小时
FALLBACK_WINDOW_HOURS=8
```

### 日志

```env
LOG_LEVEL=INFO                # DEBUG / INFO / WARNING / ERROR
LOG_FILE=data/bot.log         # 留空则只输出到控制台
```

---

## 管理命令

在群里发送 `@机器人 <命令>` 即可（仅 `ADMIN_WXID` 设定的管理员可用）：

| 命令 | 说明 | 示例 |
|------|------|------|
| `改名 wxid = 昵称` | 给群友设昵称 | `改名 wxid_abc = 张三` |
| `删除昵称 wxid` | 删除已设昵称 | `删除昵称 wxid_abc` |
| `刷新昵称` | 重新加载昵称缓存 | |
| `帮助` / `help` | 查看全部命令 | |

---

## 常见问题

<details>
<summary><strong>首次使用需要安装什么？</strong></summary>

什么都不用装。下载 EXE 双击即可。所有需要的 DLL 文件已内置在程序中，密钥提取由程序自动完成。唯一前提是电脑上已登录微信。

</details>

<details>
<summary><strong>会被封号吗？</strong></summary>

WeChatBot 只读取微信本地的加密数据库文件，通过键盘模拟发送消息。不注入进程、不 Hook 函数、不模拟网络协议。这是一种非常安全的只读方式，目前没有已知的封号案例。但任何第三方工具都有理论风险，请自行评估。

</details>

<details>
<summary><strong>支持哪些 AI 模型？费用如何？</strong></summary>

- **DeepSeek V4 Flash**（推荐）：极速极低价，约 ¥0.001/千 tokens。普通群一天的总结费用通常不到 ¥0.10。
- **DeepSeek V4 Pro**：1M 上下文旗舰，稍贵。
- **Claude Haiku 4.5**：快速廉价，适合总结和简单对话。
- **Claude Sonnet 4.5/4.6**：更高质量，适合复杂分析。

切换模型只需改 `.env` 中的 `AI_BACKEND` 和对应 Model 配置，或直接在仪表盘的配置面板里修改。

</details>

<details>
<summary><strong>微信窗口可以最小化吗？</strong></summary>

消息读取不受影响。但消息发送需要微信窗口可见——发送时会自动尝试激活微信窗口。建议保持微信窗口打开状态（可以放在其他虚拟桌面）。

</details>

<details>
<summary><strong>支持 macOS 吗？</strong></summary>

目前仅支持 Windows。macOS 版微信使用了不同的数据库加密方案，暂无支持计划。

</details>

<details>
<summary><strong>支持多个群聊吗？</strong></summary>

支持。在 `WECHAT_GROUPS` 中填入群聊名称（逗号分隔），留空或填 `*` 则自动监控所有群。

</details>

<details>
<summary><strong>机器人会漏消息吗？</strong></summary>

默认每秒轮询一次，每次拉取每个群最近 50 条消息，正常群聊节奏下不会漏。如果担心遗漏，可减小 `POLL_INTERVAL_SEC`。

</details>

<details>
<summary><strong>如何停止机器人？</strong></summary>

在仪表盘点击停止按钮，或在终端按 `Ctrl+C`。

</details>

---

## 许可证

MIT © [cancelGuMu](https://github.com/cancelGuMu)

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/cancelGuMu">孤舟99</a></sub>
</p>

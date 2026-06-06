# webot

> 微信群聊 AI 助手 —— 原生读取微信数据库，零 Hook 零注入，安全不封号。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.10%2B-green?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/AI-Claude%20%7C%20DeepSeek-purple?style=flat-square" alt="AI Backend" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/ui-React%20%2B%20Tailwind-cyan?style=flat-square&logo=react" alt="UI" />
  <img src="https://img.shields.io/badge/tests-241%20passed-success?style=flat-square" alt="Tests" />
</p>

---

## 它是什么

webot 是一个运行在 Windows 上的微信群聊机器人。把它加入你的群聊，它会：

- **帮你总结错过的消息** —— 对群里说一句「总结一下」，立刻告诉你前面聊了什么，按话题分类、附关键人物和时间线。
- **回应你的提问** —— **@机器人** 问任何问题，它会结合群聊上下文和联网搜索来回答。
- **自然参与群聊** —— 感知聊天节奏，在合适的时候自动插话、接梗、吐槽，像个普通群友。

内置 **Web 仪表盘**（React + Tailwind CSS），实时查看运行状态、处理消息量、AI 延迟。内置暗色/亮色双主题，配置导入导出。可打包为单个 EXE，双击即用。

---

## 功能一览

### 智能总结

发送以下关键词即可触发总结：`总结一下`、`前面说了什么`、`聊天总结`、`说了啥`、`发生了什么`、`summarize` 等（可在仪表盘自定义）。

机器人会自动找到你上一条消息的位置，把之后所有群聊内容交给 AI，生成一份结构化摘要：谁说了什么、讨论了哪些话题、有什么决定和趣事。

对话特别长（999+ 条消息）时，会自动分块处理，不会超出 AI 的上下文限制。支持在仪表盘一键开关总结功能、调整回溯时长（1-72 小时）、增删触发关键词。

### AI 对话

在群里 **@机器人 + 你的问题**，即可获得 AI 回复。机器人会：

- 自动附上最近 10 分钟的群聊记录作为上下文，让回答更贴合当前话题。
- 支持 **Claude** 和 **DeepSeek** 两种 AI 后端，随时切换。
- **DeepSeek 自定义 API 地址**：支持配置 `DEEPSEEK_BASE_URL`，可使用代理、第三方 API 或私有部署。

### 提示词沙箱

内置 Prompt Sandbox，无需在真实群里发消息即可测试 AI 回复效果。支持自定义模拟发送人、群聊名称、长期群聊记忆，所见即所得的测试 AI 的表现和延迟。

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

群友的微信号（wxid_xxx）自动替换为显示名。你也可以手动给群友设昵称（见下方管理命令）。群名也会自动持久化，下拉框显示人类可读的群名称（如「摸鱼群」）而非 chat_id。

### 趣味功能

对机器人说「**抽签**」，随机抽取一支运势签（大吉~凶，5 档加权），附带幽默解读。

### 配置备份与导入

仪表盘支持一键导出当前配置为 JSON 文件，也可以通过上传 JSON 备份恢复配置。方便迁移、分享配置、多环境切换。

### Web 仪表盘

机器人启动后自动打开 `http://127.0.0.1:7327`，包含五大模块：

- **Dashboard 运行看板**：实时指标卡片（已处理消息、运行时长、API 延迟）、SVG 动态波形图、一键诊断（Python 环境 / 依赖 / 微信进程 / DLL 文件 / 数据库连接）
- **系统配置**：在线修改 AI 后端、API Key、机器人身份、功能开关、触发关键词等
- **提示词沙箱**：模拟群聊场景测试 AI 回复，支持自定义上下文变量
- **群友昵称**：管理群友的显示名称映射
- **运行日志**：实时查看、按级别筛选（DEBUG/INFO/WARNING/ERROR）、关键词搜索高亮

---

## 快速开始

### 前提

- **Windows 10 或 11**
- **微信桌面版** 已登录
- **希望机器人监控的群聊需手动添加到通讯录**：打开群聊 → 点击右上角 `···` → 开启「添加到通讯录」。未添加的群聊无法通过搜索名称进入，机器人将无法回复
- Python 3.10+（仅源码运行需要，用 EXE 则不需要）

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/cancelGuMu/webot/releases) 下载 `webot.exe`，双击运行。

首次运行弹出配置向导，按提示完成四步即可开始使用：密钥提取 → 机器人身份 → AI 后端 → 功能开关。

### 方式二：从源码运行

Windows：

```bash
git clone https://github.com/cancelGuMu/webot.git
cd webot
pip install -r requirements.txt
python desktop.py
```

macOS 实验版：

```bash
git clone https://github.com/cancelGuMu/webot.git
cd webot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-macos.txt
cd ui && npm install && npm run build && cd ..
python desktop_mac.py
```

macOS 路径会使用独立的 `.env.macos`，默认设置 `WECHAT_BACKEND=mac_hybrid`，不会覆盖 Windows 使用的 `.env`。`mac_hybrid` 通过本地 chatlog 服务读取 macOS 微信数据库，再通过辅助功能发送消息；`mac_ui` 仍可作为只走界面自动化的兜底模式。

macOS 读消息前需要先准备本地 chatlog 服务：

```bash
# 1. 确认微信已登录，SIP 已关闭；首次提取 key 需要管理员权限
python3 tools/macos_chatlog_setup.py diagnose

# 2. 提取当前账号的 all_keys.json（会触发 sudo 密码输入，不会打印 key 明文）
python3 tools/macos_chatlog_setup.py extract-keys

# 3. 再次确认 valid_key_entries > 0
python3 tools/macos_chatlog_setup.py diagnose

# 4. 构建并启动 chatlog_alpha HTTP 服务，默认监听 127.0.0.1:5030
python3 tools/macos_chatlog_setup.py build-chatlog
python3 tools/macos_chatlog_setup.py start-chatlog

# 5. 验证能读取增量消息；输出只包含数量/字段，不打印聊天正文
python3 tools/macos_chatlog_setup.py verify-read

# 如果已启动服务后才重新提取 key，请重启 chatlog 服务
python3 tools/macos_chatlog_setup.py restart-chatlog
```

`.env.macos` 中可显式配置：

```env
WECHAT_BACKEND=mac_hybrid
CHATLOG_BASE_URL=http://127.0.0.1:5030
# 如已安装自己的 chatlog_alpha，可指定二进制路径
# CHATLOG_BIN=/path/to/chatlog
```

首次发送消息时，需要在系统设置中给终端或 Python 授权“辅助功能”权限。

如果 `extract-keys` 返回 `scan failed code=-2`，说明当前终端没有权限读取
WeChat 进程内存。请确认 SIP 已关闭，并在命令提示时输入本机管理员密码；
Codex/脚本不会也不能代输这个密码。WeChat 重启或更新后，通常需要重新执行
`extract-keys`。

参考实现：
[teest114514/chatlog_alpha](https://github.com/teest114514/chatlog_alpha)、
[wechat-db-decrypt-macos](https://github.com/Thearas/wechat-db-decrypt-macos)、
[macOS 微信自动化调研](https://blog.ax0x.ai/wechat-automation-macos)。

---

## 配置说明

所有配置在项目根目录的 `.env` 文件中设置。首次运行会自动创建模板。大部分配置也可以在仪表盘中在线修改。

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
# DeepSeek 自定义 API 地址（可选，默认官方地址）
# 可用于代理转发、第三方 API、私有部署
DEEPSEEK_BASE_URL=https://api.deepseek.com

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

### 总结功能

```env
# 是否启用总结功能（true/false，也可在仪表盘一键开关）
SUMMARIZE_ENABLED=true

# 兜底总结窗口（小时），找不到请求者的上一条消息时，向前看多少小时
FALLBACK_WINDOW_HOURS=8

# 触发关键词（逗号分隔，不区分大小写，可在仪表盘在线增删）
TRIGGER_KEYWORDS=总结一下,之前发了什么,错过了什么,summarize,what did i miss,聊天总结,帮我总结,前面说了什么,说了啥,发生了什么
```

### 功能开关

```env
# 主动发言（机器人在没人 @ 它时也会自动插话）
PROACTIVE_ENABLED=false       # true=开启  false=关闭

# 趣味抽签（@机器人说"抽签"，返回运势签文）
FUN_ENABLED=true              # true=开启  false=关闭

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

## 测试

项目包含完整的测试套件：

```bash
# 单元测试（37 个测试用例）
python -m pytest tests/test_trigger.py tests/test_config.py -v

# 全量测试（241 个测试用例，包含 Web API）
python -m pytest tests/ -v

# E2E 功能测试（需 Playwright + Chromium）
python tests/test_functional.py
```

测试覆盖：配置加载、触发词检测、Web API 端点、WebSocket、前端浏览器自动化、消息路由、密钥提取。

---

## 常见问题

<details>
<summary><strong>首次使用需要安装什么？</strong></summary>

什么都不用装。下载 EXE 双击即可。所有需要的 DLL 文件已内置在程序中，密钥提取由程序自动完成。唯一前提是电脑上已登录微信。

</details>

<details>
<summary><strong>会被封号吗？</strong></summary>

webot 只读取微信本地的加密数据库文件，通过键盘模拟发送消息。不注入进程、不 Hook 函数、不模拟网络协议。这是一种非常安全的只读方式，目前没有已知的封号案例。但任何第三方工具都有理论风险，请自行评估。

</details>

<details>
<summary><strong>支持哪些 AI 模型？费用如何？</strong></summary>

- **DeepSeek V4 Flash**（推荐）：极速极低价，约 ¥0.001/千 tokens。普通群一天的总结费用通常不到 ¥0.10。
- **DeepSeek V4 Pro**：1M 上下文旗舰，稍贵。
- **Claude Haiku 4.5**：快速廉价，适合总结和简单对话。
- **Claude Sonnet 4.6**：更高质量，适合复杂分析。

切换模型只需改 `.env` 中的 `AI_BACKEND` 和对应 Model 配置，或直接在仪表盘的配置面板里修改。支持自定义 DeepSeek API 地址，可用于代理转发或私有部署。

</details>

<details>
<summary><strong>微信窗口可以最小化吗？</strong></summary>

消息读取不受影响。但消息发送需要微信窗口可见——发送时会自动尝试激活微信窗口。建议保持微信窗口打开状态（可以放在其他虚拟桌面）。

</details>

<details>
<summary><strong>支持 macOS 吗？</strong></summary>

Windows 仍是正式推荐平台。macOS 推荐实验性的 `WECHAT_BACKEND=mac_hybrid` 路径：读取由 chatlog 服务解密后的本地微信数据库，发送消息时再通过辅助功能操作微信窗口。它需要当前微信账号目录中存在 `all_keys.json`，并需要本地 chatlog HTTP 服务运行在 `CHATLOG_BASE_URL`。`WECHAT_BACKEND=mac_ui` 仍保留为界面自动化兜底，但不适合稳定读取聊天消息。

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

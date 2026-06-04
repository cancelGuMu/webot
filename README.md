# WeChatBot

> 微信群聊 AI 助手 —— 原生 WCDB 直读，零外部依赖，开箱即用。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue?style=flat-square&logo=windows" />
  <img src="https://img.shields.io/badge/python-3.10+-green?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/AI-Claude%20%7C%20DeepSeek-purple?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" />
  <img src="https://img.shields.io/badge/ui-React%20%2B%20Tailwind-cyan?style=flat-square&logo=react" />
</p>

---

## 它是什么

WeChatBot 是一个运行在 Windows 上的微信群聊机器人。它通过原生读取微信加密数据库获取消息，无需任何 Hook、注入或网页版微信，安全不封号。

你可以把它当做一个**群聊私人助理**：

- 错过几百条消息？对它说一句"总结一下"，立刻告诉你前面聊了什么
- 需要查资料？@它提问，它会结合联网搜索回答
- 群里聊嗨了？它能感知聊天节奏，恰到好处地插话
- 有人开车？自动警告，维护群聊氛围

内置 **React + Tailwind CSS** 仪表盘，WebSocket 实时推送运行状态。双击 EXE 即可启动，无需命令行。

---

## 功能一览

<table>
  <tr>
    <td width="50%">
      <strong>🔍 智能总结</strong><br/>
      发送"总结一下""前面说了什么"等关键词，自动定位你的上一条消息，将之后的所有聊天内容交给 AI 生成结构化总结。
    </td>
    <td width="50%">
      <strong>💬 AI 对话</strong><br/>
      @机器人 提问，支持 Claude 和 DeepSeek 两大模型后端，可选联网搜索增强（DuckDuckGo，免费免 Key）。
    </td>
  </tr>
  <tr>
    <td>
      <strong>📊 三级 Map-Reduce</strong><br/>
      超长对话自动分块 → 合并，安全处理 999+ 条消息不会超出模型上下文窗口。
    </td>
    <td>
      <strong>🎯 主动发言</strong><br/>
      根据群聊活跃度自动插话（可开关），5 种速率模式 × 概率门控，自然不突兀。
    </td>
  </tr>
  <tr>
    <td>
      <strong>🧠 长期记忆</strong><br/>
      每 20 条消息自动整合群聊记忆日记，注入 AI 上下文，让机器人越聊越懂群。
    </td>
    <td>
      <strong>🛡️ 低俗内容过滤</strong><br/>
      40+ 正则规则前后双向检测，自动发出文明提醒，同时过滤 AI 自身输出确保安全。
    </td>
  </tr>
  <tr>
    <td>
      <strong>📌 粘性提及</strong><br/>
      发送空 @ 后，下一条消息自动作为 @ 处理。不用每次都打 @机器人。
    </td>
    <td>
      <strong>🏷️ 昵称系统</strong><br/>
      wxid 绑定自定义昵称，AI 输出自动替换，群聊体验更自然。
    </td>
  </tr>
  <tr>
    <td>
      <strong>🖥️ Web 仪表盘</strong><br/>
      React + Tailwind CSS 构建，WebSocket 实时推送运行状态、消息处理量、AI 后端延迟。
    </td>
    <td>
      <strong>⚙️ 管理命令</strong><br/>
      支持改名 / 删除昵称 / 帮助等管理命令，管理员 wxid 鉴权。
    </td>
  </tr>
</table>

---

## 快速开始

### 前置条件

- **Windows 10 或 11**
- **Python 3.10+**（仅源码运行需要）
- **微信桌面版** 已登录
- **[WeFlow](https://github.com/hicccc77/WeFlow)** —— 只需安装并运行一次（用于生成 `wcdb_api.dll` 和配置文件），之后机器人独立运行，不需要启动 WeFlow

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/cancelGuMu/wechat-group-bot/releases) 下载 `WeChatBot.exe`，双击运行。

首次运行会弹出配置向导，引导你输入 API Key（可在 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 免费注册，新用户有赠送额度）。

### 方式二：从源码运行

```bash
git clone https://github.com/cancelGuMu/wechat-group-bot.git
cd wechat-group-bot
pip install -r requirements.txt
python launcher.py
```

### 方式三：自行打包

```bash
pip install pyinstaller
pyinstaller build.spec
# 输出: dist/WeChatBot.exe
```

---

## 配置

所有配置通过项目根目录的 `.env` 文件管理。首次运行会自动从 `.env.example` 创建模板。

### 核心配置

```env
# AI 后端选择 (claude 或 deepseek)
AI_BACKEND=deepseek

# DeepSeek API Key（AI_BACKEND=deepseek 时必填）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek-v4-flash        # v4-flash(推荐) 或 v4-pro

# Claude API Key（AI_BACKEND=claude 时必填）
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
SUMMARIZE_MODEL=claude-haiku-4-5-20251001

# 机器人显示名（用于 @ 检测，填你的机器人在群里的昵称）
BOT_DISPLAY_NAME=群聊小助手

# 监控的群聊（逗号分隔，留空 = 所有群聊）
WECHAT_GROUPS=

# 管理员 wxid（可管理昵称和设置）
ADMIN_WXID=
```

### 功能开关

```env
# 主动发言（机器人自动插话）
PROACTIVE_ENABLED=false

# 低俗内容过滤
VULGAR_GUARD_ENABLED=true

# 粘性提及（空 @ 后下一条消息自动作为 @）
STICKY_MENTION_ENABLED=true

# 联网搜索增强
ENABLE_WEB_SEARCH=true
```

### 高级调参

```env
# 轮询间隔（秒，默认 1.0，增大可降低 CPU 占用）
POLL_INTERVAL_SEC=1.0

# 总结最大消息数（群聊 999+ 时可增大）
MAX_MESSAGES_FOR_SUMMARY=5000

# Map-Reduce 每块大小
CHUNK_SIZE=400

# 去重窗口（秒，同一群聊两次触发之间的最小间隔）
DEDUP_WINDOW_SEC=60
```

完整配置项见 [`.env.example`](.env.example)。

---

## 使用指南

### 基础用法

| 操作 | 方式 |
|------|------|
| 群聊总结 | 发送 `总结一下` / `前面说了什么` / `聊天总结` |
| AI 问答 | `@机器人 <你的问题>` |
| 空 @ 粘性 | 发送 `@机器人`（不带文字），然后在 60 秒内发送你的问题 |
| Web 仪表盘 | 启动后自动打开 `http://127.0.0.1:8765` |

### 管理命令

发送 `@机器人 <命令>`（需配置 ADMIN_WXID）：

| 命令 | 说明 |
|------|------|
| `改名 wxid 新昵称` | 为指定 wxid 绑定昵称 |
| `删除昵称 wxid` | 删除指定 wxid 的昵称 |
| `帮助` | 查看可用命令列表 |

### 主动发言模式

开启 `PROACTIVE_ENABLED=true` 后，机器人会根据群聊消息速率自动切换行为模式：

| 模式 | 速率阈值 | 行为 |
|------|----------|------|
| SLEEP | < 1.5 msg/min | 完全沉默 |
| QUIET | 1.5 ~ 4.0 | 偶尔参与，低频 |
| CASUAL | 4.0 ~ 6.5 | 正常聊天节奏 |
| LIVELY | 6.5 ~ 8.5 | 活跃参与 |
| BURST | > 8.5 | 高频插话 |

阈值可通过 `PROACTIVE_RATE_*` 系列配置项调整。建议先用 `python tools/analyze_chat_rhythm.py` 分析群聊节奏后再校准。

---

## 与同类项目对比

| | WeChatBot | 其他微信机器人 |
|---|---|---|
| 消息获取 | WCDB 原生数据库直读 | Hook / 注入 / 网页协议 |
| 封号风险 | 极低（只读数据库文件） | 高（注入 / 协议模拟） |
| 外部依赖 | 仅需 WeFlow 初始化一次 | 常驻进程 / Docker / 特定微信版本 |
| UI | 原生桌面窗口 + Web 仪表盘 | 通常仅命令行 |
| 多群支持 | ✅ | 部分支持 |
| AI 后端 | Claude / DeepSeek 双选 | 通常单一 |

---

## 常见问题

<details>
<summary><strong>必须安装 WeFlow 吗？</strong></summary>

是的，但只需要安装并运行一次。WeFlow 会生成 `wcdb_api.dll`（WCDB 数据库读取接口）和 `WeFlow-config.json`（微信路径配置）。之后 WeChatBot 独立运行，不再需要 WeFlow。

</details>

<details>
<summary><strong>会被封号吗？</strong></summary>

WeChatBot 只读取微信的本地加密数据库文件，不注入微信进程、不 Hook、不模拟协议。这是一种非常安全的只读方式，目前没有已知的封号案例。但任何第三方工具都有理论风险，请自行评估。

</details>

<details>
<summary><strong>支持哪些 AI 模型？</strong></summary>

- **DeepSeek**：V4 Flash（推荐，极速极低价）、V4 Pro（1M 上下文旗舰）
- **Claude**：Haiku 4.5（快速廉价）、Sonnet 4.5/4.6（更高质量）

切换模型只需修改 `.env` 中的 `AI_BACKEND` 和对应 Model 配置。

</details>

<details>
<summary><strong>API 调用费用高吗？</strong></summary>

不高。总结和聊天默认使用 DeepSeek V4 Flash，单价极低。普通群聊一天的总结费用通常不到 ¥0.10。你也可以切换为 Claude Haiku，同样以低成本和低延迟著称。

</details>

<details>
<summary><strong>如何停止机器人？</strong></summary>

点击仪表盘中的停止按钮，或在终端按 `Ctrl+C`。

</details>

<details>
<summary><strong>支持 macOS 吗？</strong></summary>

目前仅支持 Windows。macOS 版本需要处理完全不同的微信数据库加密方案，暂无计划。

</details>

---

## License

MIT © [cancelGuMu](https://github.com/cancelGuMu)

# WeChat Group Bot —— 微信群聊 AI 助手

基于 AI 的微信群聊智能机器人。原生 WCDB 数据库直读，**零外部依赖**。支持消息总结、AI 对话、主动参与、长期记忆、低俗内容过滤。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/python-3.10+-green?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" />
  <img src="https://img.shields.io/badge/status-active-success?style=flat-square" />
</p>

---

## 功能

| 功能 | 说明 |
|------|------|
| 智能总结 | 发送"总结一下"等关键词，自动定位你上一条消息，总结之后的所有聊天 |
| AI 对话 | @机器人 提问，获得基于大模型的对话回复 |
| Map-Reduce 分段 | 超长对话自动分块总结，支持三级 Map-Reduce |
| 主动参与 | 根据群聊活跃度自动插话（可开关），5 模式速率门控 |
| 长期记忆 | 每 20 条消息自动整合群聊记忆，注入 AI 上下文 |
| 低俗过滤 | 40+ 正则规则前后双向检测，自动警告 |
| Web 搜索增强 | DuckDuckGo 搜索增强 AI 回答 |
| 粘性提及 | 发送空 @ 后下一条消息自动作为 @ 处理 |
| 昵称系统 | wxid 绑定昵称，AI 输出自动替换 |
| 管理命令 | 改名 / 删除昵称 / 帮助 等 |

## 快速开始

### 前置条件

- Windows 10/11
- Python 3.10+
- 微信桌面版已登录
- [WeFlow](https://github.com/hicccc77/WeFlow) 至少安装并运行过一次（用于生成配置文件和 DLL）

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/cancelGuMu/wechat-group-bot/releases) 下载 `WeChatBot.exe`，双击运行。

首次运行会自动引导你输入 DeepSeek API Key（在 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 免费注册）。

### 方式二：源码运行

```bash
git clone https://github.com/cancelGuMu/wechat-group-bot.git
cd wechat-group-bot
pip install -r requirements.txt
python launcher.py
```

### 配置

所有配置通过 `.env` 文件管理。首次运行会自动从 `.env.example` 创建模板。

```env
# AI 后端
AI_BACKEND=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek-v4-flash

# 机器人身份
BOT_DISPLAY_NAME=群聊小助手
WECHAT_GROUPS=          # 留空 = 所有群聊

# 功能开关
PROACTIVE_ENABLED=false
VULGAR_GUARD_ENABLED=true
```

完整配置项见 `.env.example`。

## 技术架构

```
launcher.py (一键启动)
  └─ src/main.py
       └─ src/bot.py (编排器)
            ├─ src/db/         SQLite 消息持久化
            ├─ src/router.py   消息路由分发
            ├─ src/summarize/  AI 后端 (DeepSeek / Claude)
            ├─ src/proactive/  主动发言门控
            ├─ src/memory/     群聊记忆整合
            ├─ src/guard/      低俗内容过滤
            └─ src/wechat/
                 ├─ wcdb_backend.py   原生 WCDB 数据库直读
                 ├─ wcdb_client.py     DLL 加载 + DRM 补丁
                 ├─ window_controller  微信窗口操控
                 └─ extract_key.py     DPAPI 密钥提取
```

### 核心技术

- **WCDB 原生直读**：通过 `wcdb_api.dll` 直接读取微信加密数据库，获取完整消息历史和真实 wxid
- **DRM 绕过**：一字节内存补丁，使 DLL 可从任意进程调用
- **Web Dashboard**：React + Tailwind CSS 浅色主题 UI，WebSocket 实时状态推送
- **Map-Reduce 总结**：超长对话自动分块 → 合并，支持三级策略

## 项目结构

```
src/
├── main.py, bot.py, config.py, router.py    核心引擎
├── db/                SQLite 消息存储
├── summarize/         AI 后端（Claude / DeepSeek）
├── proactive/         主动发言（门控 / 模式 / 速率追踪）
├── memory/            群聊长期记忆整合
├── guard/             低俗内容过滤器
├── trigger/           触发词检测
├── wechat/            微信后端（wcdb 数据库直读）
├── web/               Web UI 服务端
├── utils/             工具（Web 搜索 / 日志）
├── admin.py           管理员命令
├── nickname.py        昵称管理
└── fun.py             抽签等小功能

ui/                    React Dashboard 前端
tools/                 开发工具（密钥提取 / 设置向导）
```

## FAQ

**Q: 需要安装 WeFlow 吗？**
首次使用需要安装 WeFlow 并运行一次，让它生成 `WeFlow-config.json` 和 `wcdb_api.dll`。之后机器人独立运行，不需要启动 WeFlow。

**Q: 支持哪些 AI 模型？**
默认使用 DeepSeek V4 Flash（极速低价）。也支持 Claude Haiku/Sonnet 和 DeepSeek V4 Pro。

**Q: 怎么获取 API Key？**
在 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 免费注册，新用户有赠送额度。

**Q: 机器人会自己发消息吗？**
默认只在被 @ 或触发关键词时回复。开启"主动发言"后，会根据群聊活跃度自动参与。

**Q: 怎么停止机器人？**
Ctrl+C，或点击 Dashboard 中的"停止运行"按钮。

## License

MIT

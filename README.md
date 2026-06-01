# WeChat Group Summarizer Bot

An AI-powered WeChat group chat bot that summarizes missed conversations and
responds to @mentions. Reads messages via WeFlow's local HTTP API and sends
replies via `PostMessage` — no UIA hooks, no DLL injection, no protocol reverse-engineering.

## Features

| Feature | Description |
|---------|-------------|
| **Smart Summarization** | Detects "what did I miss" intent; finds the user's last message timestamp; summarizes everything since |
| **AI Chat** | @bot with any question → conversational AI response (DeepSeek V4 Flash) |
| **Admin Controls** | Designated admin can manage nickname mappings via chat commands |
| **Map-Reduce** | Conversations exceeding the token budget are chunked, summarized per chunk, then merged |
| **Multi-Backend** | Pluggable AI (Claude / DeepSeek) and WeChat (WeFlow / wx4py / wxauto / UIA) backends |
| **Deduplication** | 60-second cooldown per group to prevent duplicate triggers |
| **Nickname Resolution** | Automatic wxid → display name mapping via WeFlow contacts API + manual overrides |
| **Graceful Degradation** | Exponential backoff on API errors; reconnection on WeChat window loss |

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  WeChat Desktop                   │
│  ┌────────────┐    ┌───────────────────────────┐ │
│  │ Local DB   │    │  Chat Window (Qt)         │ │
│  │ (WCDB)     │    │  ← PostMessage keystrokes │ │
│  └─────┬──────┘    └───────────▲───────────────┘ │
└────────┼───────────────────────┼──────────────────┘
         │ read                   │ send
         ▼                        │
┌─────────────────┐    ┌──────────┴──────────┐
│    WeFlow       │    │  WeFlowBackend       │
│  (localhost:    │◄───│  - HTTP polling      │
│   5031)         │    │  - PostMessage send  │
└─────────────────┘    └──────────┬───────────┘
                                  │
                         ┌────────▼───────────┐
                         │   MessageStore      │
                         │   (SQLite WAL)      │
                         └────────┬───────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
             TriggerDetector  DeepSeek/Claude  Admin Commands
                    │             │             │
                    └─────────────┼─────────────┘
                                  ▼
                           Reply → WeChat
```

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.10+
- WeChat Desktop 4.x (no specific version required)
- [WeFlow](https://github.com/hicccc77/WeFlow) (for message reading)
- DeepSeek or Anthropic API key

### Setup

```bash
# 1. Clone or extract the project
cd wechatbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API key, bot name, and group names

# 4. Start WeFlow and enable HTTP API
#    WeFlow → Settings → API Service → Start → copy the access token
#    Paste the token into .env as WEFLOW_TOKEN

# 5. Launch
python launcher.py
```

### First Run

1. WeFlow must be running with HTTP API enabled (port 5031)
2. WeChat must be logged in (window can be in the background — PostMessage doesn't need focus)
3. On first run, the bot resolves group names to internal WeChat IDs
4. Nicknames are loaded from WeFlow contacts + `data/nicknames.json`

## Usage

### Summary Mode

Send any of these in a monitored group:

- `之前发了什么` / `总结一下` / `错过了什么` / `聊天总结` / `说了啥`
- `summarize` / `what did i miss`

Or @mention the bot with summary-like content.

### AI Chat Mode

@mention the bot with any question that is NOT a summary request:

> @Gumu's chat bot 推荐一个周末去处

The bot responds conversationally using DeepSeek V4 Flash.

### Admin Commands

The bot admin (configured via `ADMIN_WXID`) can manage nicknames:

| Command | Effect |
|---------|--------|
| `@bot 改名 wxid_xxx = 昵称` | Add/update a nickname mapping |
| `@bot 删除昵称 wxid_xxx` | Remove a nickname mapping |
| `@bot 帮助` | Show available commands |

Nicknames are persisted to `data/nicknames.json`.

## Configuration Reference

### Required

| Variable | Description |
|----------|-------------|
| `AI_BACKEND` | AI provider: `deepseek` or `claude` |
| `DEEPSEEK_API_KEY` | DeepSeek API key (if using DeepSeek) |
| `ANTHROPIC_API_KEY` | Anthropic API key (if using Claude) |
| `BOT_DISPLAY_NAME` | Bot's WeChat display name |
| `WECHAT_GROUPS` | Comma-separated group names to monitor |
| `WEFLOW_TOKEN` | WeFlow HTTP API access token |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek model ID |
| `SUMMARIZE_MODEL` | `claude-haiku-4-5-20251001` | Claude model ID |
| `WECHAT_BACKEND` | `weflow` | WeChat backend: `weflow`, `uia`, `wx4py`, `wxauto` |
| `WEFLOW_URL` | `http://127.0.0.1:5031` | WeFlow API base URL |
| `ADMIN_WXID` | — | Bot admin's WeChat ID (for admin commands) |
| `POLL_INTERVAL_SEC` | `1.0` | WeFlow API poll interval |
| `DEDUP_WINDOW_SEC` | `60` | Min seconds between triggers per group |
| `MAX_MESSAGES_FOR_SUMMARY` | `5000` | Max messages per summary query |
| `CHUNK_SIZE` | `400` | Messages per chunk in Map-Reduce mode |
| `FALLBACK_WINDOW_HOURS` | `8` | Minimum summary window (fallback & safety net) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | `data/bot.log` | Log file path |

### AI Model Comparison

| Model | Context | Input Price | Best For |
|-------|---------|-------------|----------|
| `deepseek-v4-flash` | 1M | $0.14/M | Daily summaries (recommended) |
| `deepseek-v4-pro` | 1M | $0.44/M | Complex analysis |
| `claude-haiku-4-5` | 200K | $1.00/M | Claude ecosystem |
| `claude-sonnet-4-5` | 200K | $3.00/M | High-quality summaries |

## Project Structure

```
wechatbot/
├── src/
│   ├── main.py                  # Entry point, message dispatch, admin commands
│   ├── config.py                # .env loader, BotConfig dataclass
│   ├── db/
│   │   ├── schema.py            # SQLite DDL (messages, user_last_message, trigger_log)
│   │   └── store.py             # MessageStore: insert, query, dedup
│   ├── wechat/
│   │   ├── base.py              # AbstractWeChatBackend ABC
│   │   ├── weflow_backend.py    # WeFlow (HTTP read + PostMessage send)
│   │   ├── wx4py_backend.py     # wx4py (WeChat 4.1.7-4.1.8)
│   │   ├── uia_backend.py       # Raw UIA (WeChat 4.x, with COM tree wake-up)
│   │   └── wxauto_backend.py    # wxauto (WeChat 3.9.x)
│   ├── trigger/
│   │   └── detector.py          # Keyword + @mention trigger detection
│   ├── summarize/
│   │   ├── models.py            # Pydantic: SummaryResult, ParticipantContribution
│   │   ├── base.py              # AbstractSummarizer (chunking, retry, formatting)
│   │   ├── claude_backend.py    # ClaudeSummarizer (Anthropic SDK, Pydantic parse)
│   │   ├── deepseek_backend.py  # DeepSeekSummarizer (OpenAI SDK, tool calling)
│   │   ├── prompts.py           # System prompts, XML templates, token estimation
│   │   └── __init__.py          # Factory: create_summarizer(config)
│   └── utils/
│       └── logging_config.py    # Structured logging setup
├── data/
│   ├── messages.db              # SQLite database (auto-created)
│   ├── nicknames.json           # Manual wxid → nickname overrides
│   └── uia_dump.txt             # UIA diagnostic output
├── diagnose_wechat.py           # UIA tree diagnostic tool
├── launcher.py                  # One-click launcher (env checks, dep install)
├── start.bat                    # Windows double-click launcher
├── start.sh                     # Bash launcher
├── .env.example                 # Configuration template
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Data Flow

### Message Ingestion

```
WeFlow API poll (1s interval)
    → GET /api/v1/messages?talker={id}&limit=100
    → Parse JSON, extract sender/content/timestamp
    → Resolve wxid → display name (contacts API + nicknames.json)
    → Resolve @wxid mentions → @nickname in content
    → INSERT into messages table (dedup by serverId)
    → UPSERT user_last_message cursor
```

### Trigger Handling

```
Incoming message
    → self-filter (skip bot's own messages)
    → TriggerDetector.is_trigger()
        ├── is_keyword_match? → summary mode
        ├── is_admin + command? → admin mode
        └── is_at_mention? → AI chat mode
```

### Summary Generation

```
Trigger detected
    → dedup check (trigger_log, 60s window)
    → get_user_last_timestamp(chat, user)
        ├── found & not self → use that timestamp
        └── null or self → fallback (last 6h)
    → get_messages_since(chat, since_ts, limit=5000)
    → pre-resolve wxids in messages
    → estimate_tokens(messages)
        ├── ≤ budget → summarize_direct (1 API call)
        └── > budget → summarize_map_reduce (chunk → extract → merge)
    → resolve_wxids_in_text(output)
    → send reply via PostMessage
```

## Database Schema

### `messages`

| Column | Type | Description |
|--------|------|-------------|
| message_id | TEXT UNIQUE | MD5 of serverId + localId |
| chat_id | TEXT | WeChat group ID (e.g. `20968749111@chatroom`) |
| sender_id | TEXT | Sender's wxid |
| sender_name | TEXT | Resolved display name |
| content | TEXT | Message text |
| msg_type | INTEGER | 1=text, 3=image, 34=voice, etc. |
| timestamp | INTEGER | Unix seconds |
| created_at | INTEGER | Insertion timestamp |

Indexes: `(chat_id, timestamp DESC)`, `(chat_id, sender_id, timestamp DESC)`

### `user_last_message`

Materialized cursor per user per chat. UPSERTed on every message insert.

### `trigger_log`

Prevents duplicate triggers. Application-level TTL via `DEDUP_WINDOW_SEC`.

## WeChat Backends

| Backend | WeChat Version | Reading | Sending | Risk |
|---------|---------------|---------|---------|------|
| **weflow** (default) | 4.x+ | WeFlow HTTP API (local DB) | PostMessage (no focus) | Medium |
| uia | 4.x+ | Raw UIAutomation | PostMessage | Low |
| wx4py | 4.1.7-4.1.8 | wx4py callbacks | wx4py ReplyAction | Low |
| wxauto | 3.9.x | wxauto polling | wxauto SendMsg | Low |

## Troubleshooting

### WeFlow API unreachable

```
[ERROR] WeFlow API is not reachable at http://127.0.0.1:5031
```

- Ensure WeFlow is running
- WeFlow → Settings → API Service → Start
- Verify: `curl http://127.0.0.1:5031/health`
- Check `WEFLOW_TOKEN` in `.env` matches WeFlow's access token

### Messages contain wxid_xxx instead of nicknames

- Populate `data/nicknames.json` manually, or use admin command: `@bot 改名 wxid_xxx = 昵称`
- WeFlow contacts API only returns your personal contacts, not all group members
- Bot does a final-pass replacement on all AI output based on `data/nicknames.json`

### Reply sent to wrong chat

- Ensure WeChat window is not minimized
- The bot sends keystrokes via `PostMessage` to WeChat's HWND
- If WeChat is restarted, the HWND changes — bot auto-detects on next poll

### Empty UIA tree (uia backend)

- Run `python diagnose_wechat.py` for diagnostics
- WeChat 4.1.x requires Qt accessibility bridge activation
- Try: open Narrator (Win+Ctrl+Enter), start WeChat, close Narrator

## Legal Considerations

| Component | Status | Notes |
|-----------|--------|-------|
| DeepSeek / Claude API | ✅ Legal | Official paid API services |
| PostMessage (Win32) | ✅ Legal | Standard Windows API, equivalent to keyboard input |
| SQLite local storage | ✅ Legal | Data stays on your device |
| Win32 clipboard API | ✅ Legal | Standard Windows API |
| WeFlow (database reader) | ⚠️ Gray | Reads WeChat's local encrypted database; similar tools have received legal notices from Tencent |

**Recommendation**: This tool is designed for personal use in small groups. Do not use commercially or at scale without consulting legal counsel. Consider informing group members that a bot is present.

## Dependencies

```
anthropic        # Claude API (optional, if using Claude)
openai            # DeepSeek API (OpenAI-compatible)
python-dotenv     # .env configuration
pydantic          # Structured output models
pywin32           # Win32 API (window management, clipboard)
comtypes          # COM-level UIAutomation client registration
uiautomation      # UIA tree walking (for uia backend)
wx4py             # WeChat 4.1.7-4.1.8 backend (optional)
wxauto            # WeChat 3.9.x backend (GitHub, optional)
```

## License

MIT

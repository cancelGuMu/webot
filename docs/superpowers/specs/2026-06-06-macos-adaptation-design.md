# macOS Adaptation Design

## Goal

Add a macOS route for running and experimenting with the bot while preserving the existing Windows service flow exactly as the default path.

## Non-Goals

- Do not replace or refactor the Windows `wcdb` backend.
- Do not require Windows users to change `desktop.py`, `.env`, `requirements.txt`, or packaging.
- Do not attempt macOS WeChat database decryption in the first pass.

## Architecture

Windows remains on the current route:

```text
desktop.py -> WECHAT_BACKEND=wcdb -> WcdbBackend -> wcdb_api.dll + pywin32/uiautomation
```

macOS gets a separate route:

```text
desktop_mac.py -> Web server 127.0.0.1:7327 -> WECHAT_BACKEND=mac_ui -> MacUIBackend
```

`MacUIBackend` implements `AbstractWeChatBackend` using macOS system automation. It activates WeChat, optionally searches for configured chats, reads visible accessibility text, deduplicates newly visible lines, and sends replies by pasting through the clipboard and pressing Return.

## Components

- `requirements-macos.txt`: cross-platform Python dependencies, excluding Windows-only `pywin32`, `uiautomation`, and `comtypes`.
- `desktop_mac.py`: macOS launcher that starts the existing Web server, opens the dashboard in the browser, and does not use WebView2.
- `src/wechat/mac_ui_backend.py`: macOS WeChat backend and automation adapter.
- `src/bot.py`: add `WECHAT_BACKEND=mac_ui` selection while leaving `wcdb` selection unchanged.
- `src/web/server.py`: make diagnostics platform-aware so macOS reports macOS-specific checks instead of Windows dependency failures.
- `README.md`: document macOS experimental setup and its limitations.

## Behavior

`mac_ui` is an experimental backend. It requires WeChat to be open and macOS Accessibility permission granted to the terminal or Python process. It is intended to make the bot usable on macOS without sharing the Windows DLL path. It will be less stable than Windows database reading because it depends on the visible WeChat UI.

## Testing

- Unit test `Bot._create_wechat_backend()` returns `MacUIBackend` for `WECHAT_BACKEND=mac_ui`.
- Unit test `requirements-macos.txt` omits Windows-only dependencies.
- Unit test `MacUIBackend` deduplicates visible lines and emits standardized messages without importing Windows modules.
- Unit test diagnostics can run on non-Windows platforms without requiring `pywin32`.
- Run focused tests with Python 3.12 on macOS.
- Build frontend if frontend files change.


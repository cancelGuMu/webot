# Auto Chatlog Service Design

## Goal

Make macOS startup feel like one project: source runs and packaged app runs should automatically prepare the local chatlog service before `mac_hybrid` starts reading WeChat messages.

## Approach

Keep `chatlog_alpha` as a child process boundary, but make webot own its lifecycle. `MacHybridBackend.start()` will check `ChatlogClient.health()` before priming state. If the service is down, it will call a small Python service manager that starts chatlog and waits for `/health`.

## Components

- `src/wechat/mac_chatlog_service.py`: pure-Python lifecycle helper. It resolves source and PyInstaller resource paths, finds an existing `CHATLOG_BIN` or bundled `tools/macos_chatlog/chatlog-alpha`, starts it with `CHATLOG_DATA_DIR` and `CHATLOG_HTTP_ADDR`, writes logs under `data/chatlog_alpha.log`, and waits for health.
- `src/wechat/mac_hybrid_backend.py`: calls the helper before polling and reports `chatlog_starting`/`chatlog_down` through health status if startup fails.
- `build-macos.spec`: bundles `tools/macos_chatlog/chatlog-alpha` when present so app startup uses the same automatic path.
- `README.md`: changes macOS run instructions from "manually start chatlog" to "webot starts chatlog automatically; setup commands are only for key extraction/building/verifying."

## Error Handling

If chatlog is already healthy, startup is a no-op. If no binary exists, the backend logs a clear message and continues to report `chatlog_down`; the user can run `python3 tools/macos_chatlog_setup.py build-chatlog`. If the child process exits during startup, the exception includes the log path.

## Testing

Add unit coverage for the service manager using fake health checks and fake process launchers, plus a backend test proving `start()` calls the manager before priming chatlog state. Existing macOS adaptation and chatlog setup tests remain the regression suite.

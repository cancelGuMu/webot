# AGENTS.md

## 每次修改必须提交 Git 到本地

每次对代码的修改完成后，必须执行 `git add` 和 `git commit`，写清楚改动内容和原因。**只提交到本地仓库，不 push 到 GitHub。**

```bash
git add -A
git commit -m "<描述做了什么，为什么>"
```

## 每次修改必须重新打包

每次修改完成后，必须重新执行 PyInstaller 打包，生成最新的 `dist/webot.exe`。

```bash
# 如果修改了前端代码，先构建前端
cd ui && npm run build && cd ..
# 打包
pyinstaller build.spec
```

## 每次修改必须进行功能测试

每次修改完成后，必须运行完整测试套件，并对修改涉及的功能做针对性验证。

### 运行全部测试

```bash
python -m pytest tests/ -v
```

测试分两层：
- **单元测试** (`test_config.py`, `test_trigger.py`, `test_web_api.py`, `test_window_controller.py`) — 毫秒级，验证逻辑正确性
- **功能测试** (`test_functional.py`) — 启动真实 HTTP 服务器 + Playwright 无头浏览器，模拟用户点击操作

### 功能测试覆盖要求

每次修改后，必须验证被修改功能在实际浏览器中可用：

| 测试类别 | 覆盖功能 |
|---------|---------|
| API 端点 | Diagnose 返回结构、Sandbox 路由注册、POST allowlist、配置字段默认值 |
| 页面加载 | 前端 SPA 正常渲染，不出现空白页或连接错误 |
| 主题系统 | 暗色模式默认启用、Sun/Moon 切换按钮可用、localStorage 持久化 |
| 侧边栏导航 | 运行状态/系统配置/运行日志 标签页渲染、沙箱子标签可见 |
| 配置功能 | 导入导出按钮可见 |

### 手动验证清单

部分功能无法自动化测试（需要微信客户端或真实 API Key），修改这些模块后需手动验证：

1. **AI 聊天/总结** — 需要真实 API Key + 微信运行
2. **密钥提取** — 需要微信客户端运行
3. **主动发言** — 需要微信客户端 + 真实群聊
4. **昵称管理** — 需要 data/messages.db 有数据
5. **消息发送** — 需要微信窗口可见

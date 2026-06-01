# Gemma 4 使用说明（thinking / nothinking）

本目录提供了两个通道的最小可用调用方式：
- `thinking 通道（key1）`
- `nothinking 通道（key2）`

当前接口返回的可用模型名为：`gemma4:e2b`  
`thinking / nothinking` 是通过不同 Key 走不同通道来区分，不是模型名后缀区分。

> 建议先使用环境变量，不要把 API Key 直接写进代码。

## 1. 准备环境（Windows PowerShell）

```powershell
cd C:\Users\86158\Desktop\codex\gumu.skill\gemma4-usage
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. 配置 Key 和 URL

按你给的通道信息设置环境变量：

```powershell
$env:GEMMA_THINKING_URL="https://api-cz.top"
$env:GEMMA_THINKING_KEY="你的 thinking key"

$env:GEMMA_NOTHINKING_URL="https://api-cz.top"
$env:GEMMA_NOTHINKING_KEY="你的 nothinking key"
```

## 3. Python 调用示例

```powershell
python chat_demo.py --mode thinking --prompt "用三句话介绍你自己"
python chat_demo.py --mode nothinking --prompt "把下面内容整理成 3 条要点：今天要做产品发布"
```

## 3.1 启动网页聊天（推荐）

```powershell
cd C:\Users\86158\Desktop\codex\gumu.skill\gemma4-usage
.\run_web.ps1
```

然后打开：`http://127.0.0.1:8787`

## 4. curl 调用示例

thinking：
```powershell
curl -X POST "https://api-cz.top/v1/chat/completions" `
  -H "Authorization: Bearer $env:GEMMA_THINKING_KEY" `
  -H "Content-Type: application/json" `
  -d '{"model":"gemma4:e2b","messages":[{"role":"user","content":"你好，请简短自我介绍"}],"temperature":0.7}'
```

nothinking：
```powershell
curl -X POST "https://api-cz.top/v1/chat/completions" `
  -H "Authorization: Bearer $env:GEMMA_NOTHINKING_KEY" `
  -H "Content-Type: application/json" `
  -d '{"model":"gemma4:e2b","messages":[{"role":"user","content":"把这个需求拆成 5 个任务"}],"temperature":0.7}'
```

## 5. 常见报错

- `401 Unauthorized`：Key 错误或未设置。
- `404 model not found`：模型名与通道不匹配。
- `429`：请求过快或额度限制。
- 超时：网络或网关抖动，重试并适当降低 `max_tokens`。

## 6. 安全建议

- 不要把 Key 提交到 Git。
- 推荐在本机会话里临时注入环境变量。
- 若怀疑泄露，立刻在通道后台更换 Key。

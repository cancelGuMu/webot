param(
  [ValidateSet("thinking","nothinking")]
  [string]$Mode = "thinking"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (!(Test-Path ".venv")) {
  python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

if (Test-Path ".env.ps1") {
  . .\.env.ps1
}

Write-Host "[info] 启动聊天网站: http://127.0.0.1:8787"
Write-Host "[info] 当前默认模式: $Mode（可在页面右上角切换）"

python .\app.py

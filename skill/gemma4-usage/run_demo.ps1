param(
  [ValidateSet("thinking","nothinking")]
  [string]$Mode = "thinking",
  [string]$Prompt = "你好，请用三句话介绍你自己"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (!(Test-Path ".venv")) {
  python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt | Out-Null

if (Test-Path ".env.ps1") {
  . .\.env.ps1
}

python .\chat_demo.py --mode $Mode --prompt $Prompt

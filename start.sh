#!/usr/bin/env bash
set -euo pipefail

# WeChat Group Chat Summarizer — One-click launcher
# Usage: bash start.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "  WeChat 群聊总结机器人 - 一键启动"
echo "============================================"
echo ""

# ── 1. Check Python ──────────────────────────
if ! command -v python &>/dev/null; then
    echo -e "${RED}[错误] 未找到 Python，请先安装 Python 3.10+${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Python 已就绪"

# ── 2. Check .env ────────────────────────────
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[警告]${NC} 未找到 .env 配置文件，正在从模板创建..."
    cp .env.example .env
    echo ""
    echo "============================================"
    echo "  请先编辑 .env 文件，填入你的 API Key！"
    echo "============================================"
    echo ""
    echo "  必填项:"
    echo "    ANTHROPIC_API_KEY=sk-ant-your-key-here"
    echo "    BOT_DISPLAY_NAME=你的机器人微信昵称"
    echo ""
    echo "  编辑完成后，再次运行此脚本即可启动。"
    echo ""
    exit 0
fi
echo -e "${GREEN}[OK]${NC} .env 配置文件已找到"

# ── 3. Install dependencies ──────────────────
if ! python -c "import wxauto" &>/dev/null; then
    echo ""
    echo -e "${YELLOW}[信息]${NC} 正在安装依赖..."
    pip install -r requirements.txt
fi
echo -e "${GREEN}[OK]${NC} 依赖已就绪"

# ── 4. Pre-flight checklist ──────────────────
echo ""
echo "============================================"
echo "  启动前检查清单:"
echo "============================================"
echo "  [ ] 微信桌面版已登录（窗口不要最小化）"
echo "  [ ] .env 中的 BOT_DISPLAY_NAME 配置正确"
echo "  [ ] 建议使用微信小号运行"
echo ""
echo "  按 Ctrl+C 可随时停止机器人"
echo "============================================"
echo ""

# ── 5. Launch ────────────────────────────────
python -m src.main

# ── 6. Exit ──────────────────────────────────
echo ""
echo "机器人已停止。"

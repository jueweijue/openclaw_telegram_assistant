#!/bin/bash
# 加载环境变量并启动 bot
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a
exec python3 bot.py

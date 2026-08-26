#!/bin/bash
# KB-AI · macOS 停止入口 · v1.7.0
#
# Finder 双击或终端 ./stop.command:
#   1. macOS 自动开 Terminal
#   2. 切到本文件所在目录(= KB-AI U 盘根)
#   3. 调 pwsh 跑 stop.ps1(单源编排,Mac/Win 共用)
#
# 行为:
#   - 5 秒倒计时(用户按 Enter/Y 确认,N 取消)— 与 Windows stop.bat 行为对齐
#   - 调 stop.ps1 → 停止 5 容器 + 备份 data/ → 弹"现在可以拔出"对话框
#
# 故障排查:
#   - Gatekeeper:同 start.command
#   - 退出码透传 stop.ps1

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$DIR/stop.ps1" "$@"

#!/bin/bash
# KB-AI · macOS 启动入口 · v1.7.0
#
# Finder 双击或终端 ./start.command:
#   1. macOS 自动开 Terminal
#   2. 切到本文件所在目录(= KB-AI U 盘根)
#   3. 调 pwsh 跑 start.ps1(单源编排,Mac/Win 共用)
#
# 故障排查:
#   - 提示 "无法打开,因为它来自身份不明的开发者":右键 → 打开方式 → 打开
#   - 提示 "permission denied":终端跑 `chmod +x start.command`
#   - 提示 "command not found: pwsh":装 PowerShell 7+,`brew install --cask powershell`
#
# 退出码透传 start.ps1:0 = 成功,1 = 失败

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$DIR/start.ps1" "$@"

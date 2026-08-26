#!/bin/bash
# KB-AI · macOS 包脚本 · v1.7.0
#
# 用途:把 KB-AI 源打包成 KB-AI-M1-M3.zip(给客户升级用)。
# 替代 package.bat(原 .bat 保留给 Windows 客户机)。
# 单源逻辑在 package.ps1(Compress-Archive 跨平台,PS 5.1+ / pwsh 7+ 都支持)。
#
# 用法:
#   chmod +x package.sh
#   ./package.sh                # 默认从 ./ 打 zip 到 ../
#   ./package.sh KB-AI-M1-M3.zip  # 自定义输出文件名
#
# 故障排查:
#   - 提示 "command not found: pwsh":装 PowerShell 7+,`brew install --cask powershell`
#   - 提示 "permission denied":`chmod +x package.sh`

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_NAME="${1:-KB-AI-M1-M3.zip}"

# 调 package.ps1 跑实际打包(Compress-Archive 跨平台)
exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$DIR/package.ps1" -OutName "$OUT_NAME"

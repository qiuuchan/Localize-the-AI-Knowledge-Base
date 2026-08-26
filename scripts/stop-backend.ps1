<#
.SYNOPSIS
  KB-AI · 停止 FastAPI 后端服务

.DESCRIPTION
  读取 tmp/backend.pid 并结束对应 uvicorn 进程。
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'get-usb-root.ps1')
$rootDir = Get-UsbRoot
$pidFile = Join-Path $rootDir "tmp/backend.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "[KB-AI Backend] 未找到 PID 文件,后端可能未启动" -ForegroundColor Yellow
    exit 0
}

$pidStr = Get-Content $pidFile -Raw -ErrorAction SilentlyContinue
if (-not $pidStr) {
    Write-Host "[KB-AI Backend] PID 文件为空" -ForegroundColor Yellow
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$pidInt = [int]$pidStr.Trim()
try {
    $proc = Get-Process -Id $pidInt -ErrorAction Stop
    Stop-Process -Id $pidInt -Force -ErrorAction Stop
    Write-Host "[KB-AI Backend] 已停止进程 PID=$pidInt" -ForegroundColor Green
} catch {
    Write-Host "[KB-AI Backend] 进程 PID=$pidInt 不存在或已停止" -ForegroundColor Yellow
} finally {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

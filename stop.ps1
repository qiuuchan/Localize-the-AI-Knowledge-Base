<#
.SYNOPSIS
  KB-AI · 停止编排(单源 PowerShell 版)· v1.7.0

.DESCRIPTION
  ### 职责
    替换 stop.bat:5 步停止流程(后端 → 容器 → fsync 等待 → 自动备份 → 弹"可以拔"对话框)
    同一份脚本在 Windows(PS 5.1)和 macOS(pwsh 7.4+)下运行。

  ### 5 步流程(对应原 stop.bat)
    [1/5] 停止 FastAPI 后端容器 kb-ai-backend(关键:不停它直接弹盘会拒绝)
    [2/5] 停止 MinerU 解析服务(:8001,Mac: pkill;Win: Get-CimInstance Win32_Process)
    [3/5] 优雅停止所有容器(docker compose stop,10s 超时,失败转 kill)
    [4/5] 等待 5s SQLite 完成 fsync(可安全拔出)
    [5/5] 自动备份到电脑硬盘(scripts/backup.ps1)+ 弹"现在可以拔出"对话框

  ### 入口
    Windows:  双击 stop.bat(原 .bat 保留)
    macOS:    双击 stop.command(本目录)→ exec pwsh -File stop.ps1

  ### 退出码
    0 = 成功(数据已落盘,用户可弹 U 盘)
    1 = docker stop 非预期失败(但仍可安全拔出,仅日志告警)

.PARAMETER SkipBackup
  跳过自动备份(developer 用)

.PARAMETER SkipNotice
  跳过最后"现在可以弹出"对话框(测试用)

.EXAMPLE
  pwsh -NoProfile -ExecutionPolicy Bypass -File stop.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File stop.ps1 -SkipBackup -SkipNotice

.NOTES
  PowerShell 5.1 兼容。
  沿用 lib/ 共享助手(log + platform-utils + load-env)。
#>

[CmdletBinding()]
param(
    [Parameter(DontShow = $true)] [switch]$SkipBackup = $false,
    [Parameter(DontShow = $true)] [switch]$SkipNotice = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# dot-source 共享助手
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'scripts/lib/Write-Log.ps1')
. (Join-Path $PSScriptRoot 'scripts/lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'scripts/lib/platform-utils.ps1')
. (Join-Path $PSScriptRoot 'scripts/get-usb-root.ps1')

Initialize-LogFile -ScriptName "stop"

$Platform = Get-KBAIPlatform
$RootDir = Get-UsbRoot

Write-LogHost ""
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost "   KB-AI  正在停止服务...  (请不要关闭此窗口)" -ForegroundColor Cyan
Write-LogHost "   平台: $Platform" -ForegroundColor Gray
Write-LogHost "   项目根: $RootDir" -ForegroundColor Gray
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost ""


# ----------------------------------------------------------------------
# [1/5] 停止 FastAPI 后端容器 kb-ai-backend
# ----------------------------------------------------------------------

Write-LogHost "[1/5] 停止 FastAPI 后端容器 · kb-ai-backend..." -ForegroundColor Cyan

Push-Location $RootDir
$backendStopped = $false
try {
    & docker compose stop kb-ai-backend 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $backendStopped = $true
    } else {
        Write-LogHost "   [警告] docker compose stop kb-ai-backend 失败,尝试强制停止..." -ForegroundColor Yellow
        & docker compose kill kb-ai-backend 2>&1 | Out-Null
    }
} catch {
    Write-LogHost "   [警告] 停止 kb-ai-backend 时出错:$_" -ForegroundColor Yellow
}
if ($backendStopped) {
    Write-LogHost "   KB-AI 后端容器已停止" -ForegroundColor Green
} else {
    Write-LogHost "   KB-AI 后端容器停止状态未知(可能未运行)" -ForegroundColor Yellow
}
Write-LogHost ""


# ----------------------------------------------------------------------
# [2/5] 停止 MinerU 解析服务
# ----------------------------------------------------------------------

Write-LogHost "[2/5] 停止 MinerU 解析服务..." -ForegroundColor Cyan

$mineruKilled = $false
try {
    if ($Platform -eq 'macOS') {
        # macOS:pkill mineru_server.py
        $procs = & pgrep -f "mineru_server.py" 2>&1
        foreach ($pid in $procs) {
            $pidStr = "$pid".Trim()
            if ($pidStr -match '^\d+$') {
                & kill -9 $pidStr 2>&1 | Out-Null
                $mineruKilled = $true
            }
        }
    } else {
        # Windows:Get-CimInstance Win32_Process 找 mineru 进程
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            if ($p.CommandLine -like '*mineru_server.py*') {
                try {
                    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                    $mineruKilled = $true
                } catch {
                    # 单个进程失败不影响
                }
            }
        }
    }
} catch {
    # pgrep / Get-CimInstance 失败,忽略
}

if ($mineruKilled) {
    Write-LogHost "   MinerU 解析服务已停止" -ForegroundColor Green
} else {
    Write-LogHost "   MinerU 解析服务未运行(或已停止)" -ForegroundColor Gray
}
Write-LogHost ""


# ----------------------------------------------------------------------
# 检查 Docker 是否在跑
# ----------------------------------------------------------------------

$dockerRunning = $false
try {
    $null = & docker info 2>&1
    $dockerRunning = $LASTEXITCODE -eq 0
} catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-LogHost "   Docker Desktop 未运行,跳过容器停止" -ForegroundColor Gray
    Write-LogHost ""
} else {

    # ----------------------------------------------------------------------
    # [3/5] 优雅停止所有容器
    # ----------------------------------------------------------------------

    Write-LogHost "[3/5] 停止 Docker 容器 · 给 10 秒优雅退出..." -ForegroundColor Cyan
    try {
        & docker compose stop 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-LogHost "   [警告] docker compose stop 失败,尝试强制停止..." -ForegroundColor Yellow
            & docker compose kill 2>&1 | Out-Null
        }
    } catch {
        Write-LogHost "   [警告] 停止容器时出错:$_" -ForegroundColor Yellow
    }
    Write-LogHost "   容器已停止" -ForegroundColor Green
    Write-LogHost ""


    # ----------------------------------------------------------------------
    # [4/5] 等待 SQLite 完成 fsync
    # ----------------------------------------------------------------------

    Write-LogHost "[4/5] 等待 SQLite 完成数据落盘..." -ForegroundColor Cyan
    for ($i = 5; $i -ge 1; $i--) {
        Write-LogHost "   $i 秒后可以安全弹出 U 盘..." -ForegroundColor Gray
        Start-Sleep -Seconds 1
    }
    Write-LogHost "   数据已落盘" -ForegroundColor Green
    Write-LogHost ""
}

Pop-Location


# ----------------------------------------------------------------------
# [5/5] 自动备份 + 弹"现在可以拔出"对话框
# ----------------------------------------------------------------------

if (-not $SkipBackup) {
    Write-LogHost "[5/5] 备份数据到电脑硬盘 · scripts/backup.ps1..." -ForegroundColor Cyan
    $backupScript = Join-Path $RootDir 'scripts/backup.ps1'
    if (Test-Path -LiteralPath $backupScript) {
        try {
            & pwsh -NoProfile -ExecutionPolicy Bypass -File $backupScript -Quiet 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-LogHost "   [警告] 自动备份失败,不影响安全弹出" -ForegroundColor Yellow
                Write-LogHost "          可稍后手动跑 scripts/backup.ps1 排查" -ForegroundColor Gray
            } else {
                Write-LogHost "   备份完成" -ForegroundColor Green
            }
        } catch {
            Write-LogHost "   [警告] 备份脚本异常:$_" -ForegroundColor Yellow
        }
    } else {
        Write-LogHost "   [警告] 找不到 backup.ps1:$backupScript" -ForegroundColor Yellow
    }
    Write-LogHost ""
}


# ----------------------------------------------------------------------
# 弹"现在可以拔出"对话框(Mac: osascript;Win: WinForms)
# ----------------------------------------------------------------------

if (-not $SkipNotice) {
    $message = @"
KB-AI 已完全停止,SQLite 数据已落盘。

现在您可以安全弹出 U 盘了!

操作步骤:
  1. 桌面/访达找到 USB SSD 图标
  2. 拖到废纸篓(macOS)或右键 → 弹出(Windows)
  3. 等待提示"已卸载"或"安全地移除设备"
  4. 物理拔出 U 盘

为什么不直接拔?请阅读 docs/safe-eject.md
关键原因:SQLite 数据库需要 fsync 才能保证一致
"@

    try {
        Show-KBAINotice -Message $message -Title "KB-AI · 安全弹出"
    } catch {
        Write-LogHost ""
        Write-LogHost "============================================================" -ForegroundColor Green
        Write-LogHost "   ✓ KB-AI 已完全停止,SQLite 数据已落盘" -ForegroundColor Green
        Write-LogHost "   现在您可以安全弹出 U 盘了!" -ForegroundColor Green
        Write-LogHost "============================================================" -ForegroundColor Green
    }
}

Write-LogHost ""
Close-LogFile
exit 0

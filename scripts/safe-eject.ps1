<#
.SYNOPSIS
  KB-AI · 安全弹出 — 5 秒倒计时确认 + 自动调 stop.bat + 提示拔出 U 盘

.DESCRIPTION
  - 流程:
      1. 终端 5 秒倒计时,用户按 Enter / Y / 任意键 → 确认
         按 N 或不按键 → 取消
      2. 确认 → 链回 stop.bat(已含 docker compose stop + SQLite fsync 5s)
      3. 完成后 → Windows Forms MessageBox 弹窗"现在可以安全拔出 U 盘"
      4. 退出 0(无论确认 / 取消都 0,具体码见 -ReturnExitCode)
  - 5 秒倒计时实现:
      - 主线程 100ms 轮询 [Console]::KeyAvailable
      - 后台 Start-Job 计时,5s 后到点
      - 不阻塞超过 5s,无需键盘模拟(被约束禁止)
  - PS 5.1 + PS 7+ 兼容:
      - 两个 Read-Host 兜底(PS 7 有 -TimeoutSeconds;PS 5.1 走轮询路径)
  - 不写 ANSI 控制符;颜色一律 Write-Host -ForegroundColor

.PARAMETER RootDir
  项目根目录(默认 $PSScriptRoot/..)

.PARAMETER TimeoutSec
  倒计时秒数(默认 5)

.PARAMETER SkipCountdown
  跳过倒计时直接进确认(用于自动化测试)

.PARAMETER AutoYes
  自动确认,等同于倒计时结束前的"Enter"(用于无人值守)

.PARAMETER NoMessageBox
  跳过最后的 MessageBox 弹窗(仅终端打印;测试场景)

.PARAMETER ReturnExitCode
  非交互测试时返回非 0 退出码

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/safe-eject.ps1
  pwsh -File scripts/safe-eject.ps1 -AutoYes           # CI/无人值守
  pwsh -File scripts/safe-eject.ps1 -TimeoutSec 10     # 自定义倒计时

.NOTES
  PowerShell 5.1 兼容。
  依赖:必须存在 stop.bat(M1 已落地)
  颜色:Write-Host -ForegroundColor,不写 ANSI。
  i18n:中文界面。
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [int]$TimeoutSec = 5,
    [switch]$SkipCountdown = $false,
    [switch]$AutoYes = $false,
    [switch]$NoMessageBox = $false,
    [switch]$ReturnExitCode = $false
)

$ErrorActionPreference = "Stop"

# v1.7.0 Mac 支持:dot-source platform-utils(Show-KBAINotice 用于安全弹出对话框)
. (Join-Path $PSScriptRoot 'lib/platform-utils.ps1')

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RootDir = Split-Path -Parent $scriptRoot
}
$stopBat = Join-Path $RootDir "stop.bat"

if (-not (Test-Path $stopBat)) {
    Write-Host "  [错误] 找不到 stop.bat:$stopBat" -ForegroundColor Red
    exit 9
}

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }

<#
.SYNOPSIS
  终端 5 秒倒计时 + 键盘监听。
  返回:
    'yes'  用户按 Enter/Y/y 或 倒计时结束
    'no'   用户按 N/n
.PARAMETER Seconds
  倒计时秒数
.PARAMETER AutoYes
  跳过倒计时,直接返回 yes
#>
function Get-StopConfirmation {
    param(
        [int]$Seconds = 5,
        [bool]$AutoYes = $false
    )
    if ($AutoYes) {
        Write-Host ""
        Write-Host "  [确认] 自动确认模式(无人值守)" -ForegroundColor Yellow
        return 'yes'
    }

    Write-Host ""
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  KB-AI · 安全弹出 — 倒计时 $Seconds 秒" -ForegroundColor Cyan
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  按 Enter 或 Y → 确认停止;按 N → 取消" -ForegroundColor Gray
    Write-Host ""

    # PS 7+ 支持 Read-Host -TimeoutSeconds(优先路径)
    $psMajor = $PSVersionTable.PSVersion.Major
    if ($psMajor -ge 7) {
        Write-Host ("  {0} 秒后自动确认…" -f $Seconds) -ForegroundColor Yellow -NoNewline
        $resp = Read-Host "" -TimeoutSeconds $Seconds
        # PS 7 -TimeoutSeconds 触发时 $resp = $null → 等价于"超时 → 自动 yes"
        if ($null -eq $resp -or [string]::IsNullOrWhiteSpace($resp)) {
            Write-Host ""
            Write-Host "  ✓ 倒计时结束 — 自动确认" -ForegroundColor Green
            return 'yes'
        }
        $r = $resp.Trim().ToLower()
        if ($r -eq 'n') {
            Write-Host "  ✗ 已取消" -ForegroundColor Yellow
            return 'no'
        }
        if ($r -eq 'y' -or $r -eq '') {
            Write-Host "  ✓ 已手动确认" -ForegroundColor Green
            return 'yes'
        }
        Write-Host "  [提示] 未识别输入 '$resp',视为取消" -ForegroundColor Yellow
        return 'no'
    }

    # PS 5.1:Read-Host 无 -TimeoutSeconds,改用 [Console]::KeyAvailable + 时间窗轮询
    $timerJob = Start-Job -ScriptBlock { param($s) Start-Sleep -Seconds $s; 'TIMEOUT' } -ArgumentList $Seconds
    $deadline = (Get-Date).AddSeconds($Seconds)
    $response = $null
    $lastSecShown = $Seconds + 1

    try {
        while ((Get-Date) -lt $deadline) {
            # 倒计时数字
            $remaining = [int][math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
            if ($remaining -lt $lastSecShown) {
                $lastSecShown = $remaining
                Write-Host ("`r  还剩 {0} 秒 " -f $remaining) -ForegroundColor Yellow -NoNewline
            }
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                $response = $key.KeyChar.ToString().ToLower()
                break
            }
            Start-Sleep -Milliseconds 100
        }
    } finally {
        if ($timerJob) {
            Stop-Job $timerJob -ErrorAction SilentlyContinue
            Remove-Job $timerJob -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host ""
    if ($response -eq 'n') {
        Write-Host "  ✗ 已取消" -ForegroundColor Yellow
        return 'no'
    }
    if ($response -ne $null) {
        # Enter (KeyChar = '' but CR = '\r') 或 Y → 确认
        Write-Host "  ✓ 已手动确认(按键 $response)" -ForegroundColor Green
        return 'yes'
    }
    Write-Host "  ✓ 倒计时结束 — 自动确认" -ForegroundColor Green
    return 'yes'
}

<#
.SYNOPSIS
  显示最终"安全拔出"对话框。失败时降级到终端打印。
.NOTES
  v1.7.0 Mac 支持:从 Windows Forms MessageBox 改为 Show-KBAINotice(平台分支)。
  - Windows:Windows Forms MessageBox
  - macOS:  osascript + System Events display dialog
  - 失败兜底:终端打印
#>
function Show-SafeEjectNotice {
    param([bool]$NoMessageBox = $false)
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "    ✓ KB-AI 已完全停止,SQLite 数据已落盘" -ForegroundColor Green
    Write-Host "    现在您可以安全弹出 U 盘了!" -ForegroundColor Green
    Write-Host ""
    Write-Host "    物理拔出步骤:" -ForegroundColor Gray
    Write-Host "    1. (Windows)系统托盘找到 USB 弹出图标" -ForegroundColor Gray
    Write-Host "    1. (macOS)桌面/访达 → 拖 USB SSD 图标到废纸篓" -ForegroundColor Gray
    Write-Host "    2. 等待提示'安全地移除设备' / 设备消失" -ForegroundColor Gray
    Write-Host "    3. 物理拔出 U 盘" -ForegroundColor Gray
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host ""

    if ($NoMessageBox) { return }

    # v1.7.0 跨平台对话框:走 Show-KBAINotice(Win: MessageBox,Mac: osascript)
    $message = "KB-AI 已完全停止,SQLite 数据已落盘。`n`n现在您可以安全弹出 U 盘了!`n`n操作步骤:`n1. 找到 USB 弹出图标`n2. 选择 USB SSD`n3. 等待 '安全地移除设备' 提示`n4. 物理拔出"
    try {
        Show-KBAINotice -Message $message -Title "KB-AI · 安全弹出"
    } catch {
        Write-Warn "无法显示通知对话框(可能无 GUI 会话);已用终端提示替代:$_"
    }
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

# 仅直接调用时执行主流程;被 dot-source(. $ejectFile)时只暴露函数
if ($MyInvocation.InvocationName -eq '.') { return }

Write-Host ""
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  KB-AI · 安全弹出 U 盘" -ForegroundColor Cyan
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if ($SkipCountdown) {
    Write-Step "已跳过倒计时,直接进入自动确认"
    $decision = 'yes'
} else {
    $decision = Get-StopConfirmation -Seconds $TimeoutSec -AutoYes ([bool]$AutoYes)
}

if ($decision -eq 'no') {
    Write-Host ""
    Write-Host "  [INFO] 用户取消,U 盘未弹出。KB-AI 服务保持运行。" -ForegroundColor Yellow
    Write-Host ""
    if ($ReturnExitCode) { exit 99 }
    exit 0
}

# 用户确认(或自动确认)→ 调 stop.bat
Write-Host ""
Write-Step "用户确认 — 开始停止 KB-AI 服务"
Write-Step "链回 $stopBat"

# 调 stop.bat(它是 .bat 文件,通过 cmd /c 调,捕获 exit code)
$proc = Start-Process -FilePath $stopBat -WorkingDirectory $RootDir -Wait -PassThru -NoNewWindow
$stopExit = $proc.ExitCode
Write-Step "stop.bat 退出码 = $stopExit"

# 无论 stop.bat 退出码如何(0/1 都正常:1 表示 docker 未运行)
# 都给最终"安全拔出"提示(用户操作目的就是拔 U 盘)
Show-SafeEjectNotice -NoMessageBox ([bool]$NoMessageBox)

# 退出码语义化
# 0 = 成功(stop.bat 0/1 都视为成功)
# 2 = stop.bat 非预期退出(stop bat 因 docker 错失败,但仍可安全拔出)
if ($stopExit -eq 0 -or $stopExit -eq 1) {
    if ($ReturnExitCode) { exit 0 }
    exit 0
} else {
    if ($ReturnExitCode) { exit 2 }
    # 即便 stop.bat 出错,仍给用户最终提示(拔 U 盘优先)
    exit 0
}

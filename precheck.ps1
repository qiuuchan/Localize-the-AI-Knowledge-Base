<#
.SYNOPSIS
  KB-AI · 客户机预检 · v1.7.0(替代 precheck.bat)

.DESCRIPTION
  ### 职责
    5 秒判断客户电脑是否能跑 KB-AI(5 容器 + 后端)。start.ps1 阶段 0 调本脚本,
    失败 exit 1 → 整个启动流程中止。

  ### 5 项检查(全平台等价)
    [1/5] CPU 虚拟化
        - Windows:Get-CimInstance Win32_Processor.VirtualizationFirmwareEnabled
        - macOS:  Apple Silicon(arm64)永远 True;Intel 查 sysctl hw.optional.hv
    [2/5] OS 版本
        - Windows:Win10 1809+ (Build 17763+) / Win11 (Build 22000+)
        - macOS:  macOS 13+(Ventura)
    [3/5] 磁盘剩余空间
        - 任意平台:Get-KBAIDiskFreeGB($rootDir)≥ 10 GB
    [4/5] 内存
        - 任意平台:Get-KBAIMemoryGB()≥ 4 GB
    [5/5] 平台专属
        - Windows:S Mode 检测(注册表 EditionID + SKU)
        - macOS:  SIP 状态 + Docker Desktop 是否安装

  ### 退出码
    0 = 全部通过
    1 = 至少 1 项失败
    2 = 致命(如 dot-source 失败)

  ### v1.7.0 与 v1.5.2.1 precheck.bat 关系
    - 不删除 precheck.bat(给 Windows 客户机保留)
    - 新 .ps1 走 PowerShell,与 start.ps1 同语言
    - 行为对齐:5 项检查 + 失败立即 exit 1

.PARAMETER RootDir
  可选:项目根目录(默认从 $PSScriptRoot 上溯 1 级)

.PARAMETER Quiet
  跳过 console 输出,只写日志(供自动化调用)

.EXAMPLE
  pwsh -NoProfile -ExecutionPolicy Bypass -File precheck.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File precheck.ps1 -RootDir "E:/" -Quiet

.NOTES
  PowerShell 5.1 兼容。
  UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding $false)。
  dot-source 守卫:$MyInvocation.InvocationName -eq '.' → return。
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [switch]$Quiet = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# dot-source 平台工具 + 写日志助手
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'scripts/lib/platform-utils.ps1')
. (Join-Path $PSScriptRoot 'scripts/lib/Write-Log.ps1')

Initialize-LogFile -ScriptName "precheck"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    if ($PSScriptRoot) {
        # Split-Path -Parent "E:\" (Windows 根盘符)返回空串,需要兜底
        $parent = Split-Path -Parent $PSScriptRoot
        if ($parent -and $parent -ne $PSScriptRoot) {
            $RootDir = $parent
        } else {
            $RootDir = $PSScriptRoot
        }
    } else {
        $RootDir = (Get-Location).Path
    }
}

$platform = Get-KBAIPlatform

# ----------------------------------------------------------------------
# 5 项检查实现
# ----------------------------------------------------------------------

$Results = New-Object System.Collections.Generic.List[object]   # 收集每项的 (Display, Level, Detail) — Level: 0=PASS, 1=WARN, 2=FAIL
$FailCount = 0
$WarnCount = 0

function _Add-Result {
    param(
        [string]$Display,
        [int]$Level,    # 0=PASS, 1=WARN, 2=FAIL
        [string]$Detail
    )
    # List.Add 是可变操作,跨函数边界作用域安全(避免数组 += 的 op_Addition 陷阱)
    [void]$Results.Add([pscustomobject]@{
        Display = $Display
        Level   = $Level
        Detail  = $Detail
    })
    if ($Level -ge 2) { $script:FailCount++ }
    elseif ($Level -eq 1) { $script:WarnCount++ }
}


# [1/5] CPU 虚拟化
$virt = Get-KBAICpuVirtualization
if ($virt.Supported) {
    _Add-Result "✓ 虚拟化" 0 "启用($($virt.Detail))"
} else {
    _Add-Result "✗ 虚拟化" 2 "未启用($($virt.Detail))"
}


# [2/5] OS 版本
$osVer = Get-KBAIOSVersion
$osOk = $false
$osDetail = ""

if ($platform -eq 'Windows') {
    $build = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
    if ($build -ge 22000) {
        $osOk = $true
        $osDetail = "Windows 11(Build $build)"
    } elseif ($build -ge 17763) {
        $osOk = $true
        $osDetail = "Windows 10 1809+(Build $build)"
    } else {
        $osDetail = "Windows Build $build 太老(需要 17763+)"
    }
} elseif ($platform -eq 'macOS') {
    $major = 0
    if ($osVer -match '^(\d+)\.') { $major = [int]$Matches[1] }
    if ($major -ge 13) {
        $osOk = $true
        $osDetail = "macOS $osVer"
    } else {
        $osDetail = "macOS $osVer 太老(需要 13+ / Ventura)"
    }
} else {
    $osOk = $true   # Linux/Unknown 不阻断
    $osDetail = "$platform $osVer(不阻断)"
}

if ($osOk) {
    _Add-Result "✓ OS 版本" 0 $osDetail
} else {
    _Add-Result "✗ OS 版本" 2 $osDetail
}


# [3/5] 磁盘剩余空间
$freeGB = Get-KBAIDiskFreeGB -Path $RootDir
if ($freeGB -ge 10) {
    _Add-Result "✓ 磁盘空间" 0 "$([math]::Round($freeGB, 1)) GB(≥ 10 GB)"
} elseif ($freeGB -gt 0) {
    _Add-Result "✗ 磁盘空间" 2 "$([math]::Round($freeGB, 1)) GB,KB-AI 需要 ≥ 10 GB"
} else {
    _Add-Result "⚠ 磁盘空间" 1 "无法检测(继续)"
}


# [4/5] 内存
$memGB = Get-KBAIMemoryGB
if ($memGB -ge 4) {
    _Add-Result "✓ 内存" 0 "$memGB GB(≥ 4 GB)"
} elseif ($memGB -gt 0) {
    _Add-Result "✗ 内存" 2 "$memGB GB,KB-AI 5 容器需要 ≥ 4 GB"
} else {
    _Add-Result "⚠ 内存" 1 "无法检测(继续)"
}


# [5/5] 平台专属
if ($platform -eq 'macOS') {
    # 5a. SIP 状态(不阻断,仅警告)
    $sip = Test-KBAISIPStatus
    if ($sip.Status -eq 'enabled') {
        _Add-Result "✓ SIP" 0 "enabled(Docker Desktop 推荐)"
    } elseif ($sip.Status -eq 'disabled') {
        _Add-Result "⚠ SIP" 1 "disabled(Docker Desktop 行为可能异常,建议恢复 enabled)"
    } else {
        _Add-Result "⚠ SIP" 1 "状态未知(继续)"
    }
    # 5b. Docker Desktop 安装
    $docker = (& which docker 2>$null) | Out-String
    if ($docker -and $docker.Trim()) {
        _Add-Result "✓ Docker" 0 $docker.Trim()
    } else {
        _Add-Result "✗ Docker" 2 "Docker Desktop 未安装(请 brew install --cask docker)"
    }
} elseif ($platform -eq 'Windows') {
    # S Mode 检测(沿用 precheck.bat 的 EditionID + SKU 联合判断)
    $sku = $null
    $edition = $null
    try {
        $sku = (Get-CimInstance Win32_OperatingSystem).OperatingSystemSKU
        $edition = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').EditionID
    } catch {
        _Add-Result "⚠ S Mode" 1 "无法检测(继续)"
    }
    if ($sku -and $edition) {
        if ($sku -in 1, 2, 3, 4, 27, 28, 100, 101 -and ($edition -match '^Core$|^Cloud$| S$')) {
            _Add-Result "✗ S Mode" 2 "检测到 S Mode,Docker Desktop 不支持"
        } else {
            _Add-Result "✓ S Mode" 0 "不是 S Mode(edition=$edition)"
        }
    }
} else {
    _Add-Result "⚠ 平台" 1 "$platform(不阻断,继续)"
}


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------

if (-not $Quiet) {
    Write-LogHost ""
    Write-LogHost "  ============================================================" -ForegroundColor Cyan
    Write-LogHost "    KB-AI · 客户机预检  v1.7.0  平台=$platform" -ForegroundColor Cyan
    Write-LogHost "  ============================================================" -ForegroundColor Cyan
    Write-LogHost ""
    foreach ($r in $Results) {
        $color = switch ($r.Level) {
            0 { "Green" }
            1 { "Yellow" }
            2 { "Red" }
        }
        $line = "    {0,-12} {1}" -f $r.Display, $r.Detail
        Write-LogHost $line -ForegroundColor $color
    }
    Write-LogHost ""
    Write-LogHost "  ------------------------------------------------------------" -ForegroundColor Gray
    if ($FailCount -gt 0) {
        Write-LogHost "    预检结果: 0 通过 / $FailCount 失败 / $WarnCount 警告" -ForegroundColor Red
        Write-LogHost "    [不通过] 您的电脑目前跑不了 KB-AI" -ForegroundColor Red
        Write-LogHost ""
        Write-LogHost "    建议:" -ForegroundColor Yellow
        Write-LogHost "      1. 截屏记录后查看 logs/ 启动日志" -ForegroundColor Gray
        Write-LogHost "      2. 让发盘人远程协助(ToDesk)或在 BIOS / 系统设置里修复" -ForegroundColor Gray
        Write-LogHost "      3. 如果是 CPU 虚拟化或 S Mode,可能需要懂电脑的人到现场修" -ForegroundColor Gray
    } else {
        Write-LogHost "    预检结果: 全部通过 / $WarnCount 警告" -ForegroundColor Green
        Write-LogHost "    [通过] 您的电脑可以跑 KB-AI" -ForegroundColor Green
    }
    Write-LogHost ""
    Write-LogHost "    [下一步] 双击 start.command / start.bat 启动 KB-AI" -ForegroundColor Gray
    Write-LogHost ""
}

# ----------------------------------------------------------------------
# 退出码
# ----------------------------------------------------------------------

Close-LogFile

if ($FailCount -gt 0) { exit 1 } else { exit 0 }

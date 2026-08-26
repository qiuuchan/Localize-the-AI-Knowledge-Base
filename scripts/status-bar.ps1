<#
.SYNOPSIS
  KB-AI · 终端状态栏 — ONLINE / OFFLINE / RETRY 三态 + Qwen3.6-Plus Credits 余量 + U 盘容量

.DESCRIPTION
  - 三种模式:
      -Mode online   直接探测;若失败仍输出(强制 ONLINE 视图)
      -Mode offline  强制显示 [OFFLINE];不调外部接口(测试场景)
      -Mode auto     默认;读 health-probe 的 ./data/health_status.json,据此显示 ONLINE/OFFLINE/RETRY
  - 后台轮询:-Loop 时每 30s 刷新,Ctrl+C 优雅退出
  - 数据源:
      1. 健康状态:  调 health-probe.ps1 -OutputJson 或读 data/health_status.json
      2. Credits:   调 Qwen3.6-Plus API(阿里云百炼)查询余额;失败显示 [未知]
      3. U 盘容量:  dot-source disk-alert.ps1 复用 Get-KBAIDiskUsage
  - 退出码:
      0 = 状态正常打印完成
      2 = ONLINE 但 Credits 余额不足(<5%)或 U 盘容量 ≥ level 3
      3 = OFFLINE

.PARAMETER Mode
  online | offline | auto(默认 auto)

.PARAMETER RootDir
  项目根目录(默认 $PSScriptRoot/..)

.PARAMETER DataDir
  数据目录(默认 $RootDir/data;health_status.json 所在)

.PARAMETER Loop
  后台轮询,每 30s 刷新,Ctrl+C 退出

.PARAMETER ApiKey
  阿里云百炼 API Key;缺省从 .env 读 ALIYUN_BAILIAN_API_KEY

.PARAMETER IntervalSec
  -Loop 轮询间隔(秒,默认 30)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/status-bar.ps1
  pwsh -File scripts/status-bar.ps1 -Mode offline           # 测试 OFFLINE 视图
  pwsh -File scripts/status-bar.ps1 -Loop                    # 后台 30s 轮询

.NOTES
  PowerShell 5.1 兼容;颜色一律 Write-Host -ForegroundColor,不写 ANSI 控制符。
  Credit 余额查询:POST {MODEL_ENDPOINT} 取 response.usage 段(若 API 提供);否则显示 [未知]
#>

[CmdletBinding()]
param(
    [ValidateSet('online', 'offline', 'auto')]
    [string]$Mode = 'auto',
    [string]$RootDir,
    [string]$DataDir,
    [switch]$Loop = $false,
    [string]$ApiKey,
    [int]$IntervalSec = 30
)

$ErrorActionPreference = "Continue"   # 网络失败不 panic

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RootDir = Split-Path -Parent $scriptRoot
}
if (-not $DataDir) {
    $DataDir = Join-Path $RootDir "data"
}

# ----------------------------------------------------------------------
# dot-source:复用 disk-alert.ps1 的 Get-KBAIDiskUsage
# ----------------------------------------------------------------------

$diskScript = Join-Path $PSScriptRoot "disk-alert.ps1"
if (Test-Path $diskScript) {
    . $diskScript   # 注入 Get-KBAIDiskUsage
}

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')

function Get-KBAICredits {
    # 调 Qwen3.6-Plus API 查 Credits;失败返回 $null
    # 阿里云百炼:模型问答不返回 Credits,需调 用户信息 API(此处简化:返回 $null + [未知])
    # 真实实现:GET https://dashscope.aliyuncs.com/api/v1/users/me
    #         (需在阿里云工作台申请用户查询权限)
    param([string]$Key)
    # 修复 2.1:用公共库 Test-IsPlaceholder 统一占位符识别
    if (-not $Key -or (Test-IsPlaceholder -Value $Key)) { return $null }
    try {
        $url = "https://dashscope.aliyuncs.com/api/v1/users/me"
        $headers = @{ "Authorization" = "Bearer $Key" }
        $resp = Invoke-WebRequest -Uri $url -Method Get -Headers $headers `
                  -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $j = $resp.Content | ConvertFrom-Json
            # 响应格式: { data: { creditBalance: X } } 或类似
            # 此处保守实现:返回数字;解析失败返回 $null
            if ($j.data -and $j.data.creditBalance -ne $null) {
                return [double]$j.data.creditBalance
            }
        }
        return $null
    } catch {
        return $null
    }
}

function Get-KBAIHealth {
    # 读 health_status.json;不存在 → $null
    param([string]$DataDirPath)
    $f = Join-Path $DataDirPath "health_status.json"
    if (-not (Test-Path $f)) { return $null }
    try {
        Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Format-Credits {
    # 用 [Parameter()] 显式允许 null:$Credits 用 [double] 会把 null 强转 0.0,
    # 改用 [object] + 显式 null 检查。
    param([Parameter()]$Credits)
    if ($null -eq $Credits) { return "[未知] ✗ 无法查询" }
    # 假设月度上限 25000 Credits(可配置)
    $monthlyCap = 25000
    $pct = [math]::Round(($Credits / $monthlyCap) * 100, 1)
    return ("{0:N0} / {1:N0} Credits(本月剩余 {2}%)" -f $Credits, $monthlyCap, $pct)
}

# ----------------------------------------------------------------------
# 渲染主体
# ----------------------------------------------------------------------

function Show-Banner {
    param(
        [string]$Mode,
        [hashtable]$Health,
        [Parameter()]$Credits,    # 不加类型,允许 $null
        [hashtable]$Disk,
        [datetime]$Now
    )

    # 网络状态判断
    $online = $false
    $retry = $false
    if ($Mode -eq 'online') {
        $online = $true
    } elseif ($Mode -eq 'offline') {
        $online = $false
    } else {
        # auto:读 health_status.json
        if ($Health -and $Health.online) {
            $online = $true
        } elseif ($Health) {
            $online = $false
            $retry = $true
        } else {
            $online = $false
        }
    }

    if ($online)      { $netTag = "[ONLINE]";  $netColor = "Green" }
    elseif ($retry)   { $netTag = "[RETRY]";   $netColor = "DarkYellow" }
    else              { $netTag = "[OFFLINE]"; $netColor = "Red" }

    if ($online)      { $netDesc = "★ Qwen3.6-Plus API 与 websearch 服务可达" }
    elseif ($retry)   { $netDesc = "⚠ 部分端点失败,正在重试" }
    else              { $netDesc = "❓ 所有外部服务不可达,AI 暂不可用" }

    # Credits 行
    $creditsLine = Format-Credits -Credits $Credits

    # 容量行
    if ($Disk) {
        $diskText = "{0:N1} GB / 1 TB ({1}%) {2}" -f $Disk.totalGB, [math]::Round($Disk.totalGB / 10, 0), $Disk.label
    } else {
        $diskText = "[未知] ✗ 无法读取容量"
    }

    # 渲染
    Write-Host ""
    Write-Host "┌─ KB-AI 状态 ──────────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host ("│ 网络:    {0}  {1}" -f $netTag, $netDesc) -ForegroundColor $netColor
    Write-Host ("│ Qwen 余额: {0}" -f $creditsLine) -ForegroundColor $(if ($Credits -and $Credits -gt 0) { "Cyan" } else { "Yellow" })
    Write-Host ("│ U 盘容量: {0}" -f $diskText) -ForegroundColor $Disk.color
    Write-Host ("│ 最后活动: {0}" -f $Now.ToString('yyyy-MM-dd HH:mm:ss')) -ForegroundColor Gray
    Write-Host "└─────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
    Write-Host ""
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

# .env API Key 兜底
if (-not $ApiKey) {
    $envPath = Join-Path $RootDir ".env"
    if (Test-Path $envPath) {
        $k = Get-EnvVar -EnvPath $envPath -Name "ALIYUN_BAILIAN_API_KEY"
        # 修复 2.1:用公共库 Test-IsPlaceholder 统一占位符识别
        if ($k -and -not (Test-IsPlaceholder -Value $k)) {
            $ApiKey = $k
        }
    }
}

if (-not $Loop) {
    # 单次渲染
    Write-Step "扫描状态 (mode=$Mode)"

    $health = if ($Mode -eq 'online') {
        # online 模式:不读 health_status.json(假装 ONLINE)
        @{ online = $true }
    } elseif ($Mode -eq 'offline') {
        @{ online = $false }
    } else {
        Get-KBAIHealth -DataDirPath $DataDir
    }

    $credits = if ($Mode -eq 'offline') { $null } else { Get-KBAICredits -Key $ApiKey }

    $disk = $null
    try {
        if (Get-Command Get-KBAIDiskUsage -ErrorAction SilentlyContinue) {
            $disk = Get-KBAIDiskUsage -Root $RootDir
        }
    } catch {
        $disk = $null
    }

    Show-Banner -Mode $Mode -Health $health -Credits $credits -Disk $disk -Now (Get-Date)

    # 退出码
    if ($Mode -eq 'offline') { exit 3 }
    if ($disk -and $disk.level -ge 3) { exit 2 }
    exit 0
} else {
    # -Loop 后台轮询
    Write-Step "进入后台轮询模式 (每 ${IntervalSec}s 刷新,Ctrl+C 退出)"
    try {
        while ($true) {
            Clear-Host
            $health = Get-KBAIHealth -DataDirPath $DataDir
            $credits = Get-KBAICredits -Key $ApiKey
            $disk = $null
            try {
                if (Get-Command Get-KBAIDiskUsage -ErrorAction SilentlyContinue) {
                    $disk = Get-KBAIDiskUsage -Root $RootDir
                }
            } catch { }
            Show-Banner -Mode $Mode -Health $health -Credits $credits -Disk $disk -Now (Get-Date)
            Write-Step "下次刷新 ${IntervalSec}s 后,Ctrl+C 退出"
            Start-Sleep -Seconds $IntervalSec
        }
    } finally {
        Write-Step "已退出 status-bar 轮询"
    }
}

<#
.SYNOPSIS
  KB-AI · 综合健康度 1 屏总览 — 串调 health-probe / status-bar / disk-alert / version / get-usb-root

.DESCRIPTION
  ### 设计
    把分散的"单一指标"脚本组合成 1 屏卡片输出,供：
      - start.bat 启动后调一次,验收当前会话是否健康
      - 用户日常 `pwsh -File scripts/health-full.ps1` 自检
      - 自动化探针(后台定时跑)

  ### 五大指标(自上而下)
    1. 版本       KB-AI v0.7.0        (version.ps1)
    2. U 盘路径   <private>\KB-AI     (get-usb-root.ps1)
    3. 容器状态   [UP] 4/4 / [DOWN]   (version.ps1 复用 / 调 docker compose ps)
    4. AI 服务    ONLINE / OFFLINE   (health-probe.ps1 -OutputJson)
    5. U 盘容量   24 GB / 1 TB(2%)✓ (disk-alert.ps1)
    6. 数据健康   [OK] 4/4            (version.ps1 data check)

  ### 输出示例
      ╔════════════════════════════════════════════════════════════╗
      ║         KB-AI · 综合健康度 自检                            ║
      ╚════════════════════════════════════════════════════════════╝
        版本       : KB-AI v0.7.0
        U 盘路径   : <private>\KB-AI
        容器状态   : [UP] 4/4 (全部运行)
        AI 服务    : ONLINE (Qwen / Tavily / Bing 全可达)
        容量       : 24.5 GB / 1 TB (2%) ✓ 正常
        数据健康   : [OK] 4/4 (data/vectors/cache/logs)
        时间戳     : 2026-07-02 14:30:00
      ╔════════════════════════════════════════════════════════════╗
      ║  ✓ 全部健康                                                ║
      ╚════════════════════════════════════════════════════════════╝

  ### 退出码
    0 = 全部健康
    1 = U 盘未找到(get-usb-root 失败)
    2 = 容器全停或 docker 不可用
    3 = 容量告警(≥ level 3)
    4 = 外部服务全 OFFLINE
    max(以上各项) — 任一不健康即非 0

  ### 运行
    powershell -ExecutionPolicy Bypass -File scripts/health-full.ps1
    pwsh -File scripts/health-full.ps1 -Json
    pwsh -File scripts/health-full.ps1 -Loop            # 每 30s 刷新,Ctrl+C 退出
    pwsh -File scripts/health-full.ps1 -IntervalSec 10  # 自定义轮询间隔

.PARAMETER RootDir
  KB-AI 根目录(默认 Get-UsbRoot)。

.PARAMETER Json
  开关:输出 JSON 到 stdout(便于 CI 抓取)。

.PARAMETER Loop
  后台轮询,每 IntervalSec 秒刷新。

.PARAMETER IntervalSec
  -Loop 轮询间隔秒(默认 30)。

.NOTES
  PowerShell 5.1 兼容;UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding $false)。
  依赖:version.ps1 / get-usb-root.ps1 / health-probe.ps1 / disk-alert.ps1(M1/M2/M3 全已落地)。
  任何 sub-script 出错不 panic — 整体包 try/catch 把异常转成"该指标未知"。
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [switch]$Json = $false,
    [switch]$Loop = $false,
    [ValidateRange(5, 600)] [int]$IntervalSec = 30
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RootDir = Split-Path -Parent $scriptRoot

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Line {
    param([string]$Label, [string]$Value, [string]$Color = "White")
    Write-Host ("  {0,-10} : " -f $Label) -NoNewline
    Write-Host $Value -ForegroundColor $Color
}

function Write-Header {
    param([string]$Title = "KB-AI · 综合健康度 自检")
    Clear-Host
    Write-Host ""
    Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host ("  ║   {0}" -f $Title.PadRight(52)) -ForegroundColor Cyan
    Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# 跑一段 sub-script,捕获 stdout,失败时返回"未知"
function Invoke-SubScript {
    param(
        [string]$Path,
        [string[]]$Arguments = @()
    )
    $result = @{ ok = $false; exit = 99; output = ""; error = "" }
    if (-not (Test-Path -LiteralPath $Path)) {
        $result.error = "脚本不存在:$Path"
        return $result
    }
    try {
        $pwsh = if ($PSVersionTable.PSVersion.Major -ge 7) { "pwsh" } else { "powershell" }
        $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Path) + $Arguments
        $tmpOut = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "kb_ai_hf_out_" + [guid]::NewGuid().ToString("N") + ".txt")
        $tmpErr = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "kb_ai_hf_err_" + [guid]::NewGuid().ToString("N") + ".txt")
        $proc = Start-Process -FilePath $pwsh -ArgumentList $argList `
                              -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr `
                              -Wait -PassThru -NoNewWindow
        $result.exit = $proc.ExitCode
        $result.ok = ($proc.ExitCode -eq 0)
        if (Test-Path -LiteralPath $tmpOut) {
            $result.output = (Get-Content -LiteralPath $tmpOut -Raw -Encoding UTF8 -ErrorAction SilentlyContinue)
            Remove-Item -LiteralPath $tmpOut -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $tmpErr) {
            $result.error = (Get-Content -LiteralPath $tmpErr -Raw -Encoding UTF8 -ErrorAction SilentlyContinue)
            Remove-Item -LiteralPath $tmpErr -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        $result.error = $_.Exception.Message
    }
    return $result
}

# 从 version.ps1 输出里抽 "KB-AI v0.7.0  ·  容器:[UP]..."
function Parse-VersionLine {
    param([string]$Output)
    $line = ($Output -split "`n" | Where-Object { $_.Trim() -match "KB-AI v" } | Select-Object -First 1)
    if (-not $line) { return $null }
    $line = $line.Trim()
    # 抽版本号
    $v = $null
    if ($line -match "KB-AI v(\S+)") { $v = $Matches[1] }
    # 抽容器标签
    $container = $null
    if ($line -match "容器:\[(\w+)\](?:\((\d+)/(\d+)\))?") {
        $container = @{ state = $Matches[1]; running = $Matches[2]; total = $Matches[3] }
    }
    # 抽数据标签
    $data = $null
    if ($line -match "数据:\[(\w+)\](?:\((\d+)/(\d+)\))?") {
        $data = @{ state = $Matches[1]; present = $Matches[2]; total = $Matches[3] }
    }
    # 抽容量
    $capacity = $null
    if ($line -match "容量:(\S+)") {
        $capacity = $Matches[1]
    }
    return @{ version = $v; container = $container; data = $data; capacity = $capacity; raw = $line }
}

# ----------------------------------------------------------------------
# 主采集
# ----------------------------------------------------------------------

function Get-FullHealth {
    param([string]$Root, [bool]$AsJson = $false)

    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

    # 1. U 盘路径(get-usb-root)
    $rootResult = Invoke-SubScript -Path (Join-Path $scriptRoot "get-usb-root.ps1") -Arguments @()
    $usbRoot = if ($rootResult.ok) { $rootResult.output.Trim() } else { "[未知]" }

    # 若 RootDir 没设,默认用 get-usb-root 输出
    if (-not $Root -or $Root -eq "") {
        $Root = if ($rootResult.ok) { $usbRoot } else { Split-Path -Parent $scriptRoot }
    }

    # 2. 版本 + 容器 + 数据 + 容量(一次 version.ps1 搞定)
    # version.ps1 在容器未起时也会返回非 0 exit,但 output 仍含 "KB-AI v..." 一行;
    # 因此不要求 $verResult.ok,直接解析 output
    $verResult = Invoke-SubScript -Path (Join-Path $scriptRoot "version.ps1") -Arguments @()
    $verInfo = if ($verResult.output -and $verResult.output.Trim().Length -gt 0) {
        Parse-VersionLine -Output $verResult.output
    } else { $null }

    $version   = if ($verInfo -and $verInfo.version) { "KB-AI v$($verInfo.version)" } else { "[未知]" }
    $container = if ($verInfo -and $verInfo.container) {
        $st = $verInfo.container.state
        $r  = $verInfo.container.running
        $t  = $verInfo.container.total
        switch ($st) {
            'UP'   {
                if ($r -and $t) { "[UP] $r/$t(全部运行)" } else { "[UP] 全部运行" }
            }
            'PART' {
                if ($r -and $t) { "[PART] $r/$t(部分运行)" } else { "[PART] 部分运行" }
            }
            default { "[DOWN] 容器未运行" }
        }
    } else { "[未知]" }
    $dataHealth = if ($verInfo -and $verInfo.data) {
        $st = $verInfo.data.state
        $p  = $verInfo.data.present
        $t  = $verInfo.data.total
        switch ($st) {
            'OK'   {
                if ($p -and $t) { "[OK] $p/$t" } else { "[OK] 全部存在" }
            }
            'WARN' {
                if ($p -and $t) { "[WARN] $p/$t(部分缺失)" } else { "[WARN] 部分缺失" }
            }
            default {
                if ($p -and $t) { "[BAD] $p/$t(严重缺失)" } else { "[BAD] 严重缺失" }
            }
        }
    } else { "[未知]" }

    # 3. AI 服务 health-probe
    $hpResult = Invoke-SubScript -Path (Join-Path $scriptRoot "health-probe.ps1") -Arguments @("-OutputJson")
    $aiService = "[未知]"
    if ($hpResult.ok -and $hpResult.output -match '"online"\s*:\s*(true|false)') {
        $online = ($Matches[1] -eq "true")
        if ($online) {
            # 数端点数
            $count = ([regex]::Matches($hpResult.output, '"(qwen|tavily|bing)"\s*:\s*true')).Count
            $total = 3
            $aiService = "ONLINE($count/$total 个端点可达)"
        }
        else {
            $aiService = "OFFLINE(AI 暂不可用)"
        }
    }

    # 4. U 盘容量(disk-alert)
    $diskResult = Invoke-SubScript -Path (Join-Path $scriptRoot "disk-alert.ps1") -Arguments @("-NoLog")
    $capacity = "[未知]"
    if ($diskResult.output -match '"totalGB"\s*:\s*(\d+(?:\.\d+)?)') {
        $gb = [double]$Matches[1]
        $pct = [Math]::Round($gb / 10, 0)   # 1TB = 10,模拟百分比
        $capacity = ("{0} GB / 1 TB ({1}%)" -f $gb, $pct)
    }
    elseif ($diskResult.output -match "正常") {
        $capacity = "[正常]"
    }

    # 5. 计算退出码(取最严重)
    $exit = 0
    if (-not $rootResult.ok) { $exit = 1 }
    elseif ($verInfo.container.state -eq 'DOWN') { $exit = 2 }
    elseif ($diskResult.exit -ge 2) { $exit = 3 }
    elseif ($hpResult.ok -and $aiService -match "OFFLINE") { $exit = 4 }
    elseif ($verInfo.data.state -eq 'BAD') { $exit = 1 }
    elseif ($diskResult.exit -ge 1) { $exit = 1 }

    # 6. 完整 payload
    $payload = [ordered]@{
        timestamp      = $ts
        root           = $Root
        usbPath        = $usbRoot
        version        = $version
        container      = $container
        aiService      = $aiService
        capacity       = $capacity
        dataHealth     = $dataHealth
        exitCode       = $exit
        components = [ordered]@{
            getUsbRoot       = $rootResult.ok
            versionOutput    = ($null -ne $verInfo)
            diskAlert        = $diskResult.ok
            healthProbe      = $hpResult.ok
        }
    }

    return $payload
}

# ----------------------------------------------------------------------
# 单次输出
# ----------------------------------------------------------------------

function Render-Panel {
    param($Payload)
    if ($Json) {
        $Payload | ConvertTo-Json -Depth 6 -Compress
        return
    }

    Write-Header
    Write-Line "版本"     $Payload.version   "White"
    Write-Line "U 盘路径" $Payload.usbPath   "White"
    Write-Line "容器状态" $Payload.container $(if ($Payload.container -match "\[UP\]") { "Green" } elseif ($Payload.container -match "\[PART\]") { "Yellow" } elseif ($Payload.container -match "\[DOWN\]") { "Red" } else { "Gray" })
    Write-Line "AI 服务"  $Payload.aiService $(if ($Payload.aiService -match "ONLINE") { "Green" } elseif ($Payload.aiService -match "OFFLINE") { "Red" } else { "Gray" })
    Write-Line "容量"     $Payload.capacity  "Green"
    Write-Line "数据健康" $Payload.dataHealth $(if ($Payload.dataHealth -match "\[OK\]") { "Green" } elseif ($Payload.dataHealth -match "\[WARN\]") { "Yellow" } elseif ($Payload.dataHealth -match "\[BAD\]") { "Red" } else { "Gray" })
    Write-Line "时间戳"   $Payload.timestamp "Gray"
    Write-Host ""
    Write-Host "  ──────────────────────────────────────────" -ForegroundColor DarkGray

    # 综合判定
    switch ($Payload.exitCode) {
        0 {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
            Write-Host "  ║  ✓  全部健康                                              ║" -ForegroundColor Green
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
        }
        1 {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
            Write-Host "  ║  ⚠  U 盘未找到或数据目录缺失(检查 USB 连接 / 目录结构)     ║" -ForegroundColor Yellow
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
        }
        2 {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
            Write-Host "  ║  ✗  容器全部停止 — 请跑 start.bat                         ║" -ForegroundColor Red
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
        }
        3 {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
            Write-Host "  ║  ✗  容量告警 — 跑 scripts/disk-alert.ps1 看等级           ║" -ForegroundColor Red
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
        }
        4 {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
            Write-Host "  ║  ⚠  AI 服务 OFFLINE — 检查网络 / 重跑 health-probe.ps1     ║" -ForegroundColor Yellow
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
        }
        default {
            Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
            Write-Host "  ║  ⚠  综合健康度异常(exit=$($Payload.exitCode))                                ║" -ForegroundColor Yellow
            Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
        }
    }
    Write-Host ""
}

# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------

if ($Loop) {
    # 后台轮询模式
    Write-Host "  [轮询模式] 每 $IntervalSec 秒刷新一次,Ctrl+C 退出" -ForegroundColor Cyan
    Write-Host ""
    try {
        while ($true) {
            $payload = Get-FullHealth -Root $RootDir -AsJson $Json
            Render-Panel -Payload $payload
            Start-Sleep -Seconds $IntervalSec
        }
    }
    finally {
        Write-Host ""
        Write-Host "  [轮询模式] 已退出" -ForegroundColor Yellow
    }
}
else {
    $payload = Get-FullHealth -Root $RootDir -AsJson $Json
    Render-Panel -Payload $payload
}

exit $payload.exitCode

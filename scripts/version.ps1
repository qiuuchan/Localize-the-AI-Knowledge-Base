<#
.SYNOPSIS
  KB-AI · 版本 + 健康度 1 行总览

.DESCRIPTION
  ### 输出示例
      KB-AI v0.7.0  ·  容器:[UP]  ·  数据:[OK]  ·  容量:412.3GB/1TB(41%)  ✓ 正常

  ### 字段解析
    - 版本号:
        1. 从 <root>/.kb-ai-root/version 读(若有)
        2. 回退 <root>/version
        3. 默认 "0.7.0"(对齐 PRD v0.7)
    - 容器状态:
        - 调 docker compose ps --format json,统计 "running" 数 vs 总数
        - [UP]   = 全部运行
        - [PART] = 部分运行
        - [DOWN] = 无容器 / docker 不可用
    - 数据健康:
        - 扫描 <root>/{data,vectors,cache,logs} 4 个目录存在性
        - [OK]  = 4 个全在
        - [WARN]= 缺失 1-2 个
        - [BAD] = 缺失 ≥ 3 个
    - 容量:复用 disk-alert.ps1 的 Get-KBAIDiskUsage
        - dot-source disk-alert.ps1 取函数,不重复实现

  ### 退出码
    0 = 全部健康
    1 = 数据目录缺失
    2 = 容器全停
    3 = 容量告警(≥ level 3)

.PARAMETER RootDir
  可选:KB-AI 根目录(默认 Get-UsbRoot)

.PARAMETER Json
  开关:输出 JSON 到 stdout(便于 CI 抓取)

.OUTPUTS
  None(Write-Host 到 stdout)

.NOTES
  PowerShell 5.1 兼容;UTF-8 无 BOM。
  依赖:disk-alert.ps1(M3a 已落地,含 Get-KBAIDiskUsage)
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [switch]$Json = $false
)

$ErrorActionPreference = "Continue"

# ----------------------------------------------------------------------
# 路径解析(用 Get-UsbRoot 跨平台定位)
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'get-usb-root.ps1')
if (-not $RootDir) { $RootDir = Get-UsbRoot }

# ----------------------------------------------------------------------
# dot-source disk-alert 取 Get-KBAIDiskUsage
# ----------------------------------------------------------------------

$diskScript = Join-Path $PSScriptRoot 'disk-alert.ps1'
if (Test-Path -LiteralPath $diskScript) {
    . $diskScript   # 注入 Get-KBAIDiskUsage
}

# ----------------------------------------------------------------------
# 版本号解析
# ----------------------------------------------------------------------

function Read-VersionString {
    # 优先级:.kb-ai-root/version > root/version > 默认 0.7.0
    param([string]$Root)
    $candidates = @(
        (Join-Path $Root '.kb-ai-root/version'),
        (Join-Path $Root 'version'),
        (Join-Path $Root '.version')
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) {
            try {
                $v = (Get-Content -LiteralPath $c -Raw -Encoding UTF8).Trim()
                if ($v) { return $v }
            } catch { }
        }
    }
    return "0.7.0"
}

# ----------------------------------------------------------------------
# 容器状态(docker compose ps 解析)
# ----------------------------------------------------------------------

function Get-ContainerStatus {
    <#
    .SYNOPSIS
      探测 docker compose 容器状态。
    .OUTPUTS
      hashtable { state: 'UP'|'PART'|'DOWN', running: int, total: int, message: string }
    #>
    # 检查 docker 命令是否存在
    $dockerCmd = $null
    try { $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue } catch { }
    if (-not $dockerCmd) {
        return @{ state = 'DOWN'; running = 0; total = 0; message = 'docker 命令不可用' }
    }

    # 优先用 docker compose ps(JSON);失败再降级到 docker ps
    $composeFile = Join-Path $RootDir 'docker-compose.yml'
    $jsonOut = ""
    try {
        if (Test-Path -LiteralPath $composeFile) {
            $jsonOut = & docker compose -f $composeFile ps --format json 2>$null
        }
        if (-not $jsonOut) {
            $jsonOut = & docker compose ps --format json 2>$null
        }
    } catch { }

    if (-not $jsonOut) {
        return @{ state = 'DOWN'; running = 0; total = 0; message = 'docker compose 无输出' }
    }

    # 多行 JSON,逐行解析
    $running = 0
    $total = 0
    $lines = $jsonOut -split "`n"
    foreach ($ln in $lines) {
        $ln = $ln.Trim()
        if (-not $ln) { continue }
        try {
            $obj = $ln | ConvertFrom-Json -ErrorAction Stop
            $total++
            $st = "$($obj.State)"
            if ($st -match 'running|Running') { $running++ }
        } catch {
            # 解析失败,跳过这一行
        }
    }

    if ($total -eq 0) {
        return @{ state = 'DOWN'; running = 0; total = 0; message = '无容器' }
    }
    elseif ($running -eq $total) {
        return @{ state = 'UP'; running = $running; total = $total; message = "$running/$total 运行中" }
    }
    elseif ($running -gt 0) {
        return @{ state = 'PART'; running = $running; total = $total; message = "$running/$total 运行" }
    }
    else {
        return @{ state = 'DOWN'; running = 0; total = $total; message = '全部停止' }
    }
}

# ----------------------------------------------------------------------
# 数据健康度
# ----------------------------------------------------------------------

function Get-DataHealth {
    <#
    .SYNOPSIS
      检查 data/vectors/cache/logs 目录存在性。
    .OUTPUTS
      hashtable { state: 'OK'|'WARN'|'BAD', present: int, total: int, missing: string[] }
    #>
    $required = @('data', 'vectors', 'cache', 'logs')
    $present = 0
    $missing = @()
    foreach ($d in $required) {
        $p = Join-Path $RootDir $d
        if (Test-Path -LiteralPath $p) { $present++ } else { $missing += $d }
    }
    $total = $required.Count
    if ($present -eq $total) {
        $state = 'OK'
    } elseif ($present -ge ($total - 2)) {
        $state = 'WARN'
    } else {
        $state = 'BAD'
    }
    return @{ state = $state; present = $present; total = $total; missing = $missing }
}

# ----------------------------------------------------------------------
# 容量
# ----------------------------------------------------------------------

function Get-CapacityLine {
    if (-not (Get-Command Get-KBAIDiskUsage -ErrorAction SilentlyContinue)) {
        return @{ text = '[未知]'; label = '✗ 不可读'; level = 0; color = 'DarkGray' }
    }
    try {
        $u = Get-KBAIDiskUsage -Root $RootDir -Paths @('data', 'vectors', 'cache', 'logs', 'tmp')
        $pct = [math]::Round($u.totalGB / 10, 0)   # 1TB 估算 → 百分比
        if ($pct -lt 0) { $pct = 0 }
        if ($pct -gt 100) { $pct = 100 }
        $text = ("{0}GB/1TB({1}%)" -f $u.totalGB, $pct)
        return @{ text = $text; label = $u.label; level = $u.level; color = $u.color }
    } catch {
        return @{ text = '[未知]'; label = '✗ 读取失败'; level = 0; color = 'DarkGray' }
    }
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

$version   = Read-VersionString -Root $RootDir
$container = Get-ContainerStatus
$data      = Get-DataHealth
$capacity  = Get-CapacityLine

# 容器标签 + 颜色
switch ($container.state) {
    'UP'   { $containerTag = "[UP]($($container.running)/$($container.total))"; $containerColor = 'Green' }
    'PART' { $containerTag = "[PART]($($container.running)/$($container.total))"; $containerColor = 'DarkYellow' }
    default{ $containerTag = "[DOWN]"; $containerColor = 'Red' }
}

# 数据标签 + 颜色
switch ($data.state) {
    'OK'   { $dataTag = "[OK]($($data.present)/$($data.total))";  $dataColor = 'Green' }
    'WARN' { $dataTag = "[WARN]($($data.present)/$($data.total))"; $dataColor = 'Yellow' }
    default{ $dataTag = "[BAD]($($data.present)/$($data.total))";  $dataColor = 'Red' }
}

# JSON 输出模式
if ($Json) {
    $payload = [ordered]@{
        version    = $version
        container  = $container
        data       = $data
        capacity   = $capacity
        scannedAt  = (Get-Date).ToString('o')
        rootDir    = $RootDir
    }
    $payload | ConvertTo-Json -Depth 4 -Compress
    exit 0
}

# 人类可读 1 行
$line = ("  KB-AI v{0}  ·  容器:{1}  ·  数据:{2}  ·  容量:{3}  {4}" -f `
         $version, $containerTag, $dataTag, $capacity.text, $capacity.label)

Write-Host ""
Write-Host $line -ForegroundColor $capacity.color
Write-Host ""

# 退出码
$exitCode = 0
if ($data.state -eq 'BAD') { $exitCode = 1 }
if ($container.state -eq 'DOWN') { $exitCode = 2 }
if ($capacity.level -ge 3) { $exitCode = 3 }
exit $exitCode
<#
.SYNOPSIS
  KB-AI · U 盘容量告警 — 5 级阈值监控,超限写 data/disk-alerts.log

.DESCRIPTION
  - 实时计算 ./data/ + ./vectors/ + ./cache/ + ./logs/ + ./tmp/ 共 5 个挂载点总占用
  - 5 级阈值(GB;v0.8.6 按实测 466GB 盘重定标,FMEA F10):
      level 0: <  300 GB   正常,绿色 ✓
      level 1: 300-350 GB  空间将满,建议清理(黄色 ⚠)
      level 2: 350-400 GB  禁止新增文档(深黄 ⚠⚠)
      level 3: 400-430 GB  全局告警(橙色 ✗)
      level 4: >= 430 GB   紧急,系统压力(红色 ✗✗)
  - 退出码:
      0 = level 0(正常)
      1 = level 1-2(预警)
      2 = level 3-4(告警 + 紧急)
  - 告警额外写入 $DataDir/disk-alerts.log(append 一行:timestamp, level, totalGB, message)
  - 暴露函数 Get-KBAIDiskUsage 给 status-bar.ps1 dot-source 调用,避免重复实现

.PARAMETER RootDir
  可选:项目根目录(默认向上取一级,即脚本所在目录的父目录)

.PARAMETER DataDir
  可选:数据目录(用于写告警日志,默认 $RootDir/data)

.PARAMETER OutputJson
  开关:stdout 输出 JSON(hashtable),便于 status-bar.ps1 调用

.PARAMETER NoLog
  开关:不写 disk-alerts.log(测试场景)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/disk-alert.ps1
  pwsh -File scripts/disk-alert.ps1 -OutputJson
  pwsh -File scripts/disk-alert.ps1 -RootDir '<private>\KB-AI'

.NOTES
  PowerShell 5.1 兼容(Get-ChildItem -Force 在 5.1 已存在)
  UTF-8 无 BOM(.NET [System.IO.File]::WriteAllText + UTF8Encoding($false))
  依赖:无外部依赖(Get-ChildItem 内置)
  dot-source 入口:
    . (Join-Path $PSScriptRoot 'disk-alert.ps1')   # 仅加载 Get-KBAIDiskUsage 函数
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [string]$DataDir,
    [switch]$OutputJson = $false,
    [switch]$NoLog = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析(相对 / 缺省)
# ----------------------------------------------------------------------

if (-not $RootDir) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RootDir = Split-Path -Parent $scriptRoot
}
if (-not $DataDir) {
    $DataDir = Join-Path $RootDir "data"
}

# ----------------------------------------------------------------------
# 阈值表
# ----------------------------------------------------------------------

# v0.8.6(FMEA F10):实测本 U 盘总容量 466GB,旧阈值(首档 500GB)高于物理容量,
# 磁盘写满前任何一级告警都不会触发;按 466GB 重定标(监控对象为 KB-AI 5 个数据目录)。
$Levels = @(
    @{ Level = 0; MaxGB = 300;  Label = "✓ 正常";           Message = "空间充足,可正常运营";                   Color = "Green"  },
    @{ Level = 1; MaxGB = 350;  Label = "⚠ 空间将满";       Message = "建议立即清理旧文档和临时文件";           Color = "Yellow" },
    @{ Level = 2; MaxGB = 400;  Label = "⚠⚠ 禁止新增文档";  Message = "禁止新增文档,清理后才能继续入库";       Color = "DarkYellow" },
    @{ Level = 3; MaxGB = 430;  Label = "✗ 全局告警";        Message = "U 盘容量危险,系统接近不可用";            Color = "DarkRed" },
    @{ Level = 4; MaxGB = 9999; Label = "✗✗ 紧急";          Message = "系统压力极高,Docker 可能崩溃,立即处理"; Color = "Red"    }
)

$MonitorDirs = @('data', 'vectors', 'cache', 'logs', 'tmp')

# v0.8.4 SQLite 单独监控:db.sqlite > 500MB 时黄色告警,> 1GB 时红色告警
# 原因:WAL 模式下 SQLite 长期运行膨胀是个人 RAG 头号慢性病,嵌入缓存合并写放大
$SqliteWarnMB = 500
$SqliteCritMB = 1024

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }

<#
.SYNOPSIS
  扫描 5 个挂载目录,返回 { totalBytes, totalGB, level, label, message, byDir } 哈希表
.PARAMETER Paths
  子目录名数组,相对 $RootDir(默认 data/vectors/cache/logs/tmp)
#>
function Get-KBAIDiskUsage {
    [CmdletBinding()]
    param(
        [string]$Root,
        [string[]]$Paths = @('data', 'vectors', 'cache', 'logs', 'tmp')
    )
    if (-not $Root) { $Root = $RootDir }   # 闭包:采用上层默认值

    $totalBytes = 0L
    $byDir = [ordered]@{}

    foreach ($p in $Paths) {
        $full = Join-Path $Root $p
        $bytes = 0L
        if (Test-Path $full) {
            try {
                $bytes = (Get-ChildItem -Path $full -Recurse -File -Force -ErrorAction SilentlyContinue |
                          Measure-Object -Property Length -Sum).Sum
                if (-not $bytes) { $bytes = 0L }
            } catch {
                $bytes = 0L
            }
        }
        $byDir[$p] = [math]::Round($bytes / 1GB, 2)
        $totalBytes += $bytes
    }

    $totalGB = [math]::Round($totalBytes / 1GB, 1)

    # level 判定(顺序扫描,每档 MaxGB 是该档上限 → 下一档下限)
    $level = 4
    $label = ""
    $message = ""
    foreach ($lv in $Levels) {
        if ($totalGB -lt $lv.MaxGB) {
            $level = $lv.Level
            $label = $lv.Label
            $message = $lv.Message
            break
        }
    }

    return [ordered]@{
        totalBytes = $totalBytes
        totalGB    = $totalGB
        level      = $level
        label      = $label
        message    = $message
        color      = ($Levels[$level]).Color
        byDir      = $byDir
        scannedAt  = (Get-Date).ToString("o")
    }
}

<#
.SYNOPSIS
  v0.8.4 新增:扫描 db.sqlite 大小,返回 { bytes, mb, level, message }
  阈值:$SqliteWarnMB (500MB 黄) / $SqliteCritMB (1024MB 红)
  调用: Get-KBAISqliteSize -Root <project_root>
  注:数据目录固定为 <Root>/data,匹配 docker-compose / compose 配置
#>
function Get-KBAISqliteSize {
    [CmdletBinding()]
    param(
        [string]$Root
    )
    if (-not $Root) { $Root = $RootDir }
    $dbPath = Join-Path $Root "data/db.sqlite"
    $result = [ordered]@{
        bytes   = 0L
        mb      = 0.0
        level   = 0
        label   = "OK"
        message = ""
        path    = $dbPath
    }
    if (-not (Test-Path $dbPath)) {
        $result.label = "N/A"
        $result.message = "db.sqlite 不存在(尚未启动过)"
        return $result
    }
    try {
        $bytes = (Get-ChildItem -Path $dbPath -File -Force -ErrorAction SilentlyContinue |
                  Measure-Object -Property Length -Sum).Sum
        if (-not $bytes) { $bytes = 0L }
    } catch {
        $bytes = 0L
    }
    $mb = [math]::Round($bytes / 1MB, 1)
    $result.bytes = $bytes
    $result.mb = $mb
    if ($mb -ge $SqliteCritMB) {
        $result.level = 2
        $result.label = "✗ 严重"
        $result.message = "db.sqlite 超过 $SqliteCritMB MB,SQLite 性能将显著下降,建议 vacuum + 重建 embedding-cache"
    } elseif ($mb -ge $SqliteWarnMB) {
        $result.level = 1
        $result.label = "⚠ 偏大"
        $result.message = "db.sqlite 超过 $SqliteWarnMB MB,可能是 embedding-cache 累积,运行 setup.ps1 -TrimCache 清理"
    } else {
        $result.level = 0
        $result.label = "OK"
        $result.message = "db.sqlite 大小正常"
    }
    return $result
}

# 注:.ps1 文件 dot-source 时所有 function 自动可见,无需 Export-ModuleMember
#     (Export-ModuleMember 仅在 .psm1 模块文件里生效)

# ----------------------------------------------------------------------
# 主流程(只在本脚本作为入口时执行;被 dot-source 时跳过,只暴露函数)
# ----------------------------------------------------------------------

# $MyInvocation.InvocationName:
#   - 直接执行:返回脚本路径('D:\...\disk-alert.ps1')
#   - dot-source:返回 '.'(点)
#   - iex/icm:   返回 'iex' / 'icm'
# 只在直接执行时跑主流程。
$isMain = ($MyInvocation.InvocationName -ne '.')
if (-not $isMain) {
    return
}

Write-Step "扫描 $RootDir 子目录: $($MonitorDirs -join ', ')"
$usage = Get-KBAIDiskUsage -Root $RootDir -Paths $MonitorDirs
$sqlite = Get-KBAISqliteSize -Root $RootDir

# ----------------------------------------------------------------------
# 写告警日志(append)
# ----------------------------------------------------------------------

if (-not $NoLog) {
    if (-not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    }
    $logFile = Join-Path $DataDir "disk-alerts.log"
    $logLine = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), level $($usage.level), totalGB=$($usage.totalGB) GB, ""$($usage.label) — $($usage.message)"""
    try {
        Add-Content -Path $logFile -Value $logLine -Encoding UTF8 -ErrorAction Stop
    } catch {
        Write-Warn "写 $logFile 失败: $($_.Exception.Message)"
    }
}

# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------

if ($OutputJson) {
    $usage | ConvertTo-Json -Depth 4 -Compress
    exit 0
}

# 人类可读 banner
Write-Host ""
Write-Host "  KB-AI · 容量告警" -ForegroundColor Cyan
Write-Host "  $($usage.scannedAt)" -ForegroundColor Gray
Write-Host "  ------------------------------------------------------------" -ForegroundColor Gray
Write-Host ""
foreach ($p in $MonitorDirs) {
    $g = $usage.byDir[$p]
    Write-Host ("    {0,-10} {1,7} GB" -f "$p/", "$g") -ForegroundColor Gray
}
Write-Host ""
Write-Host ("    {0,-10} {1,7} GB" -f "TOTAL", "$($usage.totalGB)") -ForegroundColor White
Write-Host ""
Write-Host ("  级别: [{0}] level {1} — {2}" -f $usage.label, $usage.level, $usage.message) -ForegroundColor $usage.color
Write-Host ""
# v0.8.6(FMEA F10):修复 v0.8.4 引入的解析错误 —— switch 语句不能直接作为
# -ForegroundColor 的参数表达式(PS 5.1 解析失败,整个脚本无法运行),改为预计算变量。
$sqliteColor = "Gray"
if ($sqlite.level -eq 2) { $sqliteColor = "Red" }
elseif ($sqlite.level -eq 1) { $sqliteColor = "Yellow" }
Write-Host ("  SQLite: [{0}] {1} MB — {2}" -f $sqlite.label, $sqlite.mb, $sqlite.message) -ForegroundColor $sqliteColor
Write-Host ""

# 退出码(level 0 = 0;level 1-2 = 1;level 3-4 = 2)
if ($usage.level -ge 3) { exit 2 }
elseif ($usage.level -ge 1) { exit 1 }
else { exit 0 }

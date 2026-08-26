<#
.SYNOPSIS
  KB-AI · 月度配额告警 rollup (v1.3.0)

.DESCRIPTION
  从 data/cost_log.jsonl 累加当日/当月 LLM 调用 token,
  按单价表折算人民币,比对 .env 中 COST_ALERT_THRESHOLDS (可选),
  写入 data/health_status.json 的 cost_alert 字段。

  月度 = UTC 自然月(每月 1 日 00:00:00 UTC 起算)。
  回溯范围:本年初起全量。

.PARAMETER Month
  显式指定要 rollup 的月份 (YYYY-MM);默认 = 当前 UTC 月。

.PARAMETER DryRun
  只打印,不写 health_status.json。

.EXAMPLE
  pwsh -File scripts/cost-alert.ps1
  pwsh -File scripts/cost-alert.ps1 -Month "2026-07"
  pwsh -File scripts/cost-alert.ps1 -DryRun

.NOTES
  PowerShell 5.1 兼容。
  退出码:0 成功;1 累加失败但继续(level=0);2 文件不存在(level=0 不写)。
#>

[CmdletBinding()]
param(
    [string]$Month = "",
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Continue"

# v1.3.1: dot-source cost_log 轮转 + UTC 规范化库
. (Join-Path $PSScriptRoot 'lib/CostLog-Rotate.ps1')

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = Split-Path -Parent $scriptRoot
$dataDir = Join-Path $root 'data'
$logPath = Join-Path $dataDir 'cost_log.jsonl'
$healthPath = Join-Path $dataDir 'health_status.json'

# 单价表现归 scripts/lib/CostLog-Rotate.ps1:Get-MonthlyCostFromAllSources 内;
# 此处不重复定义(单一真相源)。

# 阈值默认值
$defaultWarn  = 500.0
$defaultHigh  = 1000.0
$defaultBlock = 1500.0

# 读 .env 中 COST_ALERT_THRESHOLDS(可选;格式: "warn:500,high:1000,block:1500")
$thresholds = @{ warn = $defaultWarn; high = $defaultHigh; block = $defaultBlock }
$envPath = Join-Path $root '.env'
if (Test-Path $envPath) {
    foreach ($line in (Get-Content $envPath)) {
        if ($line -match '^COST_ALERT_THRESHOLDS\s*=\s*(.+)$') {
            $raw = $Matches[1].Trim()
            foreach ($pair in ($raw -split ',')) {
                if ($pair -match '^(warn|high|block):(\d+(?:\.\d+)?)$') {
                    $thresholds[$Matches[1]] = [double]$Matches[2]
                }
            }
        }
    }
}

# 月份
if (-not $Month) {
    $Month = (Get-Date).ToUniversalTime().ToString("yyyy-MM")
}
$yearMonth = $Month
Write-Host "[cost-alert] Rollup month: $yearMonth" -ForegroundColor Cyan
Write-Host "[cost-alert] Thresholds: warn=$($thresholds.warn), high=$($thresholds.high), block=$($thresholds.block)" -ForegroundColor Cyan

# v1.3.1: 轮转超 50MB 的 cost_log.jsonl(失败也不抛)
Rotate-CostLog -Path $logPath

# v1.3.1: 累加当前 + 同月所有 .gz 归档
if (-not (Test-Path $logPath)) {
    Write-Host "[cost-alert] [WARN] $logPath 不存在;写入 level=0" -ForegroundColor Yellow
    $agg = @{
        today_yuan = 0.0; month_yuan = 0.0
        today_count = 0; month_count = 0
        input_tokens = 0; output_tokens = 0
        sources = @()
    }
} else {
    $agg = Get-MonthlyCostFromAllSources -DataDir $dataDir -YearMonth $yearMonth
    $todayDate = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-dd")
    Write-Host "[cost-alert] Today ($todayDate): ¥$([math]::Round($agg.today_yuan, 2)) / $($agg.today_count) calls" -ForegroundColor Green
    Write-Host "[cost-alert] Month ($yearMonth): ¥$([math]::Round($agg.month_yuan, 2)) / $($agg.month_count) calls" -ForegroundColor Green
    if ($agg.sources.Count -gt 1) {
        Write-Host "[cost-alert] Sources ($($agg.sources.Count) files): $($agg.sources -join ', ')" -ForegroundColor Cyan
    }
}

$todayYuan = $agg.today_yuan
$monthYuan = $agg.month_yuan

# 等级判定
$level = 0
if ($monthYuan -ge $thresholds.warn)  { $level = 1 }
if ($monthYuan -ge $thresholds.high)  { $level = 2 }
if ($monthYuan -ge $thresholds.block) { $level = 3 }
$levelColor = if ($level -ge 3) { "Red" } elseif ($level -ge 2) { "Yellow" } else { "Green" }
Write-Host "[cost-alert] Level: $level (monthly ¥$([math]::Round($monthYuan, 0)) / block=$($thresholds.block))" -ForegroundColor $levelColor

if ($DryRun) {
    Write-Host "[cost-alert] [DRY-RUN] would write to $healthPath" -ForegroundColor Cyan
    exit 0
}

# 写 health_status.json(读 → 合并 cost_alert → atomic 写回)
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }
$existing = @{}
if (Test-Path $healthPath) {
    try {
        $rawJson = Get-Content $healthPath -Raw
        $parsed = $rawJson | ConvertFrom-Json -ErrorAction Stop
        $existing = @{}
        foreach ($prop in $parsed.PSObject.Properties) {
            $existing[$prop.Name] = $prop.Value
        }
    } catch {
        Write-Host "[cost-alert] [WARN] $healthPath JSON 损坏;按空对象处理" -ForegroundColor Yellow
        $existing = @{}
    }
}
$existing["cost_alert"] = @{
    level = $level
    today_yuan = [math]::Round($todayYuan, 2)
    month_yuan = [math]::Round($monthYuan, 2)
    month = $yearMonth
    thresholds = $thresholds
    updated_at = (Get-Date).ToUniversalTime().ToString("o")
}

# 原子写
$json = $existing | ConvertTo-Json -Depth 5
$tmp = "$healthPath.tmp"
[System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
Move-Item -Force $tmp $healthPath

Write-Host "[cost-alert] OK Wrote $healthPath (level=$level)" -ForegroundColor Green
exit 0
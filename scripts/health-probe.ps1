<#
.SYNOPSIS
  离线/在线状态探测:每 30s(可调)ping dashscope + tavily + bing,写到 ./data/health_status.json。

.DESCRIPTION
  - 端点清单(任一可达 → ONLINE):
      1. dashscope.aliyuncs.com:443   (Qwen3.6-Plus 必须)
      2. api.tavily.com:443           (Tavily websearch 可选)
      3. api.bing.microsoft.com:443   (Bing websearch 兜底)
  - 测试方法:Test-NetConnection -Port 443(短超时,失败默认 ONLINE 避免误判)
  - 写 ./data/health_status.json:{ online: bool, timestamp, endpoints: {...} }
  - chat.ps1 启动时读这个文件,OFFLINE 时跳过 Qwen 调用

.PARAMETER DataDir
  可选:数据目录(默认 ./data)。

.PARAMETER OutputJson
  开关:stdout 输出 JSON,便于被调用方解析。

.EXAMPLE
  pwsh -File scripts/health-probe.ps1 -OutputJson
  powershell -ExecutionPolicy Bypass -File scripts/health-probe.ps1

.NOTES
  PowerShell 5.1 兼容(Test-NetConnection 在 5.1 已存在)。
  错误处理:任一探测失败默认 ONLINE(避免误判离线导致 chat 走退化路径)。
#>

[CmdletBinding()]
param(
    [string]$DataDir = "./data",
    [switch]$OutputJson = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }

# ----------------------------------------------------------------------
# 端点清单(v0.7.1 分类:critical / optional)
# ----------------------------------------------------------------------
# 设计原则(架构评审 Part 2 §9.2 #7):
#   - critical:qwen dashscope。chat.ps1 必须能调,失败 → OFFLINE。
#   - optional:tavily / bing。websearch 降级用,失败 → 仍 ONLINE,
#     chat 走纯 KB 回答(无 websearch 兜底)。
#   修复前:"全失败才 OFFLINE" → Qwen 不可达仍判 ONLINE → chat 走 Qwen
#          然后才在调用层失败 → 用户体验"沉默失败"。
#   修复后:Qwen 不可达立即 OFFLINE → chat 跳过 Qwen 直接返回 "AI 暂不可用"。

$CriticalEndpoints = @(
    @{ Host = "dashscope.aliyuncs.com";   Port = 443; Name = "qwen"   }
)

$OptionalEndpoints = @(
    @{ Host = "api.tavily.com";          Port = 443; Name = "tavily" },
    @{ Host = "api.bing.microsoft.com";  Port = 443; Name = "bing"   }
)

function Test-Endpoint {
    param(
        [string]$Hostname,
        [int]$Port
    )
    try {
        # Test-NetConnection 在 5.1 已存在,默认 WarningAction SilentlyContinue
        $r = Test-NetConnection -ComputerName $Hostname -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction Stop
        return [bool]$r
    } catch {
        return $false
    }
}

# ----------------------------------------------------------------------
# 探测循环
# ----------------------------------------------------------------------

$status = [ordered]@{
    online              = $true
    websearch_available = $false
    timestamp           = (Get-Date).ToString("o")
    endpoints           = [ordered]@{}
}

foreach ($ep in ($CriticalEndpoints + $OptionalEndpoints)) {
    Write-Step "ping $($ep.Host):$($ep.Port)"
    $ok = Test-Endpoint -Hostname $ep.Host -Port $ep.Port
    $status.endpoints[$ep.Name] = $ok
    if (-not $ok) {
        Write-Warn "$($ep.Name) 不可达"
    }
}

# online = Qwen 关键路径可达(架构评审 #7:不再"沉默失败")
$status.online = [bool]$status.endpoints["qwen"]

# websearch_available = Tavily 或 Bing 任一可达(chat 走 websearch 兜底的条件)
$status.websearch_available = [bool]($status.endpoints["tavily"] -or $status.endpoints["bing"])

# ----------------------------------------------------------------------
# 写文件
# ----------------------------------------------------------------------

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}
$statusFile = Join-Path $DataDir "health_status.json"
$json = $status | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($statusFile, $json, [System.Text.UTF8Encoding]::new($false))

Write-Step "状态写入 $statusFile (online=$($status.online))"

# ----------------------------------------------------------------------
# stdout 输出
# ----------------------------------------------------------------------

if ($OutputJson) {
    $json
} else {
    Write-Host ""
    # 修复 2.9:文案与新权重逻辑对齐(online/websearch_available 组合区分,不再笼统说"AI 与 websearch 可达")
    if ($status.online) {
        if ($status.websearch_available) {
            Write-Host "  ONLINE - Qwen 与 websearch 服务可达" -ForegroundColor Green
        } else {
            Write-Host "  ONLINE - Qwen 可达,websearch 不可达(走纯 KB 回答)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  OFFLINE - Qwen 不可达,AI 暂不可用" -ForegroundColor Red
    }
    foreach ($k in $status.endpoints.Keys) {
        $v = $status.endpoints[$k]
        $tag = if ($v) { "OK  " } else { "FAIL" }
        $color = if ($v) { "Green" } else { "Red" }
        Write-Host ("    [{0}] {1,-8} {2}" -f $tag, $k, $k) -ForegroundColor $color
    }
    Write-Host ""
}

exit 0
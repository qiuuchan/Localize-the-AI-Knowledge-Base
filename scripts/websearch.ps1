<#
.SYNOPSIS
  Websearch 降级:知识库未命中时调用外部搜索 → 标"来源:网络"。
  降级链:Tavily → Bing → 失败返回 null。

.DESCRIPTION
  - 1. 调 Tavily (POST https://api.tavily.com/search)
       body: { api_key, query, max_results }
  - 2. 失败 → 调 Bing (GET https://api.bing.microsoft.com/v7.0/search)
       header: Ocp-Apim-Subscription-Key
  - 3. 都失败 → return $null
  - 4. 返回 JSON: { source: "web:tavily"|"web:bing", results: [{title, url, snippet}] }

.PARAMETER Query
  必填:搜索关键词。

.PARAMETER TavilyKey
  可选:Tavily API Key;缺省从 .env 读 TAVILY_API_KEY。

.PARAMETER BingKey
  可选:Bing Search API Key;缺省从 .env 读 BING_SEARCH_API_KEY。

.PARAMETER MaxResults
  可选:返回结果数(默认 3)。

.PARAMETER OutputJson
  开关:stdout 输出 JSON。

.EXAMPLE
  pwsh -File scripts/websearch.ps1 -Query "餐饮 Q3 营收下滑原因"

.NOTES
  PowerShell 5.1 兼容;失败一律不抛错,降级到下一步。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]  [string]$Query,
    [string]$TavilyKey,
    [string]$BingKey,
    [ValidateRange(1, 10)] [int]$MaxResults = 3,
    [switch]$OutputJson = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')

# ----------------------------------------------------------------------
# .env 加载
# ----------------------------------------------------------------------

if (-not $TavilyKey -or -not $BingKey) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $rootDir = Split-Path -Parent $scriptDir
    $envPath = Join-Path $rootDir ".env"
    if (-not $TavilyKey) {
        $k = Get-EnvVar -EnvPath $envPath -Name "TAVILY_API_KEY"
        # 修复 2.1:用公共库 Test-IsPlaceholder 统一占位符识别(原"双重 -ne"含逻辑错误:Tavily key 不会以 sk- 开头)
        if ($k -and -not (Test-IsPlaceholder -Value $k)) {
            $TavilyKey = $k
            Write-Step "从 .env 读 TAVILY_API_KEY"
        }
    }
    if (-not $BingKey) {
        $k = Get-EnvVar -EnvPath $envPath -Name "BING_SEARCH_API_KEY"
        if ($k -and -not (Test-IsPlaceholder -Value $k)) {
            $BingKey = $k
            Write-Step "从 .env 读 BING_SEARCH_API_KEY"
        }
    }
}

# ----------------------------------------------------------------------
# 1. Tavily
# ----------------------------------------------------------------------

function Invoke-Tavily {
    param(
        [string]$QueryText,
        [string]$Key,
        [int]$Limit
    )
    $url = "https://api.tavily.com/search"
    $body = @{
        api_key     = $Key
        query       = $QueryText
        max_results = $Limit
    } | ConvertTo-Json -Depth 4 -Compress
    $headers = @{ "Content-Type" = "application/json" }
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -Body $body `
                  -TimeoutSec 30 -UseBasicParsing
        if ($resp.StatusCode -ne 200) {
            throw "HTTP $($resp.StatusCode): $($resp.Content)"
        }
        $j = $resp.Content | ConvertFrom-Json
        $results = @()
        if ($j.results) {
            foreach ($r in $j.results) {
                $results += @{
                    title   = [string]$r.title
                    url     = [string]$r.url
                    snippet = [string]$r.content
                }
            }
        }
        return @{
            source  = "web:tavily"
            results = $results
        }
    } catch {
        Write-Warn "Tavily 调用失败:$($_.Exception.Message)"
        return $null
    }
}

# ----------------------------------------------------------------------
# 2. Bing
# ----------------------------------------------------------------------

function Invoke-Bing {
    param(
        [string]$QueryText,
        [string]$Key,
        [int]$Limit
    )
    $url = "https://api.bing.microsoft.com/v7.0/search?q=$([uri]::EscapeDataString($QueryText))&count=$Limit"
    $headers = @{ "Ocp-Apim-Subscription-Key" = $Key }
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Get -Headers $headers `
                  -TimeoutSec 30 -UseBasicParsing
        if ($resp.StatusCode -ne 200) {
            throw "HTTP $($resp.StatusCode): $($resp.Content)"
        }
        $j = $resp.Content | ConvertFrom-Json
        $results = @()
        if ($j.webPages -and $j.webPages.value) {
            foreach ($r in $j.webPages.value) {
                $results += @{
                    title   = [string]$r.name
                    url     = [string]$r.url
                    snippet = [string]$r.snippet
                }
            }
        }
        return @{
            source  = "web:bing"
            results = $results
        }
    } catch {
        Write-Warn "Bing 调用失败:$($_.Exception.Message)"
        return $null
    }
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

$result = $null

# 1. Tavily
if ($TavilyKey) {
    Write-Step "尝试 Tavily (query=$Query)"
    $result = Invoke-Tavily -QueryText $Query -Key $TavilyKey -Limit $MaxResults
    if ($result) {
        Write-Step "Tavily 命中 $($result.results.Count) 条"
    }
} else {
    Write-Warn "Tavily Key 未配置,跳过"
}

# 2. Bing fallback
if (-not $result -and $BingKey) {
    Write-Step "回退 Bing (query=$Query)"
    $result = Invoke-Bing -QueryText $Query -Key $BingKey -Limit $MaxResults
    if ($result) {
        Write-Step "Bing 命中 $($result.results.Count) 条"
    }
} elseif (-not $result) {
    Write-Warn "Bing Key 未配置,跳过"
}

# 3. 都失败
if (-not $result) {
    Write-Warn "Tavily + Bing 均失败,返回 null"
    if ($OutputJson) {
        "null"
    } else {
        Write-Host ""
        Write-Host "  AI 暂时不可用 (Tavily + Bing 均失败)" -ForegroundColor Yellow
        Write-Host ""
    }
    exit 0
}

# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------

if ($OutputJson) {
    $result | ConvertTo-Json -Depth 5
} else {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  来源: $($result.source)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    foreach ($r in $result.results) {
        Write-Host ("  - {0}" -f $r.title) -ForegroundColor Green
        Write-Host ("    URL: {0}" -f $r.url) -ForegroundColor Gray
        Write-Host ("    {0}" -f $r.snippet) -ForegroundColor Gray
        Write-Host ""
    }
}

exit 0
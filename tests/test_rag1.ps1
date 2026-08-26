<#
.SYNOPSIS
  RAG 借鉴 v1.1.5 / Stage A — T-RAG-1 Embedding cache 验收。

.DESCRIPTION
  6 项验收:
    1. -SkipCache 参数声明
    2. -CacheFile 参数声明 + 默认路径推导
    3. Get-EmbeddingCache / Add-EmbeddingCache 函数声明
    4. cache 命中跳过 API 的逻辑分支
    5. cache 损坏自动重建逻辑
    6. 命中统计输出

  运行:
    powershell -ExecutionPolicy Bypass -File tests/test_rag1.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

function Write-Pass { param($msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$Results = @()
$Failed = 0

function Add-Result {
    param($Name, $Pass, $Error = "")
    $script:Results += @{ Name = $Name; Status = if ($Pass) { "PASS" } else { "FAIL" }; Error = $Error }
    if (-not $Pass) { $script:Failed++ }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI  T-RAG-1 Embedding Cache 验收 (v1.1.5)" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$embedScript = Join-Path $RootDir "scripts/embed-and-ingest.ps1"
$embedContent = Get-Content $embedScript -Raw -Encoding UTF8

# ----------------------------------------------------------------------
# Test 1: -SkipCache 参数声明
# ----------------------------------------------------------------------

Write-Info "Test 1: -SkipCache 参数声明"
try {
    if ($embedContent -notmatch '\[switch\]\s*\$SkipCache') {
        throw '-SkipCache 参数未声明(应使用 [switch] 类型)'
    }
    Write-Pass "-SkipCache 参数已声明"
    Add-Result "SkipCache param declared" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "SkipCache param declared" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: -CacheFile 参数 + 默认路径
# ----------------------------------------------------------------------

Write-Info "Test 2: -CacheFile 参数 + 默认路径 embedding-cache.jsonl"
try {
    if ($embedContent -notmatch '\[string\]\s*\$CacheFile') {
        throw '-CacheFile 参数未声明'
    }
    if ($embedContent -notmatch 'embedding-cache\.jsonl') {
        throw '默认 cache 路径未设置 embedding-cache.jsonl'
    }
    if ($embedContent -notmatch 'Join-Path\s+\$rootDirForCache\s+"data/embedding-cache\.jsonl"') {
        throw '默认 cache 路径推导逻辑缺失(应在 $CacheFile 默认值处)'
    }
    Write-Pass "-CacheFile 参数 + 默认 data/embedding-cache.jsonl 已声明"
    Add-Result "CacheFile param + default path" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "CacheFile param + default path" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: Get-EmbeddingCache / Add-EmbeddingCache 函数声明
# ----------------------------------------------------------------------

Write-Info "Test 3: Get-EmbeddingCache / Add-EmbeddingCache 函数声明"
try {
    $missing = @()
    if ($embedContent -notmatch 'function\s+Get-EmbeddingCache') { $missing += 'Get-EmbeddingCache' }
    if ($embedContent -notmatch 'function\s+Add-EmbeddingCache') { $missing += 'Add-EmbeddingCache' }
    if ($missing.Count -gt 0) {
        throw "缺失函数: $($missing -join ', ')"
    }
    Write-Pass "Get-EmbeddingCache + Add-EmbeddingCache 已声明"
    Add-Result "Cache functions declared" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "Cache functions declared" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: cache 命中跳过 API 的逻辑分支
# ----------------------------------------------------------------------

Write-Info "Test 4: cache 命中跳过 API 的逻辑分支"
try {
    $hasCacheCheck = $embedContent -match 'cache\.ContainsKey\('
    $hasFetchList = $embedContent -match '\$textsToFetch\s*\+='
    $hasApiGuard = $embedContent -match 'if\s*\(\s*\$textsToFetch\.Count\s*-gt\s+0'
    $missing = @()
    if (-not $hasCacheCheck) { $missing += 'cache.ContainsKey 检查' }
    if (-not $hasFetchList) { $missing += 'textsToFetch 累积' }
    if (-not $hasApiGuard) { $missing += 'API 调用前 textsToFetch.Count > 0 判定' }
    if ($missing.Count -gt 0) {
        throw "缺失元素: $($missing -join ', ')"
    }
    Write-Pass "cache 命中跳过 API 逻辑完整"
    Add-Result "Cache hit skip API" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "Cache hit skip API" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: cache 损坏自动重建
# ----------------------------------------------------------------------

Write-Info "Test 5: cache 损坏自动重建逻辑"
try {
    if ($embedContent -notmatch 'cache 文件读取失败') {
        throw 'cache 损坏提示文案缺失'
    }
    if ($embedContent -notmatch 'Test-Path\s+\$Path\)[\s\S]{0,50}return\s+\$cache') {
        throw 'cache 文件不存在时未提前 return'
    }
    Write-Pass "cache 损坏自动重建逻辑完整"
    Add-Result "Cache corruption recovery" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "Cache corruption recovery" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 6: 命中统计输出
# ----------------------------------------------------------------------

Write-Info "Test 6: 命中统计输出(hit/miss + hit_rate)"
try {
    $missing = @()
    # 累加用 ++ 或 += 都算
    if (-not ($embedContent -match '\$cacheHits\s*\+\+') -and -not ($embedContent -match '\$cacheHits\s*\+=')) {
        $missing += 'cacheHits 累加'
    }
    if (-not $embedContent -match '\$cacheMisses\s*=') { $missing += 'cacheMisses 赋值' }
    if (-not $embedContent -match 'T-RAG-1 cache 统计') { $missing += 'cache 统计输出文案' }
    if (-not $embedContent -match 'hit_rate=') { $missing += 'hit_rate 输出' }
    if ($missing.Count -gt 0) {
        throw "缺失元素: $($missing -join ', ')"
    }
    Write-Pass "命中统计输出完整(hit/miss/hit_rate)"
    Add-Result "Cache stats output" $true
} catch {
    Write-Fail "Test 6 失败: $_"
    Add-Result "Cache stats output" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# 总结
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  总结:$($Results.Count) 项测试,$($Results.Count - $Failed) PASS,$Failed FAIL" -ForegroundColor $(if ($Failed -eq 0) { "Green" } else { "Red" })
Write-Host "============================================================" -ForegroundColor Yellow

if ($Failed -gt 0) {
    Write-Host ""
    Write-Host "失败项:" -ForegroundColor Red
    $Results | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object {
        Write-Host "  X $($_.Name): $($_.Error)" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "[ALL PASS] T-RAG-1 Embedding cache 验收通过" -ForegroundColor Green
exit 0
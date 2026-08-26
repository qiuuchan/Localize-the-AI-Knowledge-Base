<#
.SYNOPSIS
  KB-AI · v0.8.1 双模型路由 mock 测试

.DESCRIPTION
  不连真 API,仅 dot-source scripts/chat.ps1 并测试 Select-ModelForQuery:
    1. 简单问题默认走 Plus 模型
    2. 命中复杂关键词走 Max 模型
    3. -DisableModelRouting 强制单模型
    4. 自定义关键词生效

.RUN
  powershell -ExecutionPolicy Bypass -File tests/test_model_routing.ps1
  pwsh -File tests/test_model_routing.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

function Write-Pass { param([string]$msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$script:Results = @()
$script:Failed = 0

function Add-Result {
    param([string]$Name, [bool]$Pass, [string]$Error = "")
    $script:Results += @{ Name = $Name; Status = if ($Pass) { "PASS" } else { "FAIL" }; Error = $Error }
    if (-not $Pass) { $script:Failed++ }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI v0.8.1 双模型路由 mock 测试" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# dot-source chat.ps1(只暴露函数,不执行主流程);提供占位 Question 满足 Mandatory
$chatFile = Join-Path $RootDir "scripts/chat.ps1"
if (-not (Test-Path -LiteralPath $chatFile)) {
    Write-Fail "chat.ps1 不存在"
    Add-Result "chat.ps1 exists" $false "missing"
    exit 1
}

Write-Info "加载 chat.ps1 的 Select-ModelForQuery..."
. $chatFile -Question "test"

if (-not (Get-Command Select-ModelForQuery -ErrorAction SilentlyContinue)) {
    Write-Fail "Select-ModelForQuery 未导出"
    Add-Result "Select-ModelForQuery exported" $false
    exit 1
}
Write-Pass "Select-ModelForQuery 已导出"
Add-Result "Select-ModelForQuery exported" $true

# ----------------------------------------------------------------------
# Test 1: 简单问题 → Plus
# ----------------------------------------------------------------------
Write-Info "Test 1: 简单问题默认路由到 Plus"
try {
    $r = Select-ModelForQuery -Query "红烧肉怎么做" `
                              -ModelName "qwen3.6-plus" `
                              -ModelNameMax "qwen3.7-max" `
                              -DisableModelRouting $false `
                              -ModelRoutingKeywords "对比,分析为什么,如何改进"
    if ($r.model -ne "qwen3.6-plus") { throw "期望 qwen3.6-plus, 实际 $($r.model)" }
    if ($r.reason -ne "default") { throw "期望 reason=default, 实际 $($r.reason)" }
    Write-Pass "简单问题路由到 Plus($($r.reason))"
    Add-Result "simple -> Plus" $true
} catch {
    Write-Fail "Test 1: $_"
    Add-Result "simple -> Plus" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: 命中复杂关键词 → Max
# ----------------------------------------------------------------------
Write-Info "Test 2: 命中复杂关键词路由到 Max"
try {
    $r = Select-ModelForQuery -Query "请对比 Docker 和 Kubernetes 的优缺点" `
                              -ModelName "qwen3.6-plus" `
                              -ModelNameMax "qwen3.7-max" `
                              -DisableModelRouting $false `
                              -ModelRoutingKeywords "对比,分析为什么,如何改进"
    if ($r.model -ne "qwen3.7-max") { throw "期望 qwen3.7-max, 实际 $($r.model)" }
    if ($r.reason -ne "complex_keyword") { throw "期望 reason=complex_keyword, 实际 $($r.reason)" }
    Write-Pass "命中关键词路由到 Max($($r.reason))"
    Add-Result "complex keyword -> Max" $true
} catch {
    Write-Fail "Test 2: $_"
    Add-Result "complex keyword -> Max" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: 禁用路由 → 强制 Plus
# ----------------------------------------------------------------------
Write-Info "Test 3: -DisableModelRouting 强制单模型"
try {
    $r = Select-ModelForQuery -Query "请对比 A 和 B" `
                              -ModelName "qwen3.6-plus" `
                              -ModelNameMax "qwen3.7-max" `
                              -DisableModelRouting $true `
                              -ModelRoutingKeywords "对比"
    if ($r.model -ne "qwen3.6-plus") { throw "期望 qwen3.6-plus, 实际 $($r.model)" }
    if ($r.reason -ne "disabled") { throw "期望 reason=disabled, 实际 $($r.reason)" }
    Write-Pass "禁用路由时强制 Plus($($r.reason))"
    Add-Result "disabled routing -> Plus" $true
} catch {
    Write-Fail "Test 3: $_"
    Add-Result "disabled routing -> Plus" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: 自定义关键词生效
# ----------------------------------------------------------------------
Write-Info "Test 4: 自定义关键词生效"
try {
    $r = Select-ModelForQuery -Query "帮我评估这个方案" `
                              -ModelName "qwen3.6-plus" `
                              -ModelNameMax "qwen3.7-max" `
                              -DisableModelRouting $false `
                              -ModelRoutingKeywords "评估,方案"
    if ($r.model -ne "qwen3.7-max") { throw "期望 qwen3.7-max, 实际 $($r.model)" }
    Write-Pass "自定义关键词命中 Max($($r.reason))"
    Add-Result "custom keywords -> Max" $true
} catch {
    Write-Fail "Test 4: $_"
    Add-Result "custom keywords -> Max" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
$total = $script:Results.Count
$passed = $total - $script:Failed
Write-Host "  结果: $passed / $total 通过" -ForegroundColor $(if ($script:Failed -eq 0) { "Green" } else { "Red" })
Write-Host "============================================================" -ForegroundColor Yellow
foreach ($res in $script:Results) {
    $color = if ($res.Status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "  [$($res.Status)] $($res.Name)" -ForegroundColor $color
    if ($res.Error) { Write-Host "       $($res.Error)" -ForegroundColor Red }
}
Write-Host ""

exit $script:Failed

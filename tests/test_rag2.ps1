<#
.SYNOPSIS
  RAG 借鉴 v1.1.5 / Stage A — T-RAG-2 Markdown header-aware 切片 验收。

.DESCRIPTION
  7 项验收:
    1. Split-ByHeaders 函数声明
    2. Split-IntoChunks 加 HeaderAware 参数
    3. Split-IntoChunks 加 Overlap 参数
    4. chunk meta 包含 header_path / header_level
    5. chunk source 字段含 §header_path 后缀
    6. HeaderAware 默认 true
    7. HeaderAware=false fallback(纯文本兼容)

  运行:
    powershell -ExecutionPolicy Bypass -File tests/test_rag2.ps1
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
Write-Host "  KB-AI  T-RAG-2 Markdown Header-aware 切片 验收 (v1.1.5)" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$parseScript = Join-Path $RootDir "scripts/parse-doc.ps1"
$parseContent = Get-Content $parseScript -Raw -Encoding UTF8

# ----------------------------------------------------------------------
# Test 1: Split-ByHeaders 函数声明
# ----------------------------------------------------------------------

Write-Info "Test 1: Split-ByHeaders 函数声明"
try {
    $missing = @()
    if ($parseContent -notmatch 'function\s+Split-ByHeaders') { $missing += 'function Split-ByHeaders' }
    if ($parseContent -notmatch 'pathStack') { $missing += 'pathStack 维护' }
    # 标题正则:检查源中是否同时有 #{1,6} 和 (.+) 两个捕获组
    if ($parseContent -notmatch '#\{1,6\}') { $missing += '标题数量范围 #{1,6}' }
    if ($parseContent -notmatch '\(\.\+\)') { $missing += '捕获组 (.+)' }
    if ($missing.Count -gt 0) {
        throw "缺失元素: $($missing -join ', ')"
    }
    Write-Pass "Split-ByHeaders 已声明,pathStack + 标题正则 OK"
    Add-Result "Split-ByHeaders declared" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "Split-ByHeaders declared" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: Split-IntoChunks 加 HeaderAware 参数
# ----------------------------------------------------------------------

Write-Info "Test 2: Split-IntoChunks 加 HeaderAware 参数"
try {
    if ($parseContent -notmatch '\[bool\]\s*\$HeaderAware') {
        throw 'Split-IntoChunks 缺少 HeaderAware 参数'
    }
    Write-Pass "Split-IntoChunks HeaderAware 参数已声明"
    Add-Result "HeaderAware param" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "HeaderAware param" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: Split-IntoChunks 加 Overlap 参数
# ----------------------------------------------------------------------

Write-Info "Test 3: Split-IntoChunks 加 Overlap 参数(默认 150)"
try {
    if ($parseContent -notmatch '\[int\]\s*\$Overlap\s*=\s*150') {
        throw 'Split-IntoChunks Overlap 默认值非 150'
    }
    if ($parseContent -notmatch 'Substring\(\$buf\.Length\s*-\s*\$Overlap\)') {
        throw 'Overlap tail 保留 Substring 逻辑缺失'
    }
    Write-Pass "Split-IntoChunks Overlap 参数 + tail 保留逻辑完整"
    Add-Result "Overlap param" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "Overlap param" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: chunk meta 包含 header_path / header_level
# ----------------------------------------------------------------------

Write-Info "Test 4: chunk meta 包含 header_path / header_level"
try {
    $missing = @()
    if ($parseContent -notmatch 'header_path\s*=\s*\$curHeaderPath') { $missing += 'header_path' }
    if ($parseContent -notmatch 'header_level\s*=\s*\$curLevel') { $missing += 'header_level' }
    if ($missing.Count -gt 0) {
        throw "meta 缺失字段: $($missing -join ', ')"
    }
    Write-Pass "chunk meta 含 header_path + header_level"
    Add-Result "Chunk meta fields" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "Chunk meta fields" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: chunk source 字段含 §header_path 后缀
# ----------------------------------------------------------------------

Write-Info "Test 5: chunk source 字段含 §header_path 后缀"
try {
    if ($parseContent -notmatch 'IsNullOrEmpty\(\$curHeaderPath\)') {
        throw 'source 字段未根据 header_path 走 IsNullOrEmpty 分支'
    }
    if ($parseContent -notmatch '\$Source\s+§\$curHeaderPath') {
        throw 'source 字段未拼接 § + header_path'
    }
    Write-Pass "chunk source 含 §header_path 后缀"
    Add-Result "Chunk source format" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "Chunk source format" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 6: HeaderAware 默认 true
# ----------------------------------------------------------------------

Write-Info "Test 6: HeaderAware 默认 true(开启)"
try {
    if ($parseContent -notmatch '\[bool\]\s*\$HeaderAware\s*=\s*\$true') {
        throw 'HeaderAware 默认值非 $true(应开启)'
    }
    Write-Pass "HeaderAware 默认开启"
    Add-Result "HeaderAware default true" $true
} catch {
    Write-Fail "Test 6 失败: $_"
    Add-Result "HeaderAware default true" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 7: HeaderAware=false fallback
# ----------------------------------------------------------------------

Write-Info "Test 7: HeaderAware=false fallback(纯文本兼容)"
try {
    if ($parseContent -notmatch 'header_path\s*=\s*""') {
        throw 'fallback 路径未设置 header_path = 空字符串'
    }
    if ($parseContent -notmatch 'level\s*=\s*0') {
        throw 'fallback 路径未设置 level = 0'
    }
    Write-Pass "HeaderAware=false fallback 路径完整(纯文本兼容)"
    Add-Result "HeaderAware fallback" $true
} catch {
    Write-Fail "Test 7 失败: $_"
    Add-Result "HeaderAware fallback" $false $_.Exception.Message
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
Write-Host "[ALL PASS] T-RAG-2 Markdown header-aware 验收通过" -ForegroundColor Green
exit 0
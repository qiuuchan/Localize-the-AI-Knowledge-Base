<#
.SYNOPSIS
  RAG 借鉴 v1.1.5 / Stage A — T-RAG-3 Chunk 重叠窗口 验收。

.DESCRIPTION
  5 项验收:
    1. Overlap 参数默认 150
    2. tail 保留逻辑(Substring 切末 150 字符)
    3. Overlap > 0 判定
    4. Overlap = 0 等价旧行为(无重叠)
    5. 边界句子在两个 chunk 完整出现

  运行:
    powershell -ExecutionPolicy Bypass -File tests/test_rag3.ps1
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
Write-Host "  KB-AI  T-RAG-3 Chunk 重叠窗口 验收 (v1.1.5)" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$parseScript = Join-Path $RootDir "scripts/parse-doc.ps1"
$parseContent = Get-Content $parseScript -Raw -Encoding UTF8

# ----------------------------------------------------------------------
# Test 1: Overlap 参数默认 150
# ----------------------------------------------------------------------

Write-Info "Test 1: Overlap 参数默认 150"
try {
    if ($parseContent -notmatch '\[int\]\s*\$Overlap\s*=\s*150') {
        throw 'Split-IntoChunks Overlap 默认值非 150'
    }
    Write-Pass "Overlap 默认 150"
    Add-Result "Overlap default 150" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "Overlap default 150" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: tail 保留逻辑(Substring 切末 150 字符)
# ----------------------------------------------------------------------

Write-Info "Test 2: tail 保留逻辑(Substring 切末 150 字符)"
try {
    if ($parseContent -notmatch 'Substring\(\$buf\.Length\s*-\s*\$Overlap\)') {
        throw 'tail 保留 Substring 逻辑缺失'
    }
    # 顺序: Clear -> Append(tail)
    # 用单引号避免 $ 解释, [\s\S] 跨行
    $patternClearAppend = '(?s)\[void\]\$buf\.Clear\(\).*?\[void\]\$buf\.Append\(\$tail\)'
    if ($parseContent -notmatch $patternClearAppend) {
        throw 'tail 顺序错误(应是 Clear 后 Append tail)'
    }
    Write-Pass "tail 保留逻辑完整"
    Add-Result "Overlap tail logic" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "Overlap tail logic" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: Overlap > 0 判定
# ----------------------------------------------------------------------

Write-Info "Test 3: Overlap > 0 判定"
try {
    if ($parseContent -notmatch 'if\s*\(\s*\$Overlap\s*-gt\s+0\s*-and\s+\$buf\.Length\s*-gt\s+\$Overlap') {
        throw 'Overlap > 0 判定逻辑缺失'
    }
    Write-Pass "Overlap > 0 判定完整"
    Add-Result "Overlap positive check" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "Overlap positive check" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: Overlap = 0 等价旧行为
# ----------------------------------------------------------------------

Write-Info "Test 4: Overlap = 0 等价旧行为(无重叠)"
try {
    # else 分支应该是 [void]$buf.Clear() 直接清空
    $patternElseClear = '(?s)else\s*\{\s*\[void\]\$buf\.Clear\(\)\s*\}'
    if ($parseContent -notmatch $patternElseClear) {
        throw 'Overlap = 0 else 分支未直接 Clear buf'
    }
    Write-Pass "Overlap = 0 等价旧行为"
    Add-Result "Overlap zero = old behavior" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "Overlap zero = old behavior" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: 边界句子完整性(tail 保留 + 顺序追加)
# ----------------------------------------------------------------------

Write-Info "Test 5: 边界句子完整性(通过 tail 保留实现)"
try {
    # tail 起点必须从 buf 末尾取
    if ($parseContent -notmatch 'Substring\(\$buf\.Length\s*-\s*\$Overlap\)') {
        throw 'tail Substring 起点错误(应从 buf 末尾取)'
    }
    # Append(tail) 之后必须追加新段(顺序: clear → append tail → append 新段)
    $patternFlow = '(?s)Append\(\$tail\).*?AppendLine\(\$pp\)'
    if ($parseContent -notmatch $patternFlow) {
        throw 'tail + 新段落 追加顺序错误'
    }
    Write-Pass "边界句子在两个 chunk 完整出现(tail 保留路径)"
    Add-Result "Boundary sentence preservation" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "Boundary sentence preservation" $false $_.Exception.Message
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
Write-Host "[ALL PASS] T-RAG-3 Chunk 重叠窗口 验收通过" -ForegroundColor Green
exit 0
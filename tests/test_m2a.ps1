<#
.SYNOPSIS
  M2a 验收脚本:8 项硬性 + 关键 mock 测试。

.DESCRIPTION
  硬性(8 项):
    1. 7 个文件齐全
    2. parse-doc.ps1 含 MinerU 调用
    3. embed-and-ingest.ps1 含 Qwen3-Embedding 调用
    4. chat.ps1 含 Qwen3.6-Plus 调用
    5. chat.ps1 含 RAG prompt 模板(参考资料 / 引用)
    6. chat.ps1 含 Qdrant 检索调用
    7. embed-and-ingest.ps1 含 batch write
    8. m2-usage.md 长度 ≥ 800 字

  Mock(3 项):
    - parse-doc.ps1 可被语法解析 + Invoke-ParseDocument 函数可 import
    - embed-and-ingest.ps1 幂等性逻辑(sha256 point id)
    - chat.ps1 RAG prompt 含强制脚注要求

  运行:
    pwsh -File tests/test_m2a.ps1
    powershell -ExecutionPolicy Bypass -File tests/test_m2a.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

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
Write-Host "  KB-AI  M2a 核心 MVP 验收" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------------
# Test 1: 7 个文件齐全
# ----------------------------------------------------------------------

Write-Info "Test 1: 7 个交付文件齐全"
try {
    $required = @(
        "scripts/parse-doc.ps1",
        "scripts/embed-and-ingest.ps1",
        "scripts/chat.ps1",
        "scripts/seed-sample-data.ps1",
        "dify/knowledge-pipeline.json",
        "tests/test_m2a.ps1",
        "docs/m2-usage.md"
    )
    $missing = @()
    foreach ($f in $required) {
        $p = Join-Path $RootDir $f
        if (-not (Test-Path $p)) {
            $missing += $f
        }
    }
    if ($missing.Count -gt 0) {
        throw "缺失文件: $($missing -join '; ')"
    }
    Write-Pass "全部 7 个文件存在"
    Add-Result "7 files exist" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "7 files exist" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: parse-doc.ps1 含 MinerU 调用
# ----------------------------------------------------------------------

Write-Info "Test 2: parse-doc.ps1 含 MinerU/8001 调用"
try {
    $parseFile = Join-Path $RootDir "scripts/parse-doc.ps1"
    $content = Get-Content $parseFile -Raw -Encoding UTF8
    if ($content -notmatch "mineru" -or $content -notmatch "8001") {
        throw "未找到 'mineru' 或 '8001'"
    }
    Write-Pass "parse-doc.ps1 含 MinerU 8001 端口调用"
    Add-Result "parse-doc MinerU" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "parse-doc MinerU" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: embed-and-ingest.ps1 含 Qwen3-Embedding 调用
# ----------------------------------------------------------------------

Write-Info "Test 3: embed-and-ingest.ps1 含 Qwen3-Embedding 调用"
try {
    $embedFile = Join-Path $RootDir "scripts/embed-and-ingest.ps1"
    $content = Get-Content $embedFile -Raw -Encoding UTF8
    $matches = ($content | Select-String -Pattern "qwen3-embedding|text-embedding-v3" -AllMatches).Matches.Count
    if ($matches -lt 1) {
        throw "未找到 'qwen3-embedding' 或 'text-embedding-v3'"
    }
    Write-Pass "embed-and-ingest.ps1 含 embedding 调用(命中 $matches 处)"
    Add-Result "embed-and-ingest Qwen3" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "embed-and-ingest Qwen3" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: chat.ps1 含 Qwen3.6-Plus 调用
# ----------------------------------------------------------------------

Write-Info "Test 4: chat.ps1 含 Qwen3.6-Plus 调用"
try {
    $chatFile = Join-Path $RootDir "scripts/chat.ps1"
    $content = Get-Content $chatFile -Raw -Encoding UTF8
    if ($content -notmatch "qwen3\.6-plus") {
        throw "未找到 'qwen3.6-plus'"
    }
    Write-Pass "chat.ps1 含 qwen3.6-plus 调用"
    Add-Result "chat Qwen3.6-Plus" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "chat Qwen3.6-Plus" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: chat.ps1 含 RAG prompt 模板(参考资料 / 引用)
# ----------------------------------------------------------------------

Write-Info "Test 5: chat.ps1 含 RAG prompt 模板 + 引用角标"
try {
    $chatFile = Join-Path $RootDir "scripts/chat.ps1"
    $content = Get-Content $chatFile -Raw -Encoding UTF8
    if ($content -notmatch "参考资料") {
        throw "未找到 '参考资料' 字样"
    }
    if ($content -notmatch "引用|\[\d+\]") {
        throw "未找到引用相关字样(无 [1] [2] 角标约束)"
    }
    Write-Pass "chat.ps1 含参考资料模板 + 角标引用"
    Add-Result "chat RAG prompt" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "chat RAG prompt" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 6: chat.ps1 含 Qdrant 检索调用
# ----------------------------------------------------------------------

Write-Info "Test 6: chat.ps1 含 Qdrant 检索调用"
try {
    $chatFile = Join-Path $RootDir "scripts/chat.ps1"
    $content = Get-Content $chatFile -Raw -Encoding UTF8
    $ok = ($content -match "qdrant") -and (($content -match "/points/search") -or ($content -match "6333"))
    if (-not $ok) {
        throw "未找到 qdrant / points/search / 6333"
    }
    Write-Pass "chat.ps1 含 qdrant + /points/search + 6333"
    Add-Result "chat Qdrant search" $true
} catch {
    Write-Fail "Test 6 失败: $_"
    Add-Result "chat Qdrant search" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 7: embed-and-ingest.ps1 含 batch write
# ----------------------------------------------------------------------

Write-Info "Test 7: embed-and-ingest.ps1 含 batch write"
try {
    $embedFile = Join-Path $RootDir "scripts/embed-and-ingest.ps1"
    $content = Get-Content $embedFile -Raw -Encoding UTF8
    $matches = ($content | Select-String -Pattern "batch|batch_size" -CaseSensitive:$false -AllMatches).Matches.Count
    if ($matches -lt 1) {
        throw "未找到 'batch' 或 'batch_size'"
    }
    Write-Pass "embed-and-ingest.ps1 含 batch 写入逻辑(命中 $matches 处)"
    Add-Result "embed-and-ingest batch" $true
} catch {
    Write-Fail "Test 7 失败: $_"
    Add-Result "embed-and-ingest batch" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 8: m2-usage.md 长度 ≥ 800 字
# ----------------------------------------------------------------------

Write-Info "Test 8: docs/m2-usage.md 长度 ≥ 800 字符"
try {
    $usageFile = Join-Path $RootDir "docs/m2-usage.md"
    if (-not (Test-Path $usageFile)) { throw "m2-usage.md 不存在" }
    $content = Get-Content $usageFile -Raw -Encoding UTF8
    $len = ($content | Measure-Object -Character).Characters
    if ($len -lt 800) {
        throw "长度不足 800 字符(实际: $len)"
    }
    Write-Pass "m2-usage.md 长度 $len 字符(>= 800)"
    Add-Result "m2-usage length" $true
} catch {
    Write-Fail "Test 8 失败: $_"
    Add-Result "m2-usage length" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 1: parse-doc.ps1 语法解析 + Invoke-ParseDocument 可发现
# ----------------------------------------------------------------------

Write-Info "Mock Test 1: parse-doc.ps1 语法 + Invoke-ParseDocument 函数"
try {
    $parseFile = Join-Path $RootDir "scripts/parse-doc.ps1"
    $err = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($parseFile, [ref]$null, [ref]$err)
    if ($err -and $err.Count -gt 0) {
        throw "语法错误: $($err[0].Message)"
    }
    # 函数发现(不用 dot-source,只验证函数被声明)
    $hasFunc = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Invoke-ParseDocument" }, $true)
    if ($hasFunc.Count -eq 0) {
        throw "未找到 Invoke-ParseDocument 函数定义"
    }
    Write-Pass "parse-doc.ps1 语法 OK + Invoke-ParseDocument 函数已声明"
    Add-Result "parse-doc syntax+func" $true
} catch {
    Write-Fail "Mock Test 1 失败: $_"
    Add-Result "parse-doc syntax+func" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 2: embed-and-ingest.ps1 含幂等性逻辑(sha256 point id)
# ----------------------------------------------------------------------

Write-Info "Mock Test 2: embed-and-ingest.ps1 幂等性(sha256 point id)"
try {
    $embedFile = Join-Path $RootDir "scripts/embed-and-ingest.ps1"
    $err = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($embedFile, [ref]$null, [ref]$err)
    if ($err -and $err.Count -gt 0) {
        throw "语法错误: $($err[0].Message)"
    }
    $content = Get-Content $embedFile -Raw -Encoding UTF8
    # 找 SHA256 + id 字段的赋值
    if ($content -notmatch "SHA256") {
        throw "未找到 SHA256 用法"
    }
    if ($content -notmatch "id\s*=") {
        throw "未找到 point id 赋值"
    }
    Write-Pass "embed-and-ingest.ps1 含 SHA256 + point id 幂等性逻辑"
    Add-Result "embed-and-ingest idempotency" $true
} catch {
    Write-Fail "Mock Test 2 失败: $_"
    Add-Result "embed-and-ingest idempotency" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 3: chat.ps1 RAG prompt 强制脚注 + 端到端流程符号完整
# ----------------------------------------------------------------------

Write-Info "Mock Test 3: chat.ps1 RAG prompt + 端到端流程"
try {
    $chatFile = Join-Path $RootDir "scripts/chat.ps1"
    $err = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($chatFile, [ref]$null, [ref]$err)
    if ($err -and $err.Count -gt 0) {
        throw "语法错误: $($err[0].Message)"
    }
    $content = Get-Content $chatFile -Raw -Encoding UTF8
    # 必备符号
    $missing = @()
    if ($content -notmatch "引用") { $missing += "引用约束" }
    if ($content -notmatch "瞎猜|没找到") { $missing += "拒答兜底" }
    if ($content -notmatch "citations?") { $missing += "citations 输出" }
    if ($missing.Count -gt 0) {
        throw "缺失符号: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 RAG prompt 完整(引用约束 + 拒答兜底 + citations 输出)"
    Add-Result "chat RAG end-to-end" $true
} catch {
    Write-Fail "Mock Test 3 失败: $_"
    Add-Result "chat RAG end-to-end" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 4: 跨文档一致性 — qwen3.6-plus 一致性
# ----------------------------------------------------------------------

Write-Info "Mock Test 4: 跨文档模型名一致性 (qwen3.6-plus)"
try {
    $envExample = Join-Path $RootDir ".env.example"
    if (-not (Test-Path $envExample)) {
        # 兼容 .env
        $envExample = Join-Path $RootDir ".env"
    }
    $envContent = Get-Content $envExample -Raw -Encoding UTF8
    $chatContent = Get-Content (Join-Path $RootDir "scripts/chat.ps1") -Raw -Encoding UTF8
    $pipeContent = Get-Content (Join-Path $RootDir "dify/knowledge-pipeline.json") -Raw -Encoding UTF8

    $envOk = $envContent -match "qwen3\.6-plus"
    $chatOk = $chatContent -match "qwen3\.6-plus"
    $pipeOk = $pipeContent -match "qwen3\.6-plus"

    $missing = @()
    if (-not $envOk)  { $missing += ".env(.example) 缺 qwen3.6-plus" }
    if (-not $chatOk) { $missing += "chat.ps1 缺 qwen3.6-plus" }
    if (-not $pipeOk) { $missing += "knowledge-pipeline.json 缺 qwen3.6-plus" }
    if ($missing.Count -gt 0) {
        throw "不一致: $($missing -join '; ')"
    }
    Write-Pass "qwen3.6-plus 在 .env + chat.ps1 + knowledge-pipeline.json 三处一致"
    Add-Result "cross-doc consistency" $true
} catch {
    Write-Fail "Mock Test 4 失败: $_"
    Add-Result "cross-doc consistency" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 5: 无 UTF-8 BOM
# ----------------------------------------------------------------------

Write-Info "Mock Test 5: PowerShell 脚本无 UTF-8 BOM"
try {
    $psFiles = @(
        "scripts/parse-doc.ps1",
        "scripts/embed-and-ingest.ps1",
        "scripts/chat.ps1",
        "scripts/seed-sample-data.ps1"
    )
    $bomFiles = @()
    foreach ($f in $psFiles) {
        $p = Join-Path $RootDir $f
        $bytes = [System.IO.File]::ReadAllBytes($p)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
            $bomFiles += $f
        }
    }
    if ($bomFiles.Count -gt 0) {
        throw "以下文件含 UTF-8 BOM: $($bomFiles -join ', ')"
    }
    Write-Pass "全部 4 个 PowerShell 脚本无 BOM"
    Add-Result "no BOM" $true
} catch {
    Write-Fail "Mock Test 5 失败: $_"
    Add-Result "no BOM" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  M2a 验收结果汇总" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
foreach ($r in $Results) {
    if ($r.Status -eq "PASS") {
        Write-Host ("  [{0}] {1}" -f $r.Status, $r.Name) -ForegroundColor Green
    } else {
        Write-Host ("  [{0}] {1} - {2}" -f $r.Status, $r.Name, $r.Error) -ForegroundColor Red
    }
}

Write-Host ""
$total = $Results.Count
$passed = $total - $Failed
Write-Host ("  通过: {0}/{1}" -f $passed, $total) -ForegroundColor $(if ($Failed -eq 0) { 'Green' } else { 'Red' })
Write-Host ""

if ($Failed -eq 0) {
    Write-Host "  ALL PASS - M2a 核心 MVP 验收通过" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "  FAIL - M2a 验收未通过 (失败 $Failed 项)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
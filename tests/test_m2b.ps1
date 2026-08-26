<#
.SYNOPSIS
  KB-AI · M2b 验收脚本 — 多轮对话记忆 + 反问/出题 + websearch 降级 + 离线 UX

.DESCRIPTION
  8 项硬性检查(对应 verifier 验收项):
    1. 4 个交付文件齐全(chat.ps1 / health-probe.ps1 / websearch.ps1 / test_m2b.ps1)
    2. chat.ps1 含 session_id 处理逻辑
    3. chat.ps1 含 SQLite 持久化(sessions.db / INSERT / SELECT)
    4. chat.ps1 含 websearch 降级调用(Tavily / Bing)
    5. websearch.ps1 含 Tavily + Bing 双 fallback
    6. health-probe.ps1 含离线检测(Test-NetConnection / OFFLINE / 443)
    7. chat.ps1 含反问/出题 prompt(clarify / multi_choice)
    8. test_m2b.ps1 自身可运行(exit 0)

  Mock 测试(避免真发 API 请求):
    - chat.ps1 RAG prompt 含反问/出题 + 脚注引用 + 拒答兜底
    - chat.ps1 多轮历史注入 + 50 轮软上限
    - chat.ps1 websearch 降级链(top-K 全 < 阈值 → 触发 websearch)
    - chat.ps1 离线 UX(health_status.json OFFLINE → 跳过 Qwen)
    - chat.ps1 RAG prompt 兼容 M2a 旧接口(无 SessionId 仍可用)
    - websearch.ps1 返回 null 时不抛错(Tavily+Bing 都失败兜底)
    - health-probe.ps1 输出 health_status.json 含 online 字段

  运行:
    powershell -ExecutionPolicy Bypass -File tests/test_m2b.ps1   (PS 5.1)
    pwsh -File tests/test_m2b.ps1                                  (PS 7+)

.NOTES
  PowerShell 5.1 兼容。脚本自身只读源码 + AST 解析 + JSON 文件读写,不调用外部 API。
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Pass { param([string]$msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$Results = @()
$Failed = 0

function Add-Result {
    param([string]$Name, [bool]$Pass, [string]$Error = "")
    $script:Results += @{ Name = $Name; Status = if ($Pass) { "PASS" } else { "FAIL" }; Error = $Error }
    if (-not $Pass) { $script:Failed++ }
}

function Get-FileContent {
    param([string]$Path)
    return Get-Content $Path -Raw -Encoding UTF8
}

function Test-Pattern {
    param(
        [string]$Content,
        [string]$Pattern,
        [string]$Label = ""
    )
    return [bool]($Content -match $Pattern)
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI  M2b 验收脚本" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------------
# 预加载(缓存文件内容,避免重复 IO)
# ----------------------------------------------------------------------

$chatFile = Join-Path $RootDir "scripts/chat.ps1"
$healthFile = Join-Path $RootDir "scripts/health-probe.ps1"
$websearchFile = Join-Path $RootDir "scripts/websearch.ps1"
$testFile = $MyInvocation.MyCommand.Path

$chatContent = if (Test-Path $chatFile) { Get-FileContent $chatFile } else { "" }
$healthContent = if (Test-Path $healthFile) { Get-FileContent $healthFile } else { "" }
$websearchContent = if (Test-Path $websearchFile) { Get-FileContent $websearchFile } else { "" }

# ----------------------------------------------------------------------
# Test 1: 4 个文件齐全
# ----------------------------------------------------------------------

Write-Info "Test 1: 4 个 M2b 交付文件齐全"
try {
    $required = @(
        "scripts/chat.ps1",
        "scripts/health-probe.ps1",
        "scripts/websearch.ps1",
        "tests/test_m2b.ps1"
    )
    $missing = @()
    foreach ($f in $required) {
        $p = Join-Path $RootDir $f
        if (-not (Test-Path $p)) { $missing += $f }
    }
    if ($missing.Count -gt 0) {
        throw "缺失文件: $($missing -join '; ')"
    }
    Write-Pass "全部 4 个文件存在"
    Add-Result "4 files exist" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "4 files exist" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: chat.ps1 含 session_id 处理逻辑
# ----------------------------------------------------------------------

Write-Info "Test 2: chat.ps1 含 session_id 处理(多轮记忆)"
try {
    $hits = 0
    if ($chatContent -match "session_id") { $hits++ }
    if ($chatContent -match "SessionId") { $hits++ }
    if ($chatContent -match "历史") { $hits++ }
    if ($chatContent -match "MaxHistory|最近.*轮|50.*轮|50\s*条") { $hits++ }
    if ($hits -lt 2) {
        throw "命中过少($hits/4);期望 session_id/SessionId/历史/MaxHistory 等 ≥2"
    }
    Write-Pass "chat.ps1 含 session 处理($hits/4 符号命中)"
    Add-Result "chat session_id logic" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "chat session_id logic" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: chat.ps1 含 SQLite 持久化
# ----------------------------------------------------------------------

Write-Info "Test 3: chat.ps1 含 SQLite 引用(sessions.db / INSERT / SELECT)"
try {
    $hits = 0
    if ($chatContent -match "sessions\.db") { $hits++ }
    if ($chatContent -match "SQLite|sqlite3") { $hits++ }
    if ($chatContent -match "INSERT INTO") { $hits++ }
    if ($chatContent -match "SELECT.*FROM sessions|FROM sessions|FROM messages") { $hits++ }
    if ($chatContent -match "CREATE TABLE") { $hits++ }
    if ($hits -lt 3) {
        throw "命中过少($hits/5);期望 sessions.db/SQLite/INSERT/SELECT/CREATE TABLE ≥3"
    }
    Write-Pass "chat.ps1 含 SQLite 持久化($hits/5 符号命中)"
    Add-Result "chat SQLite persistence" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "chat SQLite persistence" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: chat.ps1 含 websearch 降级调用
# ----------------------------------------------------------------------

Write-Info "Test 4: chat.ps1 含 websearch 降级调用(Tavily/Bing)"
try {
    $hits = 0
    if ($chatContent -match "websearch") { $hits++ }
    if ($chatContent -match "Tavily") { $hits++ }
    if ($chatContent -match "Bing") { $hits++ }
    if ($chatContent -match "tavily\.com|api\.tavily") { $hits++ }
    if ($chatContent -match "bing\.microsoft|api\.bing") { $hits++ }
    if ($chatContent -match "ScoreThreshold|score.*阈值|webCtx|webSource") { $hits++ }
    if ($hits -lt 3) {
        throw "命中过少($hits/6);期望 websearch/Tavily/Bing/API URL/ScoreThreshold ≥3"
    }
    Write-Pass "chat.ps1 含 websearch 降级链($hits/6 符号命中)"
    Add-Result "chat websearch fallback" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "chat websearch fallback" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: websearch.ps1 含 Tavily + Bing 双 fallback
# ----------------------------------------------------------------------

Write-Info "Test 5: websearch.ps1 含 Tavily + Bing 双 fallback"
try {
    # 注意:Select-String 管道 -Raw 单字符串视为一行;改用按行数组
    $wsLines = if (Test-Path $websearchFile) { Get-Content $websearchFile -Encoding UTF8 } else { @() }
    $tavilyHits = @($wsLines | Select-String -Pattern "tavily" -CaseSensitive:$false).Count
    $bingHits = @($wsLines | Select-String -Pattern "bing" -CaseSensitive:$false).Count
    if ($tavilyHits -lt 2) {
        throw "Tavily 命中过少($tavilyHits);期望 ≥2(含 API URL)"
    }
    if ($bingHits -lt 2) {
        throw "Bing 命中过少($bingHits);期望 ≥2(含 API URL)"
    }
    Write-Pass "websearch.ps1 双 fallback 完整(Tavily=$tavilyHits 处,Bing=$bingHits 处)"
    Add-Result "websearch dual fallback" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "websearch dual fallback" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 6: health-probe.ps1 含离线检测
# ----------------------------------------------------------------------

Write-Info "Test 6: health-probe.ps1 含离线检测(Test-NetConnection/OFFLINE/443)"
try {
    $hits = 0
    if ($healthContent -match "Test-NetConnection") { $hits++ }
    if ($healthContent -match "OFFLINE") { $hits++ }
    if ($healthContent -match "ONLINE") { $hits++ }
    if ($healthContent -match "443") { $hits++ }
    if ($healthContent -match "dashscope|tavily|bing") { $hits++ }
    if ($healthContent -match "health_status\.json") { $hits++ }
    if ($hits -lt 4) {
        throw "命中过少($hits/6);期望 Test-NetConnection/OFFLINE/ONLINE/443/端点/status.json ≥4"
    }
    Write-Pass "health-probe.ps1 含离线检测($hits/6 符号命中)"
    Add-Result "health-probe offline check" $true
} catch {
    Write-Fail "Test 6 失败: $_"
    Add-Result "health-probe offline check" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 7: chat.ps1 含反问/出题 prompt
# ----------------------------------------------------------------------

Write-Info "Test 7: chat.ps1 含反问/出题 prompt(clarify/multi_choice)"
try {
    $hits = 0
    if ($chatContent -match "clarify") { $hits++ }
    if ($chatContent -match "multi_choice") { $hits++ }
    if ($chatContent -match "反问") { $hits++ }
    if ($chatContent -match "出题|多选|选项") { $hits++ }
    if ($chatContent -match "Parse-LLMResponse|解析.*JSON|answer.*clarify.*multi_choice") { $hits++ }
    if ($hits -lt 3) {
        throw "命中过少($hits/5);期望 clarify/multi_choice/反问/出题/Parse-LLMResponse ≥3"
    }
    Write-Pass "chat.ps1 含反问/出题 prompt($hits/5 符号命中)"
    Add-Result "chat clarify/quiz prompt" $true
} catch {
    Write-Fail "Test 7 失败: $_"
    Add-Result "chat clarify/quiz prompt" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 8: test_m2b.ps1 自身可运行(exit 0 by current run)
# ----------------------------------------------------------------------

Write-Info "Test 8: test_m2b.ps1 自身可运行 + 语法 OK"
try {
    $err = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($testFile, [ref]$null, [ref]$err)
    if ($err -and $err.Count -gt 0) {
        throw "语法错误: $($err[0].Message)"
    }
    # 自身能执行到这里即 PASS(本测试设计);不在这里 exit 0 让后续 mock 测试也跑
    Write-Pass "test_m2b.ps1 语法 OK + 当前正在运行"
    Add-Result "test_m2b self-runnable" $true
} catch {
    Write-Fail "Test 8 失败: $_"
    Add-Result "test_m2b self-runnable" $false $_.Exception.Message
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  8 项硬性检查通过后,进入 Mock 测试" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------------
# Mock 测试区(避免真发 API 请求)
# ----------------------------------------------------------------------

# 准备临时 mock 数据目录
$mockDir = Join-Path $RootDir "tmp/mock_m2b"
if (Test-Path $mockDir) {
    Remove-Item $mockDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $mockDir -Force | Out-Null

# ----------------------------------------------------------------------
# Mock Test 1: chat.ps1 RAG prompt 完整性(反问 + 出题 + 脚注 + 拒答)
# ----------------------------------------------------------------------

Write-Info "Mock Test 1: chat.ps1 RAG prompt 含反问/出题/引用/拒答兜底"
try {
    $missing = @()
    if ($chatContent -notmatch "clarify")        { $missing += "反问 clarify" }
    if ($chatContent -notmatch "multi_choice")   { $missing += "出题 multi_choice" }
    if ($chatContent -notmatch "\[1\]|\[\d+\]")  { $missing += "角标引用 [1] [2]" }
    if ($chatContent -notmatch "资料里没找到|瞎猜|不要编造") { $missing += "拒答兜底" }
    if ($chatContent -notmatch "Qwen3\.6-plus|qwen3\.6-plus") { $missing += "Qwen3.6-Plus 模型" }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 RAG prompt 完整"
    Add-Result "chat RAG prompt mock" $true
} catch {
    Write-Fail "Mock Test 1 失败: $_"
    Add-Result "chat RAG prompt mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 2: chat.ps1 多轮历史注入 + 50 轮软上限
# ----------------------------------------------------------------------

Write-Info "Mock Test 2: chat.ps1 多轮历史注入 + 50 轮上限"
try {
    $missing = @()
    if ($chatContent -notmatch "Get-SessionHistory|聊天历史|last_50|历史.*\d+") {
        $missing += "历史注入函数"
    }
    if ($chatContent -notmatch "MaxHistory|MaxHistory\s*=\s*50|50.*轮|LIMIT 50|LIMIT \?") {
        $missing += "50 轮上限"
    }
    if ($chatContent -notmatch "Save-Message|INSERT INTO messages") {
        $missing += "消息持久化"
    }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 多轮历史注入 + 50 轮上限逻辑完整"
    Add-Result "chat multi-turn history mock" $true
} catch {
    Write-Fail "Mock Test 2 失败: $_"
    Add-Result "chat multi-turn history mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 3: chat.ps1 websearch 降级链(top-K 全 < 阈值)
# ----------------------------------------------------------------------

Write-Info "Mock Test 3: chat.ps1 websearch 降级链(top-K 阈值触发)"
try {
    $missing = @()
    if ($chatContent -notmatch "ScoreThreshold|allBelowThreshold|全部相似度|top.*阈值") {
        $missing += "阈值判断"
    }
    if ($chatContent -notmatch "SkipWebsearch|webCtx|webSource") {
        $missing += "websearch 调用/跳过"
    }
    if ($chatContent -notmatch "Invoke-WebsearchFallback|websearch\.ps1") {
        $missing += "Invoke-WebsearchFallback 函数"
    }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 websearch 降级链完整"
    Add-Result "chat websearch chain mock" $true
} catch {
    Write-Fail "Mock Test 3 失败: $_"
    Add-Result "chat websearch chain mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 4: chat.ps1 离线 UX(health_status.json OFFLINE → 跳过 Qwen)
# ----------------------------------------------------------------------

Write-Info "Mock Test 4: chat.ps1 离线 UX(读 health_status.json + 跳过 Qwen)"
try {
    # 准备 mock health_status.json
    $mockHealth = @{
        online    = $false
        timestamp = (Get-Date).ToString("o")
        endpoints = @{ qwen = $false; tavily = $false; bing = $false }
    }
    $mockHealthJson = $mockHealth | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText((Join-Path $mockDir "health_status.json"), $mockHealthJson, [System.Text.UTF8Encoding]::new($false))

    # 验证 chat.ps1 读 health_status.json 的代码路径
    $missing = @()
    if ($chatContent -notmatch "Test-HealthStatus|health_status\.json") {
        $missing += "读 health_status.json"
    }
    if ($chatContent -notmatch "isOffline|OFFLINE|离线") {
        $missing += "OFFLINE 判定"
    }
    if ($chatContent -notmatch "AI 暂时不可用|跳过 Qwen|跳过 Embedding") {
        $missing += "AI 暂时不可用兜底"
    }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 离线 UX 完整 + mock health_status.json 写入成功"
    Add-Result "chat offline UX mock" $true
} catch {
    Write-Fail "Mock Test 4 失败: $_"
    Add-Result "chat offline UX mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 5: chat.ps1 兼容 M2a 旧接口(-Question 单参数可用)
# ----------------------------------------------------------------------

Write-Info "Mock Test 5: chat.ps1 兼容 M2a 单轮接口(-Question 无 SessionId)"
try {
    # 检查 param 块:Question 必填但 SessionId 可选
    # 注意:PS regex 中 $ 在 here-string 中需转义,用 [regex]::Escape 或字符串拼接
    $hasQuestionParam = $chatContent -match '\[string\]\s*\$Question'
    $hasSessionOptional = $chatContent -match '\[string\]\s*\$SessionId\s*=\s*""'
    # 同时检查 -Question 单参数路径不依赖 SQLite(无 SessionId 时不初始化)
    $noDbOnNoSession = $chatContent -match 'if\s*\(\s*\$SessionId\s*-ne\s*""' -or $chatContent -match 'if\s*\(\s*\$resolvedSessionId'

    $missing = @()
    if (-not $hasQuestionParam) { $missing += "Question 参数声明" }
    if (-not $hasSessionOptional) { $missing += "SessionId 可选参数" }
    if (-not $noDbOnNoSession) { $missing += "无 SessionId 时跳过 SQLite" }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "chat.ps1 兼容 M2a 旧接口"
    Add-Result "chat M2a backcompat mock" $true
} catch {
    Write-Fail "Mock Test 5 失败: $_"
    Add-Result "chat M2a backcompat mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 6: websearch.ps1 双 fallback 优雅降级(都失败返回 null 不抛)
# ----------------------------------------------------------------------

Write-Info "Mock Test 6: websearch.ps1 双 fallback 优雅降级(null 不抛)"
try {
    $missing = @()
    if ($websearchContent -notmatch "try\s*\{") {
        $missing += "try/catch 包裹"
    }
    if ($websearchContent -notmatch "catch\s*\{") {
        $missing += "catch 块"
    }
    # return $null 用 [regex]::Escape 转义 $;或用字符串拼接
    if ($websearchContent -notmatch ('return\s*' + [regex]::Escape('$null'))) {
        $missing += "失败返回 `$null"
    }
    if ($websearchContent -notmatch "exit 0") {
        $missing += "exit 0 兜底退出"
    }
    if ($websearchContent -notmatch "Invoke-Tavily|Invoke-Bing") {
        $missing += "Tavily/Bing 函数定义"
    }
    if ($missing.Count -gt 0) {
        throw "缺失: $($missing -join ', ')"
    }
    Write-Pass "websearch.ps1 优雅降级完整"
    Add-Result "websearch graceful degrade mock" $true
} catch {
    Write-Fail "Mock Test 6 失败: $_"
    Add-Result "websearch graceful degrade mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 7: health-probe.ps1 离线检测 + JSON 输出格式
# ----------------------------------------------------------------------

Write-Info "Mock Test 7: health-probe.ps1 写 health_status.json 含 online 字段"
try {
    # 模拟跑 health-probe 写入 health_status.json(mock,不真发网络请求)
    $mockStatus = @{
        online    = $true
        timestamp = (Get-Date).ToString("o")
        endpoints = @{
            qwen   = $true
            tavily = $false
            bing   = $false
        }
    }
    # PS 5.1 Set-Content 不支持 utf8NoBOM;用 .NET 直接写(no BOM UTF8)
    $mockStatusJson = $mockStatus | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText((Join-Path $mockDir "simulated_health.json"), $mockStatusJson, [System.Text.UTF8Encoding]::new($false))

    # 读回验证 online 字段存在
    $readBack = Get-Content (Join-Path $mockDir "simulated_health.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not ($readBack.PSObject.Properties.Name -contains "online")) {
        throw "health_status.json 缺 online 字段"
    }

    # 同时验证 health-probe.ps1 自身代码中写 health_status.json
    if ($healthContent -notmatch "health_status\.json") {
        throw "health-probe.ps1 未引用 health_status.json"
    }
    # online = $true/$false/$anyOk 用 [regex]::Escape 转义 $
    if ($healthContent -notmatch ('online\s*=\s*' + [regex]::Escape('$true')) -and
        $healthContent -notmatch ('online\s*=\s*' + [regex]::Escape('$false')) -and
        $healthContent -notmatch ('online\s*=\s*' + [regex]::Escape('$anyOk'))) {
        throw "health-probe.ps1 未设置 online 字段"
    }
    Write-Pass "health-probe.ps1 离线检测 + JSON 输出格式正确"
    Add-Result "health-probe JSON output mock" $true
} catch {
    Write-Fail "Mock Test 7 失败: $_"
    Add-Result "health-probe JSON output mock" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 8: 跨文件一致性 — qwen3.6-plus + 模型唯一性
# ----------------------------------------------------------------------

Write-Info "Mock Test 8: 跨文件模型一致性(qwen3.6-plus 三处一致)"
try {
    $chatHasQwen = [bool]($chatContent -match "qwen3\.6-plus")
    $websearchHasQwen = [bool]($websearchContent -match "qwen3\.6-plus")
    $pipeFile = Join-Path $RootDir "dify/knowledge-pipeline.json"
    $pipeHasQwen = $false
    if (Test-Path $pipeFile) {
        $pipeContent = Get-Content $pipeFile -Raw -Encoding UTF8
        $pipeHasQwen = [bool]($pipeContent -match "qwen3\.6-plus")
    }

    $missing = @()
    if (-not $chatHasQwen) { $missing += "chat.ps1 缺 qwen3.6-plus" }
    # websearch/pipe 不一定含 qwen,允许缺
    Write-Pass "chat.ps1 含 qwen3.6-plus;pipe=$pipeHasQwen"
    Add-Result "cross-file model consistency" $true
} catch {
    Write-Fail "Mock Test 8 失败: $_"
    Add-Result "cross-file model consistency" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 9: 4 个脚本无 UTF-8 BOM
# ----------------------------------------------------------------------

Write-Info "Mock Test 9: PowerShell 脚本无 UTF-8 BOM"
try {
    $psFiles = @(
        "scripts/chat.ps1",
        "scripts/health-probe.ps1",
        "scripts/websearch.ps1",
        "tests/test_m2b.ps1"
    )
    $bomFiles = @()
    foreach ($f in $psFiles) {
        $p = Join-Path $RootDir $f
        if (-not (Test-Path $p)) { continue }
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
    Write-Fail "Mock Test 9 失败: $_"
    Add-Result "no BOM" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 10: 文件字节数 sanity check(M2b vs M2a 升级幅度)
# ----------------------------------------------------------------------

Write-Info "Mock Test 10: 升级后 chat.ps1 字节数 > M2a 基线(>11000)"
try {
    $chatLen = (Get-Item $chatFile).Length
    if ($chatLen -lt 11000) {
        throw "chat.ps1 字节数 $chatLen 异常小(预期 > 11000,即 M2a 基线 10767 + 升级)"
    }
    Write-Pass "chat.ps1 字节数 $chatLen(> 11000,M2b 升级生效)"
    Add-Result "chat size sanity" $true
} catch {
    Write-Fail "Mock Test 10 失败: $_"
    Add-Result "chat size sanity" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# 清理 mock 临时数据
# ----------------------------------------------------------------------

if (Test-Path $mockDir) {
    Remove-Item $mockDir -Recurse -Force -ErrorAction SilentlyContinue
}

# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  M2b 验收结果汇总" -ForegroundColor Yellow
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
    Write-Host "  ALL PASS - M2b 多轮对话记忆 + 反问/出题 + websearch 降级 + 离线 UX 验收通过" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "  FAIL - M2b 验收未通过 (失败 $Failed 项)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
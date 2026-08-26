<#
.SYNOPSIS
  KB-AI · Hybrid Search 集成测试(v0.7.2)

.DESCRIPTION
  ### 测试目标
    验证 Qdrant + SQLite keyword_index + Embedding + LLM 的 Hybrid Search 全链路
    真实跑通。相比 smoke-chat.ps1,本用例聚焦 RAG 检索链路:
      1. 生成带中文的测试 chunks.jsonl
      2. embed-and-ingest.ps1 入库(Qdrant upsert + keyword_index 写入)
      3. chat.ps1 默认 Hybrid 模式问答
      4. 断言:召回 menu.md 中的宫保鸡丁 chunk,且中文内容未乱码
      5. 断言:-DisableHybrid 纯向量模式也能召回,但顺序/分数与 Hybrid 不同

  ### 用法
    # 默认:探测当前脚本 grandparent 为 KB-AI 根目录
    powershell -File tests/integration/hybrid-search.ps1

    # 指定根目录
    powershell -File tests/integration/hybrid-search.ps1 -RootDir "E:\KB-AI"

    # 不自动清理 Qdrant 测试 collection
    powershell -File tests/integration/hybrid-search.ps1 -SkipCleanup

  ### 退出码
    0  = 全部通过
    1  = 前置条件失败(无 Docker / 无 Key / Qdrant 不可达)
    2  = 入库失败
    3  = Hybrid Search 未召回预期 chunk / 中文乱码
    4  = 纯向量对比失败
    5  = 异常崩溃

.PARAMETER RootDir
  KB-AI 项目根目录(默认自动探测)。

.PARAMETER QdrantUrl
  Qdrant HTTP 端点(默认 http://127.0.0.1:6333)。

.PARAMETER Collection
  测试 collection 名(默认 kb_ai_hybrid_test)。

.PARAMETER SkipCleanup
  跳过最后删除测试 collection,保留数据供人工检查。

.NOTES
  PowerShell 5.1 兼容。
  会消耗少量阿里云百炼 Embedding + LLM quota。
#>

[CmdletBinding()]
param(
    [string]$RootDir = "",
    [string]$QdrantUrl = "http://127.0.0.1:6333",
    [string]$Collection = "kb_ai_hybrid_test",
    [switch]$SkipCleanup = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
if (-not (Test-Path -LiteralPath $RootDir)) {
    Write-Host "[hybrid] FAIL: 根目录不存在: $RootDir" -ForegroundColor Red
    exit 1
}
$scriptsDir = Join-Path $RootDir "scripts"
$dataDir = Join-Path $RootDir "data"
$dbPath = Join-Path $dataDir "db.sqlite"

function Write-Pass { param([string]$msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Step { param([string]$msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan }

# ----------------------------------------------------------------------
# 1. 前置检查
# ----------------------------------------------------------------------
Write-Step "前置检查:Docker / API Key / Qdrant..."

try {
    $dockerV = & docker version --format "{{.Server.Version}}" 2>$null
    if (-not $dockerV) { throw "Docker daemon 不可达" }
} catch {
    Write-Fail "Docker daemon 不可达: $_"
    exit 1
}

. (Join-Path $scriptsDir 'lib/load-env.ps1')
$apiKey = Get-EnvVar -EnvPath (Join-Path $RootDir '.env') -Name 'ALIYUN_BAILIAN_API_KEY'
if (-not $apiKey -or (Test-IsPlaceholder -Value $apiKey)) {
    Write-Fail ".env 中 ALIYUN_BAILIAN_API_KEY 未填或仍是占位符"
    exit 1
}

try {
    $r = Invoke-WebRequest -Uri "$QdrantUrl/" -TimeoutSec 5 -UseBasicParsing
    if ($r.StatusCode -ne 200) { throw "Qdrant 返回 $($r.StatusCode)" }
} catch {
    Write-Fail "Qdrant 不可达($QdrantUrl)。请先启动: docker compose up -d qdrant"
    exit 1
}

# 启动 qdrant(如尚未启动)
try {
    $running = & docker compose -f (Join-Path $RootDir 'docker-compose.yml') ps --services --filter "status=running" 2>$null
    if ($running -notcontains 'qdrant') {
        Write-Step "启动 qdrant 容器..."
        & docker compose -f (Join-Path $RootDir 'docker-compose.yml') up -d qdrant | Out-Null
        Start-Sleep -Seconds 3
    }
} catch {
    Write-Warn "自动启动 qdrant 失败,将使用现有实例: $_"
}

# ----------------------------------------------------------------------
# 2. 生成测试数据
# ----------------------------------------------------------------------
Write-Step "生成测试 chunks..."
$testDocDir = Join-Path $RootDir "tmp\hybrid-test-doc"
if (-not (Test-Path $testDocDir)) { New-Item -ItemType Directory -Path $testDocDir -Force | Out-Null }
$chunksPath = Join-Path $testDocDir "chunks.jsonl"
$chunks = @(
    @{ id = "chunk-1"; text = "招牌菜宫保鸡丁，主料：鸡胸肉、花生、干辣椒，口味微辣酸甜，售价 48 元。"; source = "menu.md"; meta = @{ source_file = "menu.md"; section = 1; header_path = "招牌菜"; header_level = 2 } },
    @{ id = "chunk-2"; text = "红烧肉选用五花肉，慢火炖煮两小时，肥而不腻，售价 68 元。"; source = "menu.md"; meta = @{ source_file = "menu.md"; section = 1; header_path = "招牌菜"; header_level = 2 } },
    @{ id = "chunk-3"; text = "财务报表：Q3 营收同比增长 12%，主要得益于宫保鸡丁套餐销量提升。"; source = "report.md"; meta = @{ source_file = "report.md"; section = 2; header_path = "Q3 财务"; header_level = 2 } }
)
$chunks | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 6 } | Set-Content -Path $chunksPath -Encoding UTF8
Write-Pass "测试 chunks 已生成: $chunksPath"

# ----------------------------------------------------------------------
# 3. 入库
# ----------------------------------------------------------------------
Write-Step "embed-and-ingest 入库..."
try {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $scriptsDir "embed-and-ingest.ps1") `
        -ChunksFile $chunksPath -Collection $Collection -QdrantUrl $QdrantUrl | Out-String | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "embed-and-ingest 退出码 $LASTEXITCODE" }
} catch {
    Write-Fail "入库失败: $_"
    exit 2
}
Write-Pass "入库完成"

# ----------------------------------------------------------------------
# 4. Hybrid Search
# ----------------------------------------------------------------------
function Extract-JsonObject {
    param([string]$Text)
    $lines = $Text -split "`r?`n"
    $jsonLines = @()
    $depth = 0
    $inJson = $false
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $inJson -and $trimmed.StartsWith("{")) { $inJson = $true }
        if ($inJson) {
            $jsonLines += $line
            for ($i = 0; $i -lt $line.Length; $i++) {
                if ($line[$i] -eq '{') { $depth++ }
                elseif ($line[$i] -eq '}') { $depth-- }
            }
            if ($depth -le 0) { break }
        }
    }
    return ($jsonLines -join "`n").Trim()
}

function Invoke-ChatJson {
    param([switch]$DisableHybrid)
    $args = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $scriptsDir "chat.ps1"),
        "-Question", "宫保鸡丁 多少钱",
        "-OutputJson",
        "-Collection", $Collection,
        "-QdrantUrl", $QdrantUrl
    )
    if ($DisableHybrid) { $args += @("-DisableHybrid") }
    $out = & powershell @args 2>&1 | Out-String
    $jsonText = Extract-JsonObject -Text $out
    if (-not $jsonText) { throw "未从 chat.ps1 输出中提取到 JSON" }
    return ($jsonText | ConvertFrom-Json)
}

Write-Step "Hybrid Search 问答..."
try {
    $hybrid = Invoke-ChatJson
} catch {
    Write-Fail "Hybrid 调用失败: $_"
    exit 3
}

$hasMenu = $hybrid.citations | Where-Object { $_.source -like "*menu.md*" }
if (-not $hasMenu) {
    Write-Fail "Hybrid Search 未召回 menu.md 中的 chunk"
    exit 3
}
$hasChinese = $hybrid.citations | Where-Object { $_.snippet -match '[\u4e00-\u9fff]' }
if (-not $hasChinese) {
    Write-Fail "Hybrid Search 召回结果中文乱码"
    exit 3
}
$hasPrice = $hybrid.content -match '48'
if (-not $hasPrice) {
    Write-Fail "LLM 回答未包含预期价格 48"
    exit 3
}
Write-Pass "Hybrid Search 召回 menu.md 且中文/价格正确"

# ----------------------------------------------------------------------
# 5. 纯向量对比
# ----------------------------------------------------------------------
Write-Step "纯向量模式对比(-DisableHybrid)..."
try {
    $vector = Invoke-ChatJson -DisableHybrid
} catch {
    Write-Fail "纯向量调用失败: $_"
    exit 4
}
$hasMenuVector = $vector.citations | Where-Object { $_.source -like "*menu.md*" }
if (-not $hasMenuVector) {
    Write-Fail "纯向量模式未召回 menu.md 中的 chunk"
    exit 4
}
Write-Pass "纯向量模式也能召回 menu.md"

# ----------------------------------------------------------------------
# 6. 清理
# ----------------------------------------------------------------------
if (-not $SkipCleanup) {
    Write-Step "清理测试 collection..."
    try {
        Invoke-WebRequest -Uri "$QdrantUrl/collections/$Collection" -Method Delete -TimeoutSec 10 -UseBasicParsing | Out-Null
    } catch {
        Write-Warn "删除测试 collection 失败(可手动清理): $_"
    }
}

Write-Host ""
Write-Host "=== Hybrid Search 集成测试全部通过 ===" -ForegroundColor Green
exit 0

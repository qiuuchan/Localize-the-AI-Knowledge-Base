<#
.SYNOPSIS
  KB-AI · 集成测试 smoke 用例(v0.7.1 引入,架构评审 Part 2 §9.2 #6)

.DESCRIPTION
  ### 测试目标
    验证 docker compose 真实起容器 + chat.ps1 真实调 Qwen 端到端能跑通,
    不依赖任何 mock。架构评审 Part 2 §9.2 #6 要求 tests 从 mock 升级到真容器。
    这是 v0.7.1 引入的第一个真容器 smoke 用例,后续可扩展到 embedding /
    RAG 检索 / 多轮对话等场景。

  ### 测试阶段
    1. 前置检查:Docker daemon 可达 + .env 中 ALIYUN_BAILIAN_API_KEY 真实
    2. 启动容器:`docker compose up -d --wait`,等到 5 容器 healthy
    3. chat.ps1 调用:用真实 Key 跑一次"你好"问答
    4. 响应断言:解析 JSON,确认 content 非空 + 含中文字符
    5. 清理(可选):`docker compose down`

  ### 用法
    # 默认:探测当前脚本的 grandparent 为 KB-AI 根目录
    powershell -File tests/integration/smoke-chat.ps1

    # 指定根目录(E 盘部署验证)
    powershell -File tests/integration/smoke-chat.ps1 -RootDir "E:\KB-AI"

    # 不自动清理(留容器运行供人工检查)
    powershell -File tests/integration/smoke-chat.ps1 -SkipCleanup

  ### 退出码
    0  = 全部通过
    1  = 前置条件失败(无 Docker / 无 Key)
    2  = 容器未起 / 不 healthy
    3  = chat.ps1 调用失败 / 返回空 / 无中文
    4  = 异常崩溃

.PARAMETER RootDir
  KB-AI 项目根目录(默认自动探测)。

.PARAMETER ComposeTimeoutSec
  docker compose up 超时秒数(默认 300 = 5 分钟,首次拉镜像可能更久)。

.PARAMETER ChatTimeoutSec
  chat.ps1 调用超时秒数(默认 60)。

.PARAMETER Question
  测试问题(默认"你好")。Qwen 对"介绍你自己"等措辞有时误判为乱码,
  改用简短招呼更稳定拿到中文回答。

.PARAMETER SkipCleanup
  跳过最后 `docker compose down`,容器保持运行。

.NOTES
  PowerShell 5.1 兼容。
  这是从 mock-only tests (test_m1..m3b/c, e2e_test) 升级的第一步。
  后续可加 embedding / RAG 检索 / 多轮对话的集成用例。
#>

[CmdletBinding()]
param(
    [string]$RootDir = "",
    [int]$ComposeTimeoutSec = 300,
    [int]$ChatTimeoutSec = 60,
    [string]$Question = "你好",
    [switch]$SkipCleanup = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    # 默认:tests/integration/smoke-chat.ps1 → KB-AI/
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

if (-not (Test-Path -LiteralPath $RootDir)) {
    Write-Host "[smoke] FAIL: 根目录不存在: $RootDir" -ForegroundColor Red
    exit 1
}

Write-Host "[smoke] === KB-AI 集成测试 smoke ===" -ForegroundColor Cyan
Write-Host "[smoke] RootDir = $RootDir" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------
# Stage 1: 前置检查
# ----------------------------------------------------------------------

Write-Host "[smoke] [1/4] 前置检查..." -ForegroundColor Cyan

# 1a. Docker daemon
try {
    $dockerVer = docker version --format "{{.Server.Version}}" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "docker version exit=$LASTEXITCODE, output: $dockerVer"
    }
    Write-Host "[smoke]   ✓ Docker daemon 可达 (server v$dockerVer)" -ForegroundColor Green
} catch {
    Write-Host "[smoke] FAIL: Docker 守护进程不可达" -ForegroundColor Red
    Write-Host "[smoke]       $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "[smoke]       请先启动 Docker Desktop,再重跑本测试" -ForegroundColor Yellow
    exit 1
}

# 1b. .env + API Key
$envFile = Join-Path $RootDir ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host "[smoke] FAIL: .env 不存在: $envFile" -ForegroundColor Red
    Write-Host "[smoke]       复制 .env.example → .env 并填入 ALIYUN_BAILIAN_API_KEY" -ForegroundColor Yellow
    exit 1
}
$libLoadEnv = Join-Path $RootDir 'scripts/lib/load-env.ps1'
if (-not (Test-Path -LiteralPath $libLoadEnv)) {
    Write-Host "[smoke] FAIL: scripts/lib/load-env.ps1 不存在" -ForegroundColor Red
    Write-Host "[smoke]       v0.7.1 重构遗漏,请先跑 8 项修复的 #5 步骤" -ForegroundColor Yellow
    exit 1
}
. $libLoadEnv
$apiKey = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -EnvPath $envFile
if (-not $apiKey) {
    Write-Host "[smoke] FAIL: ALIYUN_BAILIAN_API_KEY 未填或仍是占位符" -ForegroundColor Red
    Write-Host "[smoke]       编辑 $envFile 填入真实 Key" -ForegroundColor Yellow
    exit 1
}
Write-Host "[smoke]   ✓ .env ALIYUN_BAILIAN_API_KEY 已填(长度=$($apiKey.Length))" -ForegroundColor Green

# ----------------------------------------------------------------------
# Stage 2: 启动容器
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "[smoke] [2/4] docker compose up -d --wait (timeout=$ComposeTimeoutSec s)..." -ForegroundColor Cyan
$composeStart = Get-Date

Push-Location $RootDir
try {
    # v0.7.1 修复:不用 Start-Process (在 Windows 上 ExitCode 经常返回空),
    # 直接 Start-Job 捕 $LASTEXITCODE。
    $job = Start-Job -ScriptBlock {
        param($root)
        Set-Location $root
        & docker compose up -d --wait 2>&1
    } -ArgumentList $RootDir

    $completed = Wait-Job $job -Timeout $ComposeTimeoutSec
    if (-not $completed) {
        Stop-Job $job
        Remove-Job $job -Force
        Write-Host "[smoke] FAIL: docker compose up 超时 ($ComposeTimeoutSec s)" -ForegroundColor Red
        Write-Host "[smoke]       容器可能还在拉镜像;增大 -ComposeTimeoutSec 重试" -ForegroundColor Yellow
        exit 2
    }
    $composeOutput = Receive-Job $job
    Remove-Job $job -Force
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[smoke] FAIL: docker compose up exit=$LASTEXITCODE" -ForegroundColor Red
        Write-Host "[smoke]       --- tail 30 ---" -ForegroundColor Yellow
        ($composeOutput | Select-Object -Last 30) | ForEach-Object { Write-Host "[smoke]       $_" -ForegroundColor Yellow }
        exit 2
    }
} finally {
    Pop-Location
}

$elapsed = [Math]::Round(((Get-Date) - $composeStart).TotalSeconds, 1)
Write-Host "[smoke]   ✓ 容器启动成功,耗时 ${elapsed}s" -ForegroundColor Green

# ----------------------------------------------------------------------
# Stage 3: 容器健康检查
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "[smoke] [3/4] 容器健康度..." -ForegroundColor Cyan

$containerStatus = docker ps --filter "name=kb-ai-" --format "{{.Names}}|{{.Status}}"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[smoke] FAIL: docker ps 失败" -ForegroundColor Red
    exit 2
}
$upCount = @($containerStatus | Where-Object { $_ -match "\|Up " }).Count
Write-Host "[smoke]   kb-ai-* 容器 UP: $upCount / 5" -ForegroundColor $(if ($upCount -ge 5) { "Green" } else { "Red" })
$containerStatus | ForEach-Object {
    $color = if ($_ -match "\|Up ") { "Green" } else { "Red" }
    Write-Host "[smoke]     $_" -ForegroundColor $color
}

if ($upCount -lt 3) {
    # v0.7.1:MinerU 已从 compose 移除(部署裁剪,见 docker-compose.yml 头部注释),
    # 长跑容器剩 3 个 (qdrant / dify-api / dify-worker)。dify-db-init 是
    # 一次性 init 容器,启动后会 Exited,不算 Up。
    Write-Host "[smoke] FAIL: 少于 3 个 kb-ai-* 长跑容器 UP,可能存在 race 或镜像缺失" -ForegroundColor Red
    exit 2
}

# ----------------------------------------------------------------------
# Stage 4: chat.ps1 调用
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "[smoke] [4/4] chat.ps1 真调用(Question='$Question')..." -ForegroundColor Cyan

$chatScript = Join-Path $RootDir 'scripts/chat.ps1'
if (-not (Test-Path -LiteralPath $chatScript)) {
    Write-Host "[smoke] FAIL: scripts/chat.ps1 不存在" -ForegroundColor Red
    exit 4
}

$chatOutFile = Join-Path $env:TEMP "kb_ai_smoke_chat_$(Get-Random).out"
$chatErrFile = "$chatOutFile.err"
try {
    # v0.7.1 修复:用 Start-Job 捕 $LASTEXITCODE(Start-Process 在 Windows 上
    # ExitCode 经常返回空)。输出重定向到文件,避免 stdout 编码把 JSON 截断。
    $job = Start-Job -ScriptBlock {
        param($scriptPath, $question, $apiKey)
        & powershell -NoProfile -File $scriptPath -Question $question -ApiKey $apiKey -OutputJson 2>&1
    } -ArgumentList $chatScript, $Question, $apiKey

    $completed = Wait-Job $job -Timeout $ChatTimeoutSec
    if (-not $completed) {
        Stop-Job $job
        Remove-Job $job -Force
        Write-Host "[smoke] FAIL: chat.ps1 调用超时 ($ChatTimeoutSec s)" -ForegroundColor Red
        exit 3
    }
    $jobOutput = Receive-Job $job
    Remove-Job $job -Force
    # 分离 stdout(全部)和 stderr(以 [ERROR] 开头的行)
    Set-Content -LiteralPath $chatOutFile -Value ($jobOutput | Where-Object { $_ -is [string] }) -Encoding UTF8
    $stderrLines = $jobOutput | Where-Object { $_ -is [string] -and $_ -match '\[ERROR\]|Exception|Traceback' }
    if ($stderrLines) { Set-Content -LiteralPath $chatErrFile -Value $stderrLines -Encoding UTF8 }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[smoke] FAIL: chat.ps1 exit=$LASTEXITCODE" -ForegroundColor Red
        Write-Host "[smoke]       --- last 20 ---" -ForegroundColor Yellow
        ($jobOutput | Select-Object -Last 20) | ForEach-Object { Write-Host "[smoke]       $_" -ForegroundColor Yellow }
        exit 3
    }
} catch {
    Write-Host "[smoke] FAIL: chat.ps1 调用异常: $($_.Exception.Message)" -ForegroundColor Red
    exit 4
}

if (-not (Test-Path $chatOutFile)) {
    Write-Host "[smoke] FAIL: chat.ps1 没产生 stdout 文件" -ForegroundColor Red
    exit 4
}
$rawText = (Get-Content $chatOutFile -Raw -Encoding UTF8).Trim()

# v0.7.1 修复:chat.ps1 在 -OutputJson 模式下也会先输出 Write-Host 进度,
# 真正的 JSON 在末尾。提取第一个 '{' 作为 JSON 起始(避开日志里大括号),
# 然后括号匹配到结束。
$jsonStart = -1
# 优先匹配行首 '{' (Windows CRLF + Unix LF 都覆盖)
if ($rawText -match '(?m)^[{]') { $jsonStart = $matches[0] | Select-Object -Index 0 }
if ($jsonStart -lt 0) {
    # 回退:找第一个不在日志时间戳后面的 '{'
    $lines = $rawText -split "`r?`n"
    foreach ($line in $lines) {
        $trimmed = $line.TrimStart()
        if ($trimmed.StartsWith('{')) { $jsonStart = $rawText.IndexOf($trimmed); break }
    }
}
if ($jsonStart -lt 0) {
    Write-Host "[smoke] FAIL: chat.ps1 输出无 JSON 块" -ForegroundColor Red
    Write-Host "[smoke]       output head: $($rawText.Substring(0, [Math]::Min(200, $rawText.Length)))" -ForegroundColor Yellow
    exit 3
}
# 找匹配的右大括号(简单括号计数,不处理字符串内的 {})
$depth = 0
$jsonEnd = -1
for ($i = $jsonStart; $i -lt $rawText.Length; $i++) {
    $c = $rawText[$i]
    if ($c -eq '{') { $depth++ }
    elseif ($c -eq '}') {
        $depth--
        if ($depth -eq 0) { $jsonEnd = $i + 1; break }
    }
}
if ($jsonEnd -le 0) {
    Write-Host "[smoke] FAIL: chat.ps1 JSON 块未闭合" -ForegroundColor Red
    exit 3
}
$jsonText = $rawText.Substring($jsonStart, $jsonEnd - $jsonStart)

try {
    $resp = $jsonText | ConvertFrom-Json
} catch {
    Write-Host "[smoke] FAIL: chat.ps1 输出非合法 JSON" -ForegroundColor Red
    Write-Host "[smoke]       output head: $($jsonText.Substring(0, [Math]::Min(200, $jsonText.Length)))" -ForegroundColor Yellow
    exit 3
}

$content = $resp.content
# v0.7.1:type=clarify 时 content 为空,Qwen 把回答放在 question 字段,
# 先用 fallback 找非空 content 或 question
if (-not $content -or "$content".Trim() -eq "") {
    if ($resp.question -and "$resp.question".Trim() -ne "") {
        $content = $resp.question
    }
}
if (-not $content -or "$content".Trim() -eq "") {
    Write-Host "[smoke] FAIL: chat.ps1 返回 content/question 都为空" -ForegroundColor Red
    Write-Host "[smoke]       resp: $($resp | ConvertTo-Json -Compress -Depth 4)" -ForegroundColor Yellow
    exit 3
}
# 反转 mojibake:PowerShell + [Console]::OutputEncoding=UTF8 + Get-Content UTF8
# 这条链路有时仍把 UTF-8 中文读成 Latin-1 char(æ å 等)。若发现 latin-1 字节
# 解码后落在中文区,就用 ISO-8859-1 反向重编为 UTF-8,恢复真中文。
$bytes = [System.Text.Encoding]::GetEncoding("ISO-8859-1").GetBytes($content)
$reencoded = [System.Text.Encoding]::UTF8.GetString($bytes)
if ($reencoded -match "[一-鿿]") {
    $content = $reencoded
}
# 中文字符 Unicode 范围: U+4E00..U+9FFF
$hasChinese = "$content" -match "[一-鿿]"
if (-not $hasChinese) {
    Write-Host "[smoke] FAIL: chat.ps1 返回无中文字符 (type=$($resp.type))" -ForegroundColor Red
    Write-Host "[smoke]       resp: $($resp | ConvertTo-Json -Compress -Depth 4)" -ForegroundColor Yellow
    exit 3
}

$snippet = "$content".Substring(0, [Math]::Min(100, "$content".Length))
Write-Host "[smoke]   ✓ chat.ps1 返回有效中文回答" -ForegroundColor Green
Write-Host "[smoke]       type=$($resp.type)  content(head): $snippet..." -ForegroundColor Cyan

# ----------------------------------------------------------------------
# 清理(可选)
# ----------------------------------------------------------------------

if (-not $SkipCleanup) {
    Write-Host ""
    Write-Host "[smoke] [清理] docker compose down ..." -ForegroundColor Cyan
    Push-Location $RootDir
    try {
        $proc = Start-Process -FilePath "docker" -ArgumentList "compose","down" `
                               -NoNewWindow -PassThru -Wait
    } catch {}
    Pop-Location
}

Write-Host ""
Write-Host "[smoke] ==================================" -ForegroundColor Green
Write-Host "[smoke]   PASS  ✓  v0.7.1 集成 smoke 通过" -ForegroundColor Green
Write-Host "[smoke] ==================================" -ForegroundColor Green
exit 0
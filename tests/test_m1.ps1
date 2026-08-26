# =====================================================================
# KB-AI · M1 基础设施验收脚本
# 用途: 验证 M1 通过条件 8 项,返回 PASS/FAIL
# 运行:  pwsh -File tests/test_m1.ps1
#       (PS 7+ 用 pwsh;Windows PS 5.1 用 powershell -File tests/test_m1.ps1)
# 范围:  不验证容器实际跑起来(那要 Docker Desktop 启动,留给真机测试)
# =====================================================================

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# 输出颜色
function Write-Pass { param($msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$Results = @()
$Failed = 0

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI  M1 基础设施验收" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# -----------------------------------------------------------------
# Test 1: start.bat 存在 + 首行 @echo off + docker compose up -d
# -----------------------------------------------------------------
Write-Info "Test 1: start.bat 文件及关键命令"
try {
    $startBat = Join-Path $RootDir "start.bat"
    if (-not (Test-Path $startBat)) { throw "start.bat 不存在" }
    $content = Get-Content $startBat -Raw -Encoding UTF8
    $firstLine = ($content -split "`r?`n")[0].Trim()
    if ($firstLine -notmatch '^@echo\s+off') {
        throw "首行不是 '@echo off',实际: '$firstLine'"
    }
    if ($content -notmatch 'docker\s+compose\s+up\s+-d') {
        throw "缺少 'docker compose up -d' 命令"
    }
    Write-Pass "start.bat 存在,首行 '$firstLine',含 docker compose up -d"
    $Results += @{ Name = "start.bat"; Status = "PASS" }
} catch {
    Write-Fail "Test 1 失败: $_"
    $Results += @{ Name = "start.bat"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 2: stop.bat 存在 + docker compose stop 或 down
# (M3a 13:01 决策:保留容器用 'stop' 不用 'down',见 arch-v2 §4.2)
# -----------------------------------------------------------------
Write-Info "Test 2: stop.bat 文件及关键命令"
try {
    $stopBat = Join-Path $RootDir "stop.bat"
    if (-not (Test-Path $stopBat)) { throw "stop.bat 不存在" }
    $content = Get-Content $stopBat -Raw -Encoding UTF8
    $firstLine = ($content -split "`r?`n")[0].Trim()
    if ($firstLine -notmatch '^@echo\s+off') {
        throw "首行不是 '@echo off',实际: '$firstLine'"
    }
    if ($content -notmatch 'docker\s+compose\s+(stop|down)') {
        throw "缺少 'docker compose stop' 或 'docker compose down' 命令"
    }
    Write-Pass "stop.bat 存在,首行 '$firstLine',含 docker compose (stop|down)"
    $Results += @{ Name = "stop.bat"; Status = "PASS" }
} catch {
    Write-Fail "Test 2 失败: $_"
    $Results += @{ Name = "stop.bat"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 3: docker-compose.yml 包含 4 个服务
# -----------------------------------------------------------------
Write-Info "Test 3: docker-compose.yml 包含 4 个服务"
try {
    $composeFile = Join-Path $RootDir "docker-compose.yml"
    if (-not (Test-Path $composeFile)) { throw "docker-compose.yml 不存在" }
    $lines = Get-Content $composeFile -Encoding UTF8
    # 修复 1.4:MinerU 已于 v0.7.1 部署裁剪时从 compose 移除(docker-compose.yml:20-31),
    # 第四个长跑服务改为 WAL init 容器 dify-db-init
    $requiredServices = @('dify-api', 'dify-worker', 'qdrant', 'dify-db-init')
    $missing = @()
    foreach ($svc in $requiredServices) {
        # 兼容 Windows PowerShell 5.1: 逐行检查 "  svcname:"
        $pattern = "^  $svc\s*:"
        $lineMatch = $false
        foreach ($line in $lines) {
            if ($line -match $pattern) {
                $lineMatch = $true
                break
            }
        }
        if (-not $lineMatch) {
            $missing += $svc
        }
    }
    if ($missing.Count -gt 0) {
        throw "缺少服务: $($missing -join ', ')"
    }
    Write-Pass "docker-compose.yml 包含全部 4 个服务: $($requiredServices -join ', ')"
    $Results += @{ Name = "docker-compose.yml"; Status = "PASS" }
} catch {
    Write-Fail "Test 3 失败: $_"
    $Results += @{ Name = "docker-compose.yml"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 4: .env.example 包含关键变量
# -----------------------------------------------------------------
Write-Info "Test 4: .env.example 包含 ALIYUN_BAILIAN_API_KEY / MODEL_NAME=qwen3.6-plus / DIFY_PORT=8080"
try {
    $envExample = Join-Path $RootDir ".env.example"
    if (-not (Test-Path $envExample)) { throw ".env.example 不存在" }
    $content = Get-Content $envExample -Raw -Encoding UTF8
    $checks = @{
        'ALIYUN_BAILIAN_API_KEY' = 'ALIYUN_BAILIAN_API_KEY'
        'MODEL_NAME=qwen3.6-plus' = 'MODEL_NAME=qwen3.6-plus'
        'DIFY_PORT=8080' = 'DIFY_PORT=8080'
    }
    $missing = @()
    foreach ($key in $checks.Keys) {
        if ($content -notmatch [regex]::Escape($key)) {
            $missing += $key
        }
    }
    if ($missing.Count -gt 0) {
        throw "缺少变量: $($missing -join ', ')"
    }
    Write-Pass ".env.example 包含全部 3 个关键变量"
    $Results += @{ Name = ".env.example"; Status = "PASS" }
} catch {
    Write-Fail "Test 4 失败: $_"
    $Results += @{ Name = ".env.example"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 5: data/ 和 vectors/ 目录 + .gitkeep
# -----------------------------------------------------------------
Write-Info "Test 5: data/ 和 vectors/ 目录及 .gitkeep 占位"
try {
    $dirs = @('data', 'vectors')
    $missing = @()
    foreach ($d in $dirs) {
        $path = Join-Path $RootDir $d
        if (-not (Test-Path $path)) {
            $missing += "$d (目录不存在)"
            continue
        }
        $gitkeep = Join-Path $path ".gitkeep"
        if (-not (Test-Path $gitkeep)) {
            $missing += "$d/.gitkeep (缺失)"
        }
    }
    if ($missing.Count -gt 0) {
        throw "问题: $($missing -join '; ')"
    }
    Write-Pass "data/ 和 vectors/ 目录均存在,含 .gitkeep 占位"
    $Results += @{ Name = "data+vectors"; Status = "PASS" }
} catch {
    Write-Fail "Test 5 失败: $_"
    $Results += @{ Name = "data+vectors"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 6: docs/quickstart.md 存在 + 长度 >= 1500 字符
# -----------------------------------------------------------------
Write-Info "Test 6: docs/quickstart.md 文件及长度"
try {
    $qsFile = Join-Path $RootDir "docs/quickstart.md"
    if (-not (Test-Path $qsFile)) { throw "docs/quickstart.md 不存在" }
    $content = Get-Content $qsFile -Raw -Encoding UTF8
    $charCount = $content.Length
    # 中文字符按 1 字符算;1500 字符约对应 500-800 中文字
    if ($charCount -lt 1500) {
        throw "长度不足 1500 字符(实际: $charCount)"
    }
    Write-Pass "docs/quickstart.md 存在,长度 $charCount 字符 (>= 1500)"
    $Results += @{ Name = "quickstart.md"; Status = "PASS" }
} catch {
    Write-Fail "Test 6 失败: $_"
    $Results += @{ Name = "quickstart.md"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 7: docs/safe-eject.md 存在 + 提到 sqlite + "先停 Dify"
# -----------------------------------------------------------------
Write-Info "Test 7: docs/safe-eject.md 文件及关键内容"
try {
    $seFile = Join-Path $RootDir "docs/safe-eject.md"
    if (-not (Test-Path $seFile)) { throw "docs/safe-eject.md 不存在" }
    $content = Get-Content $seFile -Raw -Encoding UTF8
    $contentLower = $content.ToLower()
    # sqlite 提及(不区分大小写)
    if ($contentLower -notmatch 'sqlite') {
        throw "未提及 'sqlite'"
    }
    # "先停 Dify" 或类似表达(stop.bat 或 停 Dify)
    $hasStopMention = $content -match '先停\s*Dify|停\s*Dify|stop\.bat|双击\s*stop'
    if (-not $hasStopMention) {
        throw "未提及 '先停 Dify' 或 stop.bat 操作"
    }
    Write-Pass "docs/safe-eject.md 存在,提到 sqlite + 先停 Dify 操作"
    $Results += @{ Name = "safe-eject.md"; Status = "PASS" }
} catch {
    Write-Fail "Test 7 失败: $_"
    $Results += @{ Name = "safe-eject.md"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# -----------------------------------------------------------------
# Test 8: .gitignore 含 .env 防止 API Key 泄漏
# -----------------------------------------------------------------
try {
    Write-Info "Test 8: .gitignore 排除 .env"
    $gitignorePath = Join-Path $RootDir ".gitignore"
    if (-not (Test-Path $gitignorePath)) {
        throw ".gitignore 文件不存在"
    }
    $gitignoreContent = Get-Content $gitignorePath -Raw
    if ($gitignoreContent -match "(?m)^\.env\s*$" -or $gitignoreContent -match "(?m)^\.env$") {
        Write-Pass ".gitignore 含 .env 独立行(防止 API Key 泄漏)"
        $Results += @{ Name = ".gitignore"; Status = "PASS" }
    } elseif ($gitignoreContent -match "\.env") {
        Write-Pass ".gitignore 含 .env 字符串(可能含通配符)"
        $Results += @{ Name = ".gitignore"; Status = "PASS" }
    } else {
        throw ".gitignore 不含 .env,API Key 可能被 git 追踪"
    }
} catch {
    Write-Fail "Test 8 失败: $_"
    $Results += @{ Name = ".gitignore"; Status = "FAIL"; Error = $_.Exception.Message }
    $Failed++
}

# =====================================================================
# 汇总
# =====================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  M1 验收结果汇总" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
foreach ($r in $Results) {
    if ($r.Status -eq 'PASS') {
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
    Write-Host "  ALL PASS - M1 基础设施验收通过" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "  FAIL - M1 基础设施验收未通过 (失败 $Failed 项)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
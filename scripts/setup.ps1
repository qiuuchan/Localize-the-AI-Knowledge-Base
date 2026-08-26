<#
.SYNOPSIS
  KB-AI · 5 分钟快速开始 — 交互式引导

.DESCRIPTION
  ### 5 步引导(每步按 Enter 继续,输入 N 跳过)
    1. 检查 Docker Desktop 是否安装
    2. 启动 KB-AI 服务(执行 start.bat)
    3. 配置 .env(含阿里云百炼 API Key)
    4. 试一次 AI 对话(调 chat.ps1)
    5. 安全弹出 U 盘(调 safe-eject.ps1)

  ### 适用对象
    非技术用户(餐饮分公司老总)— 全中文,避免专业术语。

  ### 运行
    powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
    pwsh -File scripts/setup.ps1

  ### 退出码
    0 = 5 步均执行或跳过
    1 = 环境检查不通过(如 Docker 未安装)

.PARAMETER NonInteractive
  跳过 Read-Host 等待,直接跑通每一步骤(用于 CI / 自动化)。

.PARAMETER SkipDockerCheck
  跳过 Docker 检查(在没有 Docker 的开发机也能跑通菜单)。

.NOTES
  PowerShell 5.1 兼容;UTF-8 无 BOM。
  不改任何已落地 .bat / .ps1 / .env / .md。
#>

[CmdletBinding()]
param(
    [switch]$NonInteractive = $false,
    [switch]$SkipDockerCheck = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RootDir    = Split-Path -Parent $scriptRoot

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step {
    param([string]$Step, [string]$Msg, [string]$Color = "Yellow")
    Write-Host "  [$Step] $Msg" -ForegroundColor $Color
}

function Write-OK {
    param([string]$Msg)
    Write-Host "        ✓ $Msg" -ForegroundColor Green
}

function Write-Skip {
    param([string]$Msg)
    Write-Host "        → $Msg(跳过)" -ForegroundColor Gray
}

function Write-Notice {
    param([string]$Msg)
    Write-Host "        ℹ $Msg" -ForegroundColor Cyan
}

function Write-Err {
    param([string]$Msg)
    Write-Host "        ✗ $Msg" -ForegroundColor Red
}

# Read-Host 兼容 PS 5.1 / PS 7+
function Read-Confirm {
    param(
        [string]$Prompt,
        [bool]$NonInteractive = $false
    )
    if ($NonInteractive) { return 'y' }
    $resp = Read-Host "        $Prompt"
    if ($null -eq $resp) { return '' }
    return $resp.Trim().ToLower()
}

# ----------------------------------------------------------------------
# Banner
# ----------------------------------------------------------------------

Clear-Host
Write-Host ""
Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║                                                            ║" -ForegroundColor Cyan
Write-Host "  ║       KB-AI  ·  5 分钟 快速开始                            ║" -ForegroundColor Cyan
Write-Host "  ║       (面向非技术用户 — 全中文,无专业术语)                  ║" -ForegroundColor Cyan
Write-Host "  ║                                                            ║" -ForegroundColor Cyan
Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  按 Enter 进入下一步;输入 N 跳过该步;Ctrl+C 随时退出。" -ForegroundColor Gray
Write-Host ""

# ----------------------------------------------------------------------
# Step 1: 检查 Docker Desktop
# ----------------------------------------------------------------------

Write-Step "1/5" "检查 Docker Desktop" "Yellow"

if ($SkipDockerCheck) {
    Write-Skip "Docker 检查已跳过"
}
else {
    try {
        $dockerVer = & docker --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $dockerVer) {
            Write-OK "已安装:$dockerVer"
        }
        else {
            throw "未找到 docker 命令"
        }
    }
    catch {
        Write-Err "Docker Desktop 未安装或未运行"
        Write-Host ""
        Write-Host "        请按以下步骤安装 Docker Desktop(免费):" -ForegroundColor Gray
        Write-Host "          1. 打开浏览器,访问 https://www.docker.com/products/docker-desktop/" -ForegroundColor Gray
        Write-Host "          2. 点击 'Download for Windows'" -ForegroundColor Gray
        Write-Host "          3. 双击安装包,一路'下一步'" -ForegroundColor Gray
        Write-Host "          4. 安装完重启电脑" -ForegroundColor Gray
        Write-Host "          5. 重启后启动 Docker Desktop,等右下角图标变绿" -ForegroundColor Gray
        Write-Host ""
        Write-Host "        安装好后重新跑本脚本。" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

Write-Host ""

# ----------------------------------------------------------------------
# Step 2: 启动 KB-AI 服务
# ----------------------------------------------------------------------

Write-Step "2/5" "启动 KB-AI 服务(执行 start.bat)" "Yellow"

$startBat = Join-Path $RootDir "start.bat"
if (-not (Test-Path -LiteralPath $startBat)) {
    Write-Err "找不到 start.bat:$startBat"
    Write-Notice "请把 KB-AI 部署到带 start.bat 的 U 盘根目录后再跑"
    exit 1
}

$ans = Read-Confirm "按 Enter 启动 KB-AI(或输入 N 跳过)"
if ($ans -eq 'n') {
    Write-Skip "未启动 start.bat(您可以稍后手动双击 start.bat)"
}
elseif ($NonInteractive) {
    # 非交互模式:start.bat 会尝试自动拉起 Docker Desktop 90s 长等待 + 阻塞;
    # 在 CI / 自动化环境直接跳过,避免阻塞
    Write-Skip "非交互模式:跳过 start.bat(改用 docker compose up -d 单独跑)"
    Write-Notice "在生产环境请直接双击 start.bat"
}
else {
    Write-Notice "正在调用 start.bat(首次启动约 60-90 秒)..."
    Write-Host ""
    try {
        # start.bat 是 .bat,ExitCode 0/1 都视为正常(1 = docker 未就绪但已尝试启动)
        $proc = Start-Process -FilePath $startBat -WorkingDirectory $RootDir -Wait -PassThru -NoNewWindow
        Write-Host ""
        if ($proc.ExitCode -eq 0) {
            Write-OK "start.bat 完成(exit=0,KB-AI 已就绪)"
            Write-Notice "浏览器可能已自动打开 Dify Web UI(http://localhost:8080)"
        } else {
            Write-Err "start.bat 退出码=$($proc.ExitCode)(可能 Docker 未启动,或端口冲突)"
            Write-Notice "可手动双击 start.bat 重试,或见 docs/quickstart.md §故障排查"
        }
    }
    catch {
        Write-Err "start.bat 执行异常:$($_.Exception.Message)"
    }
}

Write-Host ""

# ----------------------------------------------------------------------
# Step 3: 配置 .env(含 API Key)
# ----------------------------------------------------------------------

Write-Step "3/5" "配置 API Key" "Yellow"

$envFile     = Join-Path $RootDir ".env"
$envExample  = Join-Path $RootDir ".env.example"

if (Test-Path -LiteralPath $envFile) {
    Write-OK ".env 已存在"
    # 简单判定 .env 里的 API Key 是否还是占位符
    $envContent = ""
    try { $envContent = Get-Content -LiteralPath $envFile -Raw -Encoding UTF8 -ErrorAction Stop } catch { }
    if ($envContent -match "ALIYUN_BAILIAN_API_KEY\s*=\s*sk-[A-Za-z0-9_\-]{8,}" -and
        $envContent -notmatch "PLEASE-FILL-IN") {
        Write-OK "ALIYUN_BAILIAN_API_KEY 已填写真实值"
    }
    else {
        Write-Host "        ⚠ ALIYUN_BAILIAN_API_KEY 仍是占位符,请用记事本打开 .env 修改" -ForegroundColor Yellow
    }
}
else {
    Write-Notice ".env 不存在,从 .env.example 复制..."
    if (Test-Path -LiteralPath $envExample) {
        try {
            Copy-Item -LiteralPath $envExample -Destination $envFile -Force
            Write-OK "已复制 .env.example → .env"
            Write-Notice "请打开 .env,把 ALIYUN_BAILIAN_API_KEY 改成您的真实 API Key"
            Write-Notice "  API Key 在 https://bailian.console.aliyun.com/ 申请"
            $ans2 = Read-Confirm "按 Enter 打开记事本编辑 .env(回退 N 跳过,稍后自己打开)"
            if ($ans2 -ne 'n') {
                try { Start-Process -FilePath "notepad.exe" -ArgumentList $envFile -ErrorAction Stop | Out-Null }
                catch {
                    Write-Err "打开记事本失败:$($_.Exception.Message)"
                    Write-Notice "请手动在文件资源管理器双击 .env"
                }
                Write-Notice "填好 API Key 后保存并关闭记事本"
                Read-Confirm "按 Enter 继续(API Key 填好后再按)"
            }
        }
        catch {
            Write-Err "复制 .env.example 失败:$($_.Exception.Message)"
        }
    }
    else {
        Write-Err ".env.example 也不存在 — 请重新安装 KB-AI"
    }
}

Write-Host ""

# ----------------------------------------------------------------------
# Step 4: 试一次 AI 对话
# ----------------------------------------------------------------------

Write-Step "4/5" "试一次 AI 对话(调 chat.ps1)" "Yellow"

$ans = Read-Confirm "按 Enter 试一次对话(或输入 N 跳过)"
if ($ans -eq 'n') {
    Write-Skip "对话测试已跳过"
}
else {
    $chatScript = Join-Path $RootDir "scripts/chat.ps1"
    if (-not (Test-Path -LiteralPath $chatScript)) {
        Write-Err "找不到 chat.ps1"
    }
    else {
        Write-Notice "正在调 chat.ps1...若 .env 已有真实 API Key 应可对话,否则给出'未提供 API Key'提示"
        Write-Host ""
        try {
            & $chatScript -Question "你好,请用一句话自我介绍"
        }
        catch {
            Write-Err "chat.ps1 异常:$($_.Exception.Message)"
        }
        Write-Host ""
    }
}

Write-Host ""

# ----------------------------------------------------------------------
# Step 5: 安全弹出 U 盘
# ----------------------------------------------------------------------

Write-Step "5/5" "安全弹出 U 盘(调 safe-eject.ps1)" "Yellow"

Write-Notice "演示模式:仅打印提示,不会真的弹窗/停容器"
$ans = Read-Confirm "按 Enter 真实弹出 U 盘(或输入 N 跳过)"
if ($ans -eq 'n') {
    Write-Skip "安全弹出已跳过"
}
elseif ($NonInteractive) {
    # 非交互模式:跳过 safe-eject(它会调 stop.bat + 可能弹窗;E2E 测试场景才需要)
    Write-Skip "非交互模式:跳过 safe-eject(改在 tests/e2e_test.ps1 验证)"
}
else {
    $ejectScript = Join-Path $RootDir "scripts/safe-eject.ps1"
    if (-not (Test-Path -LiteralPath $ejectScript)) {
        Write-Err "找不到 safe-eject.ps1"
    }
    else {
        Write-Notice "5 秒倒计时 + 自动确认 + 提示拔出..."
        Write-Host ""
        try {
            & $ejectScript -AutoYes
        }
        catch {
            Write-Err "safe-eject.ps1 异常:$($_.Exception.Message)"
        }
    }
}

Write-Host ""

# ----------------------------------------------------------------------
# 收官
# ----------------------------------------------------------------------

Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   ✓  KB-AI 5 分钟快速开始 完成!                            ║" -ForegroundColor Green
Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Step "下一步" "见 QUICKSTART.md(用户快速开始指南)" "Cyan"
Write-Host "        上传文档:    powershell -File scripts/parse-doc.ps1 -Input 你的文档.pdf" -ForegroundColor Gray
Write-Host "        文档入库:    powershell -File scripts/embed-and-ingest.ps1 -ChunksFile ..chunks.jsonl" -ForegroundColor Gray
Write-Host "        多轮对话:    powershell -File scripts/chat.ps1 -SessionId <UUID> -Question " -NoNewline -ForegroundColor Gray
Write-Host "你的问题" -ForegroundColor DarkYellow
Write-Host "        健康度自检:  powershell -File scripts/health-full.ps1" -ForegroundColor Gray
Write-Host "        帮助中心:    powershell -File scripts/show-help.ps1" -ForegroundColor Gray
Write-Host "        故障排查:    powershell -File scripts/status-bar.ps1 -Mode auto -Loop" -ForegroundColor Gray
Write-Host ""

exit 0

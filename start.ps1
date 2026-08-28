<#
.SYNOPSIS
  KB-AI · 启动编排(单源 PowerShell 版)· v1.7.0

.DESCRIPTION
  ### 职责
    替换 start.bat:用 PowerShell 把 5 容器 + FastAPI 后端 + React 前端全链路拉起。
    同一份脚本在 Windows(PS 5.1)和 macOS(pwsh 7.4+)下运行,平台差异由
    scripts/lib/platform-utils.ps1 自动处理。

  ### 8 阶段流程(对应原 start.bat)
    [0/8] 预检(precheck.ps1 5 项)— 失败 abort
    [1/8] U 盘根目录定位 + PowerShell 策略(PS 5.1/7 进程级 Bypass)
    [2/8] Docker Desktop 检查 / 启动(Mac: open -a Docker;Win: Docker Desktop.exe)
    [3/8] .env 自检 + WAL 文件检测
    [4/8] 加载预置 Docker 镜像(tools/kb-ai-images.tar)
    [5/8] 复制预置 HF 模型到用户缓存(~/.cache/huggingface 或 %USERPROFILE%\.cache\huggingface)
    [6/8] 启动 Docker 容器(5 个)+ kb-ai-backend + MinerU 探测
    [7/8] 等待 http://localhost:8000/api/health 200(轮询 80s)
    [8/8] 打开浏览器

  ### 入口
    Windows:  双击 start.bat(原 .bat 保留,内部可改调本 .ps1,v1.7.1+)
    macOS:    双击 start.command(本目录)→ exec pwsh -File start.ps1

  ### 退出码
    0 = 成功(浏览器已打开)
    1 = 预检失败 / Docker 未就绪 / 镜像加载失败 / 80s 健康等待超时

.PARAMETER SkipPrecheck
  跳过预检(developer 用,客户文档不出现)

.PARAMETER SkipBrowser
  启动后不打开浏览器(测试用)

.EXAMPLE
  pwsh -NoProfile -ExecutionPolicy Bypass -File start.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File start.ps1 -SkipPrecheck -SkipBrowser

.NOTES
  PowerShell 5.1 兼容。
  UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding $false)。
  沿用 lib/ 共享助手(log + platform-utils + load-env)。
#>

[CmdletBinding()]
param(
    [Parameter(DontShow = $true)] [switch]$SkipPrecheck = $false,
    [Parameter(DontShow = $true)] [switch]$SkipBrowser = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# dot-source 共享助手
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'scripts/lib/Write-Log.ps1')
. (Join-Path $PSScriptRoot 'scripts/lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'scripts/lib/platform-utils.ps1')
. (Join-Path $PSScriptRoot 'scripts/get-usb-root.ps1')

Initialize-LogFile -ScriptName "start"

$Platform = Get-KBAIPlatform
$RootDir = Get-UsbRoot

Write-LogHost ""
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost "   KB-AI  启动中...  (请不要关闭此窗口)" -ForegroundColor Cyan
Write-LogHost "   平台: $Platform" -ForegroundColor Gray
Write-LogHost "   项目根: $RootDir" -ForegroundColor Gray
Write-LogHost "   AI 模型: Qwen3.6-Plus (默认) / Qwen3.7-Max (复杂)" -ForegroundColor Gray
Write-LogHost "   前端入口: http://localhost:8000" -ForegroundColor Gray
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost ""


# ----------------------------------------------------------------------
# [0/8] 预检(5 项检查)
# ----------------------------------------------------------------------

if (-not $SkipPrecheck) {
    Write-LogHost "[0/8] 客户机预检..." -ForegroundColor Cyan
    $precheck = Join-Path $PSScriptRoot 'precheck.ps1'
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $precheck
    if ($LASTEXITCODE -ne 0) {
        Write-LogHost ""
        Write-LogHost "   [错误] 预检未通过,KB-AI 启动中止" -ForegroundColor Red
        Write-LogHost "   看上方预检输出 + 查看 logs/ 启动日志排查" -ForegroundColor Yellow
        Close-LogFile
        exit 1
    }
    Write-LogHost "   预检通过" -ForegroundColor Green
    Write-LogHost ""
}


# ----------------------------------------------------------------------
# [1/8] U 盘根目录 + PowerShell 策略
# ----------------------------------------------------------------------

Write-LogHost "[1/8] U 盘根目录: $RootDir" -ForegroundColor Cyan

# PowerShell 5.1 执行策略(只对当前进程生效,不修改系统策略)
try {
    Set-ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue
} catch {
    # macOS pwsh 7+ 上 Set-ExecutionPolicy 在某些配置下不可用,忽略
}

# 验证关键目录存在
$requiredDirs = @('backend', 'data', 'vectors', 'docker-compose.yml', '.env', 'scripts')
$missingDirs = @()
foreach ($d in $requiredDirs) {
    $full = Join-Path $RootDir $d
    if (-not (Test-Path -LiteralPath $full)) {
        $missingDirs += $d
    }
}
if ($missingDirs.Count -gt 0) {
    Write-LogHost "   [错误] 项目根缺少关键目录/文件:$($missingDirs -join ', ')" -ForegroundColor Red
    Write-LogHost "   可能是 U 盘数据损坏或目录错位" -ForegroundColor Yellow
    Close-LogFile
    exit 1
}


# ----------------------------------------------------------------------
# [2/8] Docker Desktop 检查 / 启动
# ----------------------------------------------------------------------

Write-LogHost "[2/8] 检查 Docker Desktop..." -ForegroundColor Cyan

# 检查 docker 命令是否在 PATH
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-LogHost "   [错误] 找不到 docker 命令" -ForegroundColor Red
    if ($Platform -eq 'macOS') {
        Write-LogHost "   请先安装 Docker Desktop(brew install --cask docker)" -ForegroundColor Yellow
    } else {
        Write-LogHost "   请先安装 Docker Desktop(从 docker.com 下载)" -ForegroundColor Yellow
    }
    Close-LogFile
    exit 1
}

# 探测 Docker daemon 是否在跑
$dockerInfo = & docker info 2>&1
$dockerReady = $LASTEXITCODE -eq 0

if (-not $dockerReady) {
    Write-LogHost "   Docker Desktop 未运行,正在后台启动(首次 30-60 秒)..." -ForegroundColor Yellow

    if ($Platform -eq 'macOS') {
        # macOS:用 open -a 启动 Docker Desktop
        & open -a "Docker" 2>&1 | Out-Null
    } else {
        # Windows:启动 Docker Desktop.exe
        $dockerDesktopExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path -LiteralPath $dockerDesktopExe) {
            Start-Process -FilePath $dockerDesktopExe -ErrorAction SilentlyContinue
        } else {
            Write-LogHost "   [错误] 找不到 Docker Desktop.exe:$dockerDesktopExe" -ForegroundColor Red
            Close-LogFile
            exit 1
        }
    }

    # 等待 Docker daemon 就绪(最多 90 秒,18 × 5s)
    $waitCount = 0
    $dockerReady = $false
    while ($waitCount -lt 18) {
        $waitCount++
        Start-Sleep -Seconds 5
        $null = & docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            break
        }
        Write-LogHost "   等待 Docker Desktop 就绪... [$waitCount/18]" -ForegroundColor Gray
    }

    if (-not $dockerReady) {
        Write-LogHost "" -ForegroundColor Red
        Write-LogHost "   [错误] Docker Desktop 启动超时(90 秒)" -ForegroundColor Red
        Write-LogHost "   排查:" -ForegroundColor Yellow
        Write-LogHost "     1. 电脑是否已重启?首次安装 Docker 需要重启一次" -ForegroundColor Gray
        Write-LogHost "     2. (macOS)系统设置 → 隐私与安全 → 允许 Docker Desktop" -ForegroundColor Gray
        Write-LogHost "     3. 截屏记录后查看 logs/ 启动日志" -ForegroundColor Gray
        Close-LogFile
        exit 1
    }
}

Write-LogHost "   Docker Desktop 已就绪" -ForegroundColor Green
Write-LogHost ""


# ----------------------------------------------------------------------
# [3/8] .env 自检 + WAL 检测
# ----------------------------------------------------------------------

Write-LogHost "[3/8] 自检..." -ForegroundColor Cyan

$envPath = Join-Path $RootDir '.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    Write-LogHost "   [错误] .env 不存在" -ForegroundColor Red
    Write-LogHost "   请联系客服补发 .env" -ForegroundColor Yellow
    Close-LogFile
    exit 1
}

# 占位符检测(用 /B 行首匹配,避开注释误命中)
$envLines = Get-Content -LiteralPath $envPath -Encoding UTF8 -ErrorAction SilentlyContinue
$placeholderHit = $false
foreach ($line in $envLines) {
    if ($line -match '^ALIYUN_BAILIAN_API_KEY=sk-PLEASE-FILL-IN') {
        $placeholderHit = $true
        break
    }
}
if ($placeholderHit) {
    Write-LogHost "   [错误] .env 里的 API Key 还是占位符" -ForegroundColor Red
    Write-LogHost "   请联系客服补填" -ForegroundColor Yellow
    Close-LogFile
    exit 1
}

# WAL 检测(上次是否干净退出,不阻断)
$walPath = Join-Path $RootDir 'data/db.sqlite-wal'
if (Test-Path -LiteralPath $walPath) {
    Write-LogHost "   [警告] 检测到 WAL 文件,上次可能未正常退出" -ForegroundColor Yellow
    Write-LogHost "          系统会自动尝试恢复,无需操作" -ForegroundColor Gray
    Start-Sleep -Seconds 3
}

Write-LogHost "   自检通过" -ForegroundColor Green
Write-LogHost ""


# ----------------------------------------------------------------------
# [4/8] 加载预置 Docker 镜像(避免 5-10 分钟 docker pull)
# ----------------------------------------------------------------------

Write-LogHost "[4/8] 加载预置 Docker 镜像..." -ForegroundColor Cyan

$imagesTar = Join-Path $RootDir 'tools/kb-ai-images.tar'
$imagesFlag = Join-Path $RootDir '.docker-images-loaded.flag'

if (-not (Test-Path -LiteralPath $imagesTar)) {
    Write-LogHost "   [警告] 未找到预置镜像 tools/kb-ai-images.tar" -ForegroundColor Yellow
    Write-LogHost "          将从 Docker Hub 联网下载,首次需 5-10 分钟" -ForegroundColor Gray
} elseif (Test-Path -LiteralPath $imagesFlag) {
    Write-LogHost "   镜像已加载过,跳过" -ForegroundColor Green
} else {
    Write-LogHost "   首次启动,正在加载预置镜像(约 1-2 分钟)..." -ForegroundColor Cyan
    & docker load -i $imagesTar 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-LogHost "   [警告] 预置镜像加载失败,将从 Docker Hub 联网下载" -ForegroundColor Yellow
        Write-LogHost "          可能原因:U 盘读写错误 / Docker Desktop 异常" -ForegroundColor Gray
    } else {
        # 写标记文件(空文件)
        try {
            "" | Out-File -LiteralPath $imagesFlag -Encoding UTF8 -ErrorAction Stop
        } catch {
            # U 盘只读时静默
        }
        Write-LogHost "   镜像加载完成" -ForegroundColor Green
    }
}
Write-LogHost ""


# ----------------------------------------------------------------------
# [5/8] 复制预置 HF 模型到用户目录
# ----------------------------------------------------------------------

Write-LogHost "[5/8] 加载预置 HF 模型..." -ForegroundColor Cyan

# 平台感知的目标路径
if ($Platform -eq 'macOS') {
    $hfDestRoot = Join-Path $env:HOME '.cache/huggingface'
} else {
    $hfDestRoot = Join-Path $env:USERPROFILE '.cache\huggingface'
}
$hfDestHub = Join-Path $hfDestRoot 'hub'
$hfReranker = Join-Path $hfDestHub 'models--BAAI--bge-reranker-base'

# 检查目标位置是否已有 reranker
if (Test-Path -LiteralPath $hfReranker) {
    Write-LogHost "   HF 模型已存在,跳过复制" -ForegroundColor Green
} else {
    $hfSourceHub = Join-Path $RootDir 'models/huggingface/hub'
    if (-not (Test-Path -LiteralPath $hfSourceHub)) {
        Write-LogHost "   [警告] 未找到预置 HF 模型,首次检索可能慢" -ForegroundColor Yellow
    } else {
        Write-LogHost "   首次启动,正在复制预置模型到本地缓存(约 30 秒)..." -ForegroundColor Cyan
        if (-not (Test-Path -LiteralPath $hfDestHub)) {
            try {
                New-Item -ItemType Directory -Path $hfDestHub -Force | Out-Null
            } catch {
                Write-LogHost "   [警告] 创建 HF 目标目录失败:$_" -ForegroundColor Yellow
            }
        }
        # 跨平台拷贝
        try {
            if ($Platform -eq 'macOS') {
                & cp -R "$hfSourceHub/." "$hfDestHub/" 2>&1 | Out-Null
            } else {
                # Windows:用 Copy-Item 递归
                Copy-Item -Path (Join-Path $hfSourceHub '*') -Destination $hfDestHub -Recurse -Force
            }
            Write-LogHost "   HF 模型加载完成" -ForegroundColor Green
        } catch {
            Write-LogHost "   [警告] 模型复制失败:$_" -ForegroundColor Yellow
        }
    }
}
Write-LogHost ""


# ----------------------------------------------------------------------
# [6/8] 启动 Docker 容器 + kb-ai-backend + MinerU 探测
# ----------------------------------------------------------------------

Write-LogHost "[6/8] 启动 Docker 容器(5 个)+ KB-AI 后端..." -ForegroundColor Cyan

Push-Location $RootDir
try {
    & docker compose up -d 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-LogHost "   [错误] docker compose up 失败" -ForegroundColor Red
        Write-LogHost "   请把这一屏截图发给客服" -ForegroundColor Yellow
        Pop-Location
        Close-LogFile
        exit 1
    }

    # 单独确保 kb-ai-backend 起来(v1.5.0+ 容器化,可能在主 compose 后没自动起)
    & docker compose up -d kb-ai-backend 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-LogHost "   [警告] FastAPI 后端容器启动失败" -ForegroundColor Yellow
        Write-LogHost "          手动排查:docker compose logs kb-ai-backend" -ForegroundColor Gray
    }
} finally {
    Pop-Location
}

# MinerU 探测(:8001,可选)
$mineruOk = $false
try {
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { $mineruOk = $true }
} catch {
    $mineruOk = $false
}

if ($mineruOk) {
    Write-LogHost "   MinerU 解析服务已在运行" -ForegroundColor Green
} else {
    Write-LogHost "   [跳过] PDF/PPTX 解析服务(本批 U 盘未打包 MinerU)" -ForegroundColor Yellow
    Write-LogHost "            聊天不受影响;如需解析请联系发盘人远程配置" -ForegroundColor Gray
}
Write-LogHost "   容器已全部启动" -ForegroundColor Green
Write-LogHost ""


# ----------------------------------------------------------------------
# [7/8] 等待 KB-AI 前端就绪(http://localhost:8000/api/health 200)
# ----------------------------------------------------------------------

Write-LogHost "[7/8] 等待 KB-AI 前端就绪(约 30-60 秒)..." -ForegroundColor Cyan

$apiReady = $false
$apiCount = 0
while ($apiCount -lt 40) {
    $apiCount++
    try {
        $resp = Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $apiReady = $true
            break
        }
    } catch {
        # 健康检查失败,继续等
    }
    Start-Sleep -Seconds 2
    if ($apiCount % 5 -eq 0) {
        Write-LogHost "   检查中... [$apiCount/40]" -ForegroundColor Gray
    }
}

if (-not $apiReady) {
    Write-LogHost "" -ForegroundColor Red
    Write-LogHost "   [警告] KB-AI 前端启动超过 80 秒" -ForegroundColor Yellow
    Write-LogHost "          可能首次在拉依赖,可手动访问:http://localhost:8000" -ForegroundColor Gray
} else {
    Write-LogHost "   KB-AI 前端已就绪!" -ForegroundColor Green
    Write-LogHost ""
}


# ----------------------------------------------------------------------
# [8/8] 打开浏览器
# ----------------------------------------------------------------------

if (-not $SkipBrowser) {
    Write-LogHost "[8/8] 打开浏览器..." -ForegroundColor Cyan
    try {
        Open-KBAIUrl -Url 'http://localhost:8000'
    } catch {
        Write-LogHost "   [警告] 打开浏览器失败:$_" -ForegroundColor Yellow
        Write-LogHost "          请手动访问:http://localhost:8000" -ForegroundColor Gray
    }
} else {
    Write-LogHost "[8/8] 跳过打开浏览器(-SkipBrowser)" -ForegroundColor Gray
}


# ----------------------------------------------------------------------
# 总结
# ----------------------------------------------------------------------

Write-LogHost ""
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost "   启动完成!" -ForegroundColor Green
Write-LogHost ""
Write-LogHost "   KB-AI 前端:     http://localhost:8000" -ForegroundColor White
Write-LogHost "   FastAPI 文档:   http://localhost:8000/docs" -ForegroundColor Gray
Write-LogHost "   Dify Web (兼容): http://localhost:8080" -ForegroundColor Gray
Write-LogHost ""
Write-LogHost "   关闭服务: 终端跑 stop.ps1(或双击 stop.bat / stop.command)" -ForegroundColor Gray
Write-LogHost "   安全弹出: 先停服务,然后桌面弹出 USB" -ForegroundColor Gray
Write-LogHost ""
Write-LogHost "   故障排查: 截屏记录后查看 logs/ 启动日志 + 看 $RootDir\logs\start-*.log" -ForegroundColor Gray
Write-LogHost "============================================================" -ForegroundColor Cyan
Write-LogHost ""

# 退出收尾(沿用 start.bat 的 errorlevel 语义)
Close-LogFile

if ($apiReady) { exit 0 } else { exit 1 }

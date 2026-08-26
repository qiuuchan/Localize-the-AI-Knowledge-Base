<#
.SYNOPSIS
  KB-AI · 启动 FastAPI 后端服务

.DESCRIPTION
  - 自动定位 U 盘根目录(get-usb-root.ps1)
  - 创建 backend/.venv(若不存在)并安装依赖
  - 启动 uvicorn,监听 127.0.0.1:8000
  - 将进程 PID 写入 tmp/backend.pid

.PARAMETER Port
  监听端口(默认 8000)

.PARAMETER Reload
  开发模式:启用 uvicorn --reload

.EXAMPLE
  pwsh -File scripts/start-backend.ps1
  pwsh -File scripts/start-backend.ps1 -Port 8081 -Reload
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Reload = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------
. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/platform-utils.ps1')
. (Join-Path $PSScriptRoot 'get-usb-root.ps1')

$rootDir = Get-UsbRoot
$backendDir = Join-Path $rootDir "backend"
# v1.7.0 Mac 支持:venv 路径走 platform-utils 自动平台切换(Win: Scripts/, Mac/Linux: bin/)
$venvPython = Get-KBAIPythonVenvPath -BackendDir $backendDir
$venvPip = Get-KBAIPythonVenvPip -BackendDir $backendDir
$pidFile = Join-Path $rootDir "tmp/backend.pid"

Write-Host "[KB-AI Backend] 项目根目录: $rootDir" -ForegroundColor Cyan

# ----------------------------------------------------------------------
# 创建虚拟环境
# ----------------------------------------------------------------------
if (-not (Test-Path $venvPython)) {
    Write-Host "[KB-AI Backend] 创建虚拟环境..." -ForegroundColor Cyan
    $pyCmd = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    & $pyCmd -3 -m venv (Join-Path $backendDir ".venv")
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
}

# ----------------------------------------------------------------------
# 安装/更新依赖
# ----------------------------------------------------------------------
Write-Host "[KB-AI Backend] 安装依赖..." -ForegroundColor Cyan
& $venvPip install -r (Join-Path $backendDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }

# ----------------------------------------------------------------------
# 写 PID 文件
# ----------------------------------------------------------------------
$tmpDir = Split-Path $pidFile
if (-not (Test-Path $tmpDir)) { New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null }

# 如果已有 PID 文件,尝试停止旧进程
if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -Raw -ErrorAction SilentlyContinue
    if ($oldPid) {
        try {
            $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[KB-AI Backend] 停止旧进程 PID=$oldPid" -ForegroundColor Yellow
                Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            }
        } catch { }
    }
}

# ----------------------------------------------------------------------
# 启动 uvicorn
# ----------------------------------------------------------------------
$env:KB_AI_ROOT = $rootDir
# v1.7.0 Mac 支持:同 venv 路径三件套
$uvicorn = Get-KBAIPythonVenvUvicorn -BackendDir $backendDir
$args = @("backend.main:app", "--host", "127.0.0.1", "--port", $Port)
if ($Reload) { $args += "--reload" }

Write-Host "[KB-AI Backend] 启动 uvicorn on 127.0.0.1:$Port ..." -ForegroundColor Green
Write-Host "  访问: http://127.0.0.1:$Port/api" -ForegroundColor Gray
Write-Host "  文档: http://127.0.0.1:$Port/docs" -ForegroundColor Gray

$proc = Start-Process -FilePath $uvicorn -ArgumentList $args `
                      -WorkingDirectory $rootDir `
                      -WindowStyle Hidden -PassThru

$proc.Id | Out-File -FilePath $pidFile -Encoding utf8 -NoNewline
Write-Host "[KB-AI Backend] 进程 PID=$($proc.Id) 已写入 $pidFile" -ForegroundColor Green

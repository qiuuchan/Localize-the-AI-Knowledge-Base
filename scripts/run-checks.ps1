<#
.SYNOPSIS
  KB-AI · 一键全检(2026-07-17 新增)— 本地 CI 等价物

.DESCRIPTION
  按顺序跑 4 道检查,任一失败最终退出码为 1(不中断,全部跑完再汇总):
    [1/4] ruff   — 后端 Python 静态检查(backend/ + tests/unit/ + tests/integration/api/)
    [2/4] pytest — 后端单元测试(tests/unit/)
    [3/4] eslint — 前端静态检查(npm run lint)
    [4/4] build  — 前端类型检查 + 构建(npm run build;可 -SkipFrontendBuild 跳过)

.PARAMETER SkipFrontendBuild
  跳过第 4 步(tsc + vite build 较慢,约 30-60 秒)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run-checks.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run-checks.ps1 -SkipFrontendBuild

.NOTES
  PowerShell 5.1 兼容;需要 backend\.venv 已建、frontend\node_modules 已装。
  退出码:0 全过;1 有失败项。
#>

[CmdletBinding()]
param(
    [switch]$SkipFrontendBuild = $false
)

$ErrorActionPreference = "Continue"

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = Split-Path -Parent $scriptRoot
# v1.7.0 Mac 支持:venv 路径走 platform-utils 自动平台切换
. (Join-Path $PSScriptRoot 'lib/platform-utils.ps1')
$venvPy = Get-KBAIPythonVenvPath -BackendDir (Join-Path $root 'backend')
$frontendDir = Join-Path $root 'frontend'

$results = @()

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== [$Name] ===" -ForegroundColor Cyan
    & $Action
    $ok = ($LASTEXITCODE -eq 0)
    $script:results += [pscustomobject]@{ Step = $Name; OK = $ok }
    if ($ok) { Write-Host "[PASS] $Name" -ForegroundColor Green }
    else     { Write-Host "[FAIL] $Name (exit=$LASTEXITCODE)" -ForegroundColor Red }
}

if (-not (Test-Path $venvPy)) {
    Write-Host "[ERROR] 未找到 backend\.venv,请先跑 scripts\start-backend.ps1 建环境" -ForegroundColor Red
    exit 1
}

Push-Location $root
try {
    Invoke-Step "1/4 ruff(后端静态检查)" {
        & $venvPy -m ruff check --config backend\ruff.toml backend\ tests\unit\ tests\integration\api\
    }

    Invoke-Step "2/4 pytest(后端单测)" {
        & $venvPy -m pytest tests\unit\ -q
    }

    Invoke-Step "3/4 eslint(前端静态检查)" {
        Push-Location $frontendDir
        try { & npm run lint --silent } finally { Pop-Location }
    }

    if ($SkipFrontendBuild) {
        Write-Host ""
        Write-Host "=== [4/4 build] 已跳过(-SkipFrontendBuild) ===" -ForegroundColor Yellow
    } else {
        Invoke-Step "4/4 build(前端类型检查+构建)" {
            Push-Location $frontendDir
            try { & npm run build } finally { Pop-Location }
        }
    }
} finally {
    Pop-Location
}

# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
$failed = @($results | Where-Object { -not $_.OK })
foreach ($r in $results) {
    $mark = if ($r.OK) { "[PASS]" } else { "[FAIL]" }
    $color = if ($r.OK) { "Green" } else { "Red" }
    Write-Host ("  {0} {1}" -f $mark, $r.Step) -ForegroundColor $color
}
if ($failed.Count -eq 0) {
    Write-Host "全部检查通过 ✓" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("{0} 项检查失败 ✗" -f $failed.Count) -ForegroundColor Red
    exit 1
}

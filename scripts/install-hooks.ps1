<#
.SYNOPSIS
  KB-AI · 安装/卸载 git hooks (v1.3.0)

.DESCRIPTION
  默认: git config core.hooksPath scripts/hooks(项目级 hooks 路径)
  -Uninstall: git config --unset core.hooksPath
  -DryRun: 只 echo,不真修改 git config

.EXAMPLE
  pwsh -File scripts/install-hooks.ps1
  pwsh -File scripts/install-hooks.ps1 -DryRun
  pwsh -File scripts/install-hooks.ps1 -Uninstall

.NOTES
  PowerShell 5.1 兼容。
  pwsh (PowerShell 7+) 不在 PATH 时输出警告但仍配置(pre-push 会降级)。
#>

[CmdletBinding()]
param(
    [switch]$Uninstall = $false,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = Split-Path -Parent $scriptRoot
$hooksDir = Join-Path $root 'scripts\hooks'
$hooksRelPath = 'scripts/hooks'

# pwsh 探测(给 pre-push 兜底)
$pwshAvailable = $null -ne (Get-Command pwsh -ErrorAction SilentlyContinue)
if (-not $pwshAvailable) {
    Write-Host "[WARN] pwsh (PowerShell 7+) not found in PATH." -ForegroundColor Yellow
    Write-Host "       pre-push hook 会降级为 noop;install PowerShell 7+ 以启用全检。" -ForegroundColor Yellow
}

if ($Uninstall) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] would unset core.hooksPath" -ForegroundColor Cyan
        exit 0
    }
    Push-Location $root
    try {
        git config --unset core.hooksPath 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ hooks 已卸载 (core.hooksPath unset)" -ForegroundColor Green
        } else {
            Write-Host "[INFO] core.hooksPath was not set; nothing to remove" -ForegroundColor Yellow
        }
    } finally {
        Pop-Location
    }
    exit 0
}

# 安装
if (-not (Test-Path $hooksDir)) {
    Write-Host "[ERROR] hooks directory not found: $hooksDir" -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host "[DRY-RUN] would run: git config core.hooksPath $hooksRelPath" -ForegroundColor Cyan
    Write-Host "[DRY-RUN] pwsh available: $pwshAvailable" -ForegroundColor Cyan
    exit 0
}

Push-Location $root
try {
    git config core.hooksPath $hooksRelPath
    if ($LASTEXITCODE -ne 0) {
        throw "git config failed"
    }
    Write-Host "✓ hooks 已配置到 $hooksRelPath" -ForegroundColor Green
    Write-Host "  下次 git commit 会自动跑 ruff check backend/ tests/" -ForegroundColor Green
    Write-Host "  下次 git push 会自动跑 scripts/run-checks.ps1" -ForegroundColor Green

    # v1.3.0 fix: 在 Unix / WSL / macOS 上确保 hook 文件有 executable bit
    # Windows 文件系统层级已经 +x,git 的 index mode 仍可能 100644(取决于 git config)
    # git update-index --chmod=+x 让 git 记录文件为可执行(Unix clone 后无需再 chmod)
    foreach ($hook in @('pre-commit', 'pre-push')) {
        $hookPath = Join-Path $hooksDir $hook
        git update-index --chmod=+x $hookRelPath/$hook 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ $hook executable bit 已设(Unix / WSL 兼容)" -ForegroundColor Green
        }
    }

    if (-not $pwshAvailable) {
        Write-Host ""
        Write-Host "[WARN] pwsh 不可用;pre-push 会降级。" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}
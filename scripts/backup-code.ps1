<#
.SYNOPSIS
  KB-AI · 代码备份(2026-07-17 新增)— 把 git 仓库推送到电脑硬盘的裸仓库

.DESCRIPTION
  - 背景:backup.ps1 备份数据(data\ + vectors\),本脚本备份代码(git 全历史)。
    两者互补:U 盘丢失/损坏时,代码与数据都能从电脑硬盘找回。
  - 机制:在备份目录维护一个裸仓库 kbai-code.git,push 所有分支与 tag。
  - 备份目录优先级(与 backup.ps1 一致):-BackupDir 参数 > 环境变量 KBAI_BACKUP_DIR
    > .env KBAI_BACKUP_DIR > %USERPROFILE%\KB-AI-Backup(默认)。
  - 同盘守卫:裸仓库与项目同盘(同一块 U 盘)时,显式参数 → 警告继续;否则回退默认目录。

.PARAMETER RootDir
  项目根目录(默认 scripts 的父目录)

.PARAMETER BackupDir
  备份目标目录(默认见上)

.PARAMETER Quiet
  只输出警告/错误与最终结果

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backup-code.ps1

.NOTES
  PowerShell 5.1 兼容;需要 git 在 PATH 中。
  退出码:0 成功;1 失败;2 项目根不是 git 仓库(提示先 git init)。
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [string]$BackupDir,
    [switch]$Quiet = $false
)

$ErrorActionPreference = "Stop"

if (-not $RootDir) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RootDir = Split-Path -Parent $scriptRoot
}

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')

function Write-Step { param([string]$Msg) if (-not $Quiet) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan } }
function Write-Ok   { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }

# ----------------------------------------------------------------------
# 前置检查
# ----------------------------------------------------------------------

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 git 命令,请先安装 Git for Windows" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $RootDir '.git'))) {
    Write-Host "[ERROR] $RootDir 不是 git 仓库,请先执行 git init 并提交" -ForegroundColor Red
    exit 2
}

# ----------------------------------------------------------------------
# 备份目录解析:参数 > 环境变量 > .env > 默认(电脑硬盘)
# ----------------------------------------------------------------------

$defaultBackupDir = Join-Path $env:USERPROFILE 'KB-AI-Backup'
$explicitDir = -not [string]::IsNullOrWhiteSpace($BackupDir)

if (-not $explicitDir) {
    if ($env:KBAI_BACKUP_DIR -and $env:KBAI_BACKUP_DIR.Trim()) {
        $BackupDir = $env:KBAI_BACKUP_DIR.Trim()
    } else {
        $envPath = Join-Path $RootDir '.env'
        $fromEnv = Get-EnvVar -EnvPath $envPath -Name 'KBAI_BACKUP_DIR'
        if ($fromEnv -and $fromEnv.Trim()) {
            $BackupDir = $fromEnv.Trim()
        } else {
            $BackupDir = $defaultBackupDir
        }
    }
}

# 同盘守卫(与 backup.ps1 一致)
$rootDrive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($RootDir))
$destDrive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($BackupDir))
if ($rootDrive -eq $destDrive) {
    if ($explicitDir) {
        Write-Warn "备份目录与项目同盘($rootDrive),盘损坏时备份会一起丢失,强烈建议改到电脑硬盘"
    } else {
        Write-Warn "备份目录与项目同盘($rootDrive),回退到默认目录:$defaultBackupDir"
        $BackupDir = $defaultBackupDir
    }
}

$bareRepo = Join-Path $BackupDir 'kbai-code.git'

# ----------------------------------------------------------------------
# 裸仓库不存在则初始化
# ----------------------------------------------------------------------

if (-not (Test-Path $bareRepo)) {
    Write-Step "初始化裸仓库:$bareRepo"
    New-Item -ItemType Directory -Path $bareRepo -Force | Out-Null
    & git init --bare $bareRepo | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] git init --bare 失败" -ForegroundColor Red
        exit 1
    }
}

# ----------------------------------------------------------------------
# 推送所有分支与 tag
# ----------------------------------------------------------------------

Write-Step "推送代码与历史 → $bareRepo"
& git -C $RootDir push $bareRepo 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] git push 失败(exit=$LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

$commitCount = (& git -C $RootDir rev-list --all --count)
Write-Ok "代码备份完成:$bareRepo(共 $commitCount 个提交)"
exit 0

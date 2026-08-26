<#
.SYNOPSIS
  KB-AI · 数据备份(v0.8.6 新增,FMEA F03)— 把 U 盘上的数据备份到电脑硬盘

.DESCRIPTION
  - 背景:全部数据只有 U 盘单份,零备份(FMEA F03,RPN 300,数据单点最高风险)。
  - 触发:stop.bat 停止服务后自动调用(2026-07-16 用户授权修改 stop.bat);
    也可随时手动执行。
  - 备份内容(存在才备):
      data\db.sqlite(含 -wal / -shm 伴生文件)
      data\entities.json
      data\embedding-cache.jsonl
      data\uploads\   data\parsed\
      vectors\(Qdrant 存储;排除 .deleted 待 GC 目录)
  - 产物:<BackupDir>\kbai-backup-yyyyMMdd-HHmmss.zip,保留最近 -Keep 份,超出自动删除。
  - 备份目录优先级:-BackupDir 参数 > 环境变量 KBAI_BACKUP_DIR > .env KBAI_BACKUP_DIR
    > %USERPROFILE%\KB-AI-Backup(默认,即电脑硬盘)。
    解析结果与项目根同盘(同一块 U 盘)时:显式参数 → 警告继续;否则回退默认目录。
  - 安全:zip 先写临时文件再 Move 到位;目标盘剩余空间 < 数据量时报错退出(不半写)。

.PARAMETER RootDir
  项目根目录(默认 scripts 的父目录)

.PARAMETER BackupDir
  备份目标目录(默认见上)

.PARAMETER Keep
  保留的备份份数(默认 7)

.PARAMETER Quiet
  只输出警告/错误与最终结果(供 stop.bat 自动调用)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
  pwsh -File scripts/backup.ps1 -BackupDir 'D:\backups\kbai' -Keep 14

.NOTES
  PowerShell 5.1 兼容;不依赖 7z(用内置 Compress-Archive)。
  服务运行中也可执行(db.sqlite 的 -wal 已一并备份,恢复时可 replay),推荐停止后执行。
  退出码:0 成功;1 失败;2 无数据可备。
#>

[CmdletBinding()]
param(
    [string]$RootDir,
    [string]$BackupDir,
    [int]$Keep = 7,
    [switch]$Quiet = $false
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    $scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RootDir = Split-Path -Parent $scriptRoot
}

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')

function Write-Step { param([string]$Msg) if (-not $Quiet) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan } }
function Write-Ok   { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }

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

# 同盘守卫:备份到同一块 U 盘没有意义(盘坏/丢 = 备份同归于尽)
try {
    $rootDrive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($RootDir))
    $destDrive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($BackupDir))
} catch {
    Write-Host "[ERROR] 备份目录路径格式无效:'$BackupDir'($($_.Exception.Message))" -ForegroundColor Red
    exit 1
}
if ($rootDrive -eq $destDrive) {
    if ($explicitDir) {
        Write-Warn "备份目录与项目同盘($rootDrive),盘损坏时备份会一起丢失,强烈建议改到电脑硬盘"
    } else {
        Write-Warn "备份目录与项目同盘($rootDrive),回退到默认目录:$defaultBackupDir"
        $BackupDir = $defaultBackupDir
    }
}

# 运行中提示(不阻断;WAL 已一并备份,恢复时可 replay)
$pidFile = Join-Path $RootDir 'tmp\backend.pid'
if (Test-Path $pidFile) {
    Write-Warn "检测到 tmp\backend.pid,后端可能在运行;建议在 stop.bat 停止后备份(运行中备份可能含未落盘写入)"
}

# ----------------------------------------------------------------------
# 收集备份源(存在才备),先拷到临时暂存目录
# ----------------------------------------------------------------------

$dataDir = Join-Path $RootDir 'data'
$staging = Join-Path $env:TEMP ("kbai-backup-" + [guid]::NewGuid().ToString('N'))
$startedAt = Get-Date

try {
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $stagingData = Join-Path $staging 'data'
    New-Item -ItemType Directory -Path $stagingData -Force | Out-Null

    $copied = 0

    if (Test-Path $dataDir) {
        # data\db.sqlite*(主库 + -wal / -shm 伴生文件)
        Get-ChildItem -Path $dataDir -File -Filter 'db.sqlite*' -Force -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item $_.FullName -Destination $stagingData -Force
            $copied++
        }
        # data 根目录下的零散文件
        foreach ($f in @('entities.json', 'embedding-cache.jsonl')) {
            $src = Join-Path $dataDir $f
            if (Test-Path $src) {
                Copy-Item $src -Destination $stagingData -Force
                $copied++
            }
        }
        # uploads / parsed 整目录
        foreach ($d in @('uploads', 'parsed')) {
            $src = Join-Path $dataDir $d
            if (Test-Path $src) {
                Copy-Item $src -Destination $stagingData -Recurse -Force
                $copied++
            }
        }
    }

    # vectors\(Qdrant 存储;排除 .deleted 待 GC 目录)
    $vectorsDir = Join-Path $RootDir 'vectors'
    if (Test-Path $vectorsDir) {
        Copy-Item $vectorsDir -Destination $staging -Recurse -Force
        $stagedDeleted = Join-Path $staging 'vectors\.deleted'
        if (Test-Path $stagedDeleted) { Remove-Item $stagedDeleted -Recurse -Force -ErrorAction SilentlyContinue }
        $copied++
    }

    if ($copied -eq 0) {
        Write-Warn "没有找到任何数据(data\ / vectors\ 均不存在),跳过备份"
        exit 2
    }

    # ----------------------------------------------------------------------
    # 目标盘剩余空间检查(不足则报错退出,不半写)
    # ----------------------------------------------------------------------

    $totalBytes = (Get-ChildItem -Path $staging -Recurse -File -Force -ErrorAction SilentlyContinue |
                   Measure-Object -Property Length -Sum).Sum
    if (-not $totalBytes) { $totalBytes = 0L }

    $destRoot = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($BackupDir))
    $driveInfo = New-Object System.IO.DriveInfo($destRoot.TrimEnd('\'))
    $freeBytes = $driveInfo.AvailableFreeSpace
    if ($freeBytes -lt $totalBytes) {
        Write-Host "[ERROR] 目标盘 $destRoot 剩余空间不足:需要约 $([math]::Round($totalBytes/1MB,0)) MB,仅剩 $([math]::Round($freeBytes/1MB,0)) MB" -ForegroundColor Red
        exit 1
    }

    # ----------------------------------------------------------------------
    # 压缩(zip 先写临时文件,再 Move 到位)
    # ----------------------------------------------------------------------

    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $finalZip = Join-Path $BackupDir "kbai-backup-$stamp.zip"
    # Compress-Archive 只接受 .zip 扩展名;临时文件放 TEMP(同名 -Force 覆盖),完成后再 Move 到位
    $tmpZip = Join-Path $env:TEMP "kbai-backup-$stamp.zip"

    Write-Step "压缩 $([math]::Round($totalBytes/1MB,1)) MB → $finalZip ..."
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $tmpZip -CompressionLevel Optimal -Force
    Move-Item $tmpZip $finalZip -Force

    $zipMB = [math]::Round((Get-Item $finalZip).Length / 1MB, 1)

    # ----------------------------------------------------------------------
    # v0.8.11(P2.2):写一份 manifest 清单(zip 同名 .manifest.json),
    # 记录每条路径与 SHA-1,供恢复时校验完整性。
    # ----------------------------------------------------------------------

    Write-Step "生成 manifest ..."
    $manifestPath = Join-Path $staging 'backup-manifest.json'
    $manifest = [ordered]@{
        backup_version = '0.8.11'
        created_at = $startedAt.ToString('o')
        root_dir = $RootDir
        total_files = 0
        total_bytes = $totalBytes
        entries = @()
    }
    Get-ChildItem -Path $staging -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $rel = $_.FullName.Substring($staging.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA1).Hash
        $manifest.entries += [ordered]@{
            path = $rel
            bytes = $_.Length
            sha1 = $hash
        }
    }
    $manifest.total_files = $manifest.entries.Count
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8

    # 重新打包,把 manifest 也打进去
    Remove-Item $tmpZip -ErrorAction SilentlyContinue
    $tmpZipWithManifest = Join-Path $env:TEMP "kbai-backup-$stamp.zip"
    if (Test-Path $tmpZipWithManifest) { Remove-Item $tmpZipWithManifest -Force }
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $tmpZipWithManifest -CompressionLevel Optimal -Force
    Move-Item $tmpZipWithManifest $finalZip -Force

    $zipMB = [math]::Round((Get-Item $finalZip).Length / 1MB, 1)

    # ----------------------------------------------------------------------
    # 轮换:只保留最近 $Keep 份
    # ----------------------------------------------------------------------

    $deleted = 0
    $zips = @(Get-ChildItem -Path $BackupDir -Filter 'kbai-backup-*.zip' -File -Force -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending)
    if ($zips.Count -gt $Keep) {
        $zips | Select-Object -Skip $Keep | ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
            $deleted++
        }
    }

    $elapsed = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
    Write-Ok "备份完成:$finalZip($zipMB MB,耗时 $elapsed 秒;保留 $($zips.Count - $deleted) 份,上限 $Keep 份)"
    exit 0
} catch {
    Write-Host "[ERROR] 备份失败:$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}

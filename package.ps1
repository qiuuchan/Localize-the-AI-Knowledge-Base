<#
.SYNOPSIS
  KB-AI · 打包脚本(单源 PowerShell 版)· v1.7.0

.DESCRIPTION
  ### 职责
    替换 package.bat:把 KB-AI 源打包成 KB-AI-M1-M3.zip(给客户升级用)。
    同一份脚本在 Windows(PS 5.1)和 macOS(pwsh 7.4+)下运行。
    Compress-Archive 是 PS 5.1+ 内置 cmdlet,跨平台。

  ### 包含项
    目录:scripts/  tests/  docs/  dify/
    文件:start.bat  stop.bat  docker-compose.yml  precheck.bat  package.bat
         start.ps1  stop.ps1  precheck.ps1  package.ps1  start.command  stop.command
         QUICKSTART.md  docs/releases/RELEASE-M3*.md
         .env.example  .gitignore
         version

  ### 排除项
    data/  vectors/  cache/  logs/  tmp/  .venv/  node_modules/  __pycache__/

  ### 输出
    默认:<项目根>/../KB-AI-M1-M3.zip
    自定义:-OutName 参数

  ### 入口
    Windows:  powershell -ExecutionPolicy Bypass -File package.ps1
    macOS:    ./package.sh(Mac 双击或终端)

.PARAMETER OutName
  输出 zip 文件名(默认 KB-AI-M1-M3.zip)

.PARAMETER RootDir
  项目根目录(默认从 $PSScriptRoot 推断)

.EXAMPLE
  pwsh -NoProfile -ExecutionPolicy Bypass -File package.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File package.ps1 -OutName KB-AI-v1.7.0.zip

.NOTES
  PowerShell 5.1 兼容(Compress-Archive 5.1+ 内置)。
  UTF-8 无 BOM。
#>

[CmdletBinding()]
param(
    [string]$OutName = 'KB-AI-M1-M3.zip',
    [string]$RootDir
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

if (-not $RootDir) {
    if ($PSScriptRoot) {
        $RootDir = $PSScriptRoot
    } else {
        $RootDir = (Get-Location).Path
    }
}

# 输出目录:项目根的父目录(沿用 package.bat 的布局,zip 放在 workspace-root/)
$parentRoot = Split-Path -Parent $RootDir
$zipPath = Join-Path $parentRoot $OutName

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   KB-AI package.ps1 v1.7.0 打包" -ForegroundColor Cyan
Write-Host "   source : $RootDir" -ForegroundColor Gray
Write-Host "   target : $zipPath" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------
# 删除旧 zip
# ----------------------------------------------------------------------

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
    Write-Host "   [清理] 旧的 $OutName" -ForegroundColor Gray
}

# ----------------------------------------------------------------------
# 收集要打包的目录(存在才加)
# ----------------------------------------------------------------------

$items = New-Object System.Collections.Generic.List[string]

$dirs = @('scripts', 'tests', 'docs', 'dify')
foreach ($d in $dirs) {
    $full = Join-Path $RootDir $d
    if (Test-Path -LiteralPath $full) {
        [void]$items.Add($full)
        Write-Host "   + $d/" -ForegroundColor Green
    } else {
        Write-Host "   - $d/(不存在,跳过)" -ForegroundColor Gray
    }
}

# 文件清单
$files = @(
    # Windows 入口
    'start.bat', 'stop.bat', 'precheck.bat', 'package.bat',
    # Mac/PowerShell 入口(v1.7.0 新增)
    'start.ps1', 'stop.ps1', 'precheck.ps1', 'package.ps1',
    'start.command', 'stop.command', 'package.sh',
    # 配置
    'docker-compose.yml', '.env.example', '.gitignore', 'version',
    # 文档
    'QUICKSTART.md'
)
foreach ($f in $files) {
    $full = Join-Path $RootDir $f
    if (Test-Path -LiteralPath $full) {
        [void]$items.Add($full)
        Write-Host "   + $f" -ForegroundColor Green
    } else {
        Write-Host "   - $f(不存在,跳过)" -ForegroundColor Gray
    }
}

# docs/releases/RELEASE-M3*.md(沿用 package.bat 的子集)
if (Test-Path -LiteralPath (Join-Path $RootDir 'docs/releases')) {
    $releases = Get-ChildItem -LiteralPath (Join-Path $RootDir 'docs/releases') -Filter 'RELEASE-M3*.md' -File -ErrorAction SilentlyContinue
    foreach ($r in $releases) {
        [void]$items.Add($r.FullName)
        Write-Host "   + docs/releases/$($r.Name)" -ForegroundColor Green
    }
}

# ----------------------------------------------------------------------
# 压缩
# ----------------------------------------------------------------------

if ($items.Count -eq 0) {
    Write-Host ""
    Write-Host "   [错误] 没有任何要打包的文件" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "   压缩 $($items.Count) 项 → $OutName ..." -ForegroundColor Cyan

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
} catch {
    # .NET 8+ 内置,5.1 需要显式加载
    Write-Host "   [警告] 加载 System.IO.Compression 失败:$_" -ForegroundColor Yellow
}

try {
    Compress-Archive -Path $items -DestinationPath $zipPath -CompressionLevel Optimal -Force -ErrorAction Stop
} catch {
    Write-Host ""
    Write-Host "   [错误] Compress-Archive 失败:$_" -ForegroundColor Red
    exit 1
}

# 统计
$zip = Get-Item -LiteralPath $zipPath
$sizeKB = [math]::Round($zip.Length / 1KB, 1)
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip.FullName)
$entryCount = $archive.Entries.Count
$archive.Dispose()

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   打包完成" -ForegroundColor Green
Write-Host "   文件: $zipPath" -ForegroundColor White
Write-Host "   大小: $sizeKB KB" -ForegroundColor Gray
Write-Host "   条目: $entryCount" -ForegroundColor Gray
Write-Host ""
Write-Host "   下一步:把 zip 拷到 U 盘根,解压覆盖旧文件" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

exit 0

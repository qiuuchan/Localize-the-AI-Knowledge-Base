<#
.SYNOPSIS
  处理剩余 PDF/PPTX 失败文件,使用策略:
  - PDF → 直接 pandoc(MinerU 太慢)
  - 小 PPTX(≤30MB) → MinerU
  - 大 PPTX(>30MB) → python-pptx 回退
#>

[CmdletBinding()]
param(
    [string]$StatusFile = "E:\tmp\batch-parse-status.json",
    [string]$OutputDir = "E:\data\parsed",
    [string]$MineruUrl = "http://127.0.0.1:8001",
    [string]$Collection = "kb_ai_chunks"
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')

# pandoc 路径
$pandocDir = "E:\tools\pandoc"
if (Test-Path $pandocDir) {
    $env:Path = "$pandocDir;" + $env:Path
    Write-Step "已添加 pandoc 到 PATH: $pandocDir"
}

if (-not (Test-Path $StatusFile)) { throw "状态文件不存在: $StatusFile" }

$status = Get-Content -Path $StatusFile -Encoding UTF8 | ConvertFrom-Json
# PowerShell 5.1 ConvertFrom-Json 不会解码 \u0026 等转义,手动还原
foreach ($item in $status.failed) { if ($item.file) { $item.file = $item.file -replace '\\u0026', '&' } }
foreach ($item in $status.success) { if ($item.file) { $item.file = $item.file -replace '\\u0026', '&' } }
foreach ($item in $status.skipped) { if ($item.file) { $item.file = $item.file -replace '\\u0026', '&' } }
$failed = $status.failed
if (-not $failed -or $failed.Count -eq 0) {
    Write-Step "没有失败文件需要重跑"
    return
}

$parseScript = Join-Path $PSScriptRoot 'parse-doc.ps1'
$ingestScript = Join-Path $PSScriptRoot 'embed-and-ingest.ps1'
$sourceDir = "E:\新建文件夹\NA"

$newSuccess = [System.Collections.Generic.List[object]]::new()
$stillFailed = [System.Collections.Generic.List[object]]::new()

foreach ($item in $failed) {
    $relPath = $item.file
    $fullPath = Join-Path $sourceDir $relPath
    $ext = [System.IO.Path]::GetExtension($relPath).ToLower()
    $sizeMB = 0
    if (Test-Path -LiteralPath $fullPath) {
        $sizeMB = (Get-Item -LiteralPath $fullPath).Length / 1MB
    }

    $noMineruPdf = $false
    $noMineruPptx = $false
    if ($ext -eq '.pdf') {
        $noMineruPdf = $true
        Write-Step "重跑 PDF(直接 pandoc): $relPath (${sizeMB:N1} MB)"
    } elseif ($ext -eq '.pptx') {
        if ($sizeMB -gt 30) {
            $noMineruPptx = $true
            Write-Step "重跑大 PPTX(直接 python-pptx): $relPath (${sizeMB:N1} MB)"
        } else {
            Write-Step "重跑小 PPTX(MinerU): $relPath (${sizeMB:N1} MB)"
        }
    } else {
        Write-Warn "跳过非 PDF/PPTX: $relPath"
        continue
    }

    try {
        if (-not (Test-Path -LiteralPath $fullPath)) {
            throw "文件不存在: $fullPath"
        }

        $hash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.Substring(0, 16)
        $docOutDir = Join-Path $OutputDir $hash
        New-Item -ItemType Directory -Force -Path $docOutDir | Out-Null

        $parseArgs = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $parseScript,
            "-InputFile", $fullPath,
            "-OutputDir", $docOutDir,
            "-MineruUrl", $MineruUrl
        )
        if ($noMineruPdf) { $parseArgs += "-NoMineruPdf" }
        if ($noMineruPptx) { $parseArgs += "-NoMineruPptx" }
        & powershell @parseArgs

        $chunksFile = Get-ChildItem -Path $docOutDir -Filter 'chunks.jsonl' -Recurse | Select-Object -First 1
        if (-not $chunksFile) {
            throw "parse-doc.ps1 未生成 chunks.jsonl"
        }

        & powershell -ExecutionPolicy Bypass -File $ingestScript `
            -ChunksFile $chunksFile.FullName `
            -Collection $Collection

        $newSuccess.Add(@{
            file = $relPath
            hash = $hash
            chunksFile = $chunksFile.FullName
        })
        Write-Step "✅ 重跑成功: $relPath"

        # 增量写状态
        $status.success = $status.success + @($newSuccess[-1])
        $status.failed = @($status.failed | Where-Object { $_.file -ne $relPath })
        $status.updatedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        $status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8
    } catch {
        $stillFailed.Add(@{
            file = $relPath
            error = $_.Exception.Message
        })
        Write-Warn "❌ 重跑仍失败: $relPath - $($_.Exception.Message)"
    }
}

$status.failed = $stillFailed
$status.updatedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8

Write-Step "重跑完成: 本次新成功 $($newSuccess.Count), 仍失败 $($stillFailed.Count)"

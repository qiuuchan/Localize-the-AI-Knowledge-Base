<#
.SYNOPSIS
  处理 batch-parse-status.json 中尚未处理的文件（跳过已成功/失败的）。
.DESCRIPTION
  1. 读取状态文件
  2. 遍历源目录，排除 ._*/不支持的扩展名/已成功/已失败的文件
  3. 逐个解析并入库，更新状态文件
  4. 支持 -MaxFileSizeMB 过滤超大文件（默认 100 MB）
#>

[CmdletBinding()]
param(
    [string]$SourceDir = "E:\新建文件夹\NA",
    [string]$OutputDir = "E:\data\parsed",
    [string]$MineruUrl = "http://127.0.0.1:8001",
    [string]$Collection = "kb_ai_chunks",
    [string]$StatusFile = "E:\tmp\batch-parse-status.json",
    [int]$MaxFileSizeMB = 100
)

$ErrorActionPreference = "Stop"

# MinerU 大 PDF 渲染超时
[Environment]::SetEnvironmentVariable("MINERU_PDF_RENDER_TIMEOUT", "1800", "Process")

# pandoc 路径
$pandocDir = "E:\tools\pandoc"
if (Test-Path $pandocDir) {
    $env:Path = "$pandocDir;" + $env:Path
}

. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')

$parseScript = Join-Path $PSScriptRoot 'parse-doc.ps1'
$ingestScript = Join-Path $PSScriptRoot 'embed-and-ingest.ps1'

if (-not (Test-Path $StatusFile)) { throw "状态文件不存在: $StatusFile" }

$status = Get-Content -Path $StatusFile -Encoding UTF8 | ConvertFrom-Json
$processed = @{}
foreach ($x in $status.success) { $processed[$x.file] = $true }
foreach ($x in $status.failed) { $processed[$x.file] = $true }

$validExts = @('.pdf','.docx','.pptx','.xlsx','.txt','.md')
$maxBytes = $MaxFileSizeMB * 1MB

$files = Get-ChildItem -Path $SourceDir -Recurse -File | Where-Object {
    $_.Name -notlike '._*' -and
    ($validExts -contains $_.Extension.ToLower()) -and
    $_.Length -le $maxBytes
} | ForEach-Object {
    $rel = $_.FullName.Substring($SourceDir.Length).TrimStart('\','/')
    [PSCustomObject]@{
        File = $_
        RelPath = $rel
        Processed = $processed.ContainsKey($rel)
        Size = $_.Length
    }
} | Where-Object { -not $_.Processed } | Sort-Object -Property Size

Write-Step "发现 $($files.Count) 个待处理文件(跳过已处理/超过 ${MaxFileSizeMB}MB 的文件)"

if ($files.Count -eq 0) { return }

$newSuccess = [System.Collections.Generic.List[object]]::new()
$newFailed = [System.Collections.Generic.List[object]]::new()

foreach ($item in $files) {
    $file = $item.File
    $relPath = $item.RelPath
    $sizeMB = [math]::Round($item.Size / 1MB, 1)
    Write-Step "处理: $relPath (${sizeMB} MB)"

    try {
        $hash = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.Substring(0, 16)
        $docOutDir = Join-Path $OutputDir $hash
        New-Item -ItemType Directory -Force -Path $docOutDir | Out-Null

        & powershell -ExecutionPolicy Bypass -File $parseScript `
            -InputFile $file.FullName `
            -OutputDir $docOutDir `
            -MineruUrl $MineruUrl

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
        $status.success += @{
            file = $relPath
            hash = $hash
            chunksFile = $chunksFile.FullName
        }
        Write-Step "✅ 完成: $relPath"
    } catch {
        $newFailed.Add(@{
            file = $relPath
            error = $_.Exception.Message
        })
        $status.failed += @{
            file = $relPath
            error = $_.Exception.Message
        }
        Write-Warn "❌ 失败: $relPath - $($_.Exception.Message)"
    }

    $status.updatedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    $status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8
}

Write-Step "剩余文件处理完成: 新成功 $($newSuccess.Count), 新失败 $($newFailed.Count)"

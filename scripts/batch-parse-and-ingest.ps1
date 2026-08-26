<#
.SYNOPSIS
  批量解析 E:\新建文件夹\NA 下所有文档并入库 Qdrant(v0.8.2 支持旧点清理 + manifest)。
.DESCRIPTION
  1. 遍历 NA 目录下所有有效文件(排除 macOS 资源分叉 ._*)  
  2. 对每个文件:若 manifest 中已有旧 point_ids,先按 source_file 清理 Qdrant + keyword_index
  3. 调 parse-doc.ps1 重新解析(启用 frontmatter + 原子分块 + certainty 标签)
  4. 调 embed-and-ingest.ps1 写入 kb_ai_chunks,并同步更新 manifest
  5. 记录成功/失败清单到 tmp/batch-parse-status.json
#>

[CmdletBinding()]
param(
    [string]$SourceDir = "E:\新建文件夹\NA",
    [string]$OutputDir = "E:\data\parsed",
    [string]$MineruUrl = "http://127.0.0.1:8001",
    [string]$Collection = "kb_ai_chunks",
    [string]$StatusFile = "E:\tmp\batch-parse-status.json",
    [string]$ManifestFile = "E:\tmp\batch-parse-manifest.json",
    [string]$QdrantUrl = "http://localhost:6333",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

# MinerU 默认 PDF 图片渲染超时只有 300 秒,大 PDF 在 CPU 上不够,改成 1800 秒
[Environment]::SetEnvironmentVariable("MINERU_PDF_RENDER_TIMEOUT", "1800", "Process")

# 把本地 pandoc 加入 PATH(供 parse-doc.ps1 调用 docx→markdown)
$pandocDir = "E:\tools\pandoc"
if (Test-Path $pandocDir) {
    $env:Path = "$pandocDir;" + $env:Path
}

# 加载公共库
. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')
. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/Invoke-SqliteExec.ps1')

$parseScript = Join-Path $PSScriptRoot 'parse-doc.ps1'
$ingestScript = Join-Path $PSScriptRoot 'embed-and-ingest.ps1'

if (-not (Test-Path $SourceDir)) { throw "SourceDir 不存在: $SourceDir" }
if (-not (Test-Path $parseScript)) { throw "parse-doc.ps1 不存在: $parseScript" }
if (-not (Test-Path $ingestScript)) { throw "embed-and-ingest.ps1 不存在: $ingestScript" }

# 创建输出根目录
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# v0.8.2: 加载已有 manifest(source_file -> point_ids)
$manifest = @{}
if (Test-Path $ManifestFile) {
    try {
        $m = Get-Content $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($m.sources) {
            foreach ($k in $m.sources.PSObject.Properties.Name) {
                $manifest[$k] = @($m.sources.$k)
            }
        }
        Write-Step "加载 manifest: $($manifest.Count) 个 source"
    } catch {
        Write-Warn "manifest 加载失败,将重建: $_"
        $manifest = @{}
    }
}

# ----------------------------------------------------------------------
# Qdrant / SQLite 清理辅助
# ----------------------------------------------------------------------

function Remove-QdrantPointsByIds {
    param(
        [string]$Url,
        [string]$Collection,
        [string[]]$Ids,
        [int]$BatchSize = 100
    )
    if ($Ids.Count -eq 0) { return }
    $headers = @{ "Content-Type" = "application/json" }
    for ($i = 0; $i -lt $Ids.Count; $i += $BatchSize) {
        $slice = $Ids[$i..([Math]::Min($i + $BatchSize - 1, $Ids.Count - 1))]
        $body = @{ points = @($slice) } | ConvertTo-Json
        try {
            $resp = Invoke-WebRequest -Uri "$Url/collections/$Collection/points/delete" -Method Post `
                 -Headers $headers -Body $body -TimeoutSec 60 -UseBasicParsing
            if ($resp.StatusCode -notin 200, 202) {
                Write-Warn "Qdrant 删除返回 HTTP $($resp.StatusCode)"
            }
        } catch {
            Write-Warn "Qdrant 删除失败: $_"
        }
    }
}

function Remove-KeywordIndexByPointIds {
    param(
        [string]$DbPath,
        [string[]]$Ids,
        [int]$BatchSize = 100
    )
    if ($Ids.Count -eq 0 -or -not (Test-Path $DbPath)) { return }
    for ($i = 0; $i -lt $Ids.Count; $i += $BatchSize) {
        $slice = $Ids[$i..([Math]::Min($i + $BatchSize - 1, $Ids.Count - 1))]
        $placeholders = ($slice | ForEach-Object { "?" }) -join ","
        try {
            Invoke-SqliteExec -DbPath $DbPath `
                -Sql "DELETE FROM keyword_index WHERE point_id IN ($placeholders)" `
                -Params $slice | Out-Null
        } catch {
            Write-Warn "keyword_index 删除失败: $_"
        }
    }
}

function Save-Manifest {
    param([string]$Path, [hashtable]$Data, [string]$Collection)
    $obj = @{
        collection = $Collection
        updatedAt  = (Get-Date).ToString("o")
        sources    = @{}
    }
    foreach ($k in $Data.Keys) {
        $obj.sources[$k] = @($Data[$k])
    }
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $obj | ConvertTo-Json -Depth 5 | Set-Content -Path $Path -Encoding UTF8
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

# 收集文件:排除 macOS 资源分叉,也排除明显不是文档的文件
$validExts = @('.pdf','.docx','.pptx','.xlsx','.doc','.ppt','.txt','.md','.png','.jpg','.jpeg')
$files = Get-ChildItem -Path $SourceDir -Recurse -File | Where-Object {
    $_.Name -notlike '._*' -and
    $_.Name -notlike '~$*' -and
    ($validExts -contains $_.Extension.ToLower())
} | Sort-Object -Property Length

Write-Step "找到 $($files.Count) 个待处理文件(已按文件大小升序排列,优先处理小文件)"

$status = @{
    startedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    total = $files.Count
    success = @()
    failed = @()
}

$dbPath = Join-Path (Split-Path -Parent $PSScriptRoot) "data/db.sqlite"

$index = 0
foreach ($file in $files) {
    $index++
    $relPath = $file.FullName.Substring($SourceDir.Length).TrimStart('\','/')
    $fileName = $file.Name
    Write-Step "[$index/$($files.Count)] 处理: $relPath"

    if ($WhatIf) { continue }

    try {
        # v0.8.2: 清理旧点(按 source_file)
        if ($manifest.ContainsKey($fileName)) {
            $oldIds = $manifest[$fileName]
            if ($oldIds -and $oldIds.Count -gt 0) {
                Write-Step "  → 清理旧点: $($oldIds.Count) 个"
                Remove-QdrantPointsByIds -Url $QdrantUrl -Collection $Collection -Ids $oldIds
                Remove-KeywordIndexByPointIds -DbPath $dbPath -Ids $oldIds
            }
        }

        # 用文件内容哈希做输出目录名,避免文件名过长/特殊字符
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.Substring(0, 16)
        $docOutDir = Join-Path $OutputDir $hash
        New-Item -ItemType Directory -Force -Path $docOutDir | Out-Null

        # 1) 解析
        & powershell -ExecutionPolicy Bypass -File $parseScript `
            -InputFile $file.FullName `
            -OutputDir $docOutDir `
            -MineruUrl $MineruUrl

        # 2) 找到 chunks.jsonl
        $chunksFile = Get-ChildItem -Path $docOutDir -Filter 'chunks.jsonl' -Recurse | Select-Object -First 1
        if (-not $chunksFile) {
            throw "parse-doc.ps1 未生成 chunks.jsonl"
        }

        # 3) 入库(同步 manifest)
        & powershell -ExecutionPolicy Bypass -File $ingestScript `
            -ChunksFile $chunksFile.FullName `
            -Collection $Collection `
            -ManifestFile $ManifestFile

        $status.success += @{
            file = $relPath
            hash = $hash
            chunksFile = $chunksFile.FullName
        }
        Write-Step "[$index/$($files.Count)] ✅ 完成: $relPath"
    } catch {
        $status.failed += @{
            file = $relPath
            error = $_.Exception.Message
        }
        Write-Warn "[$index/$($files.Count)] ❌ 失败: $relPath - $($_.Exception.Message)"
    }

    # 每处理完一个文件保存一次状态,方便中断后恢复
    $status.updatedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    $status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8
}

$status.finishedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8

Write-Step "批量处理完成: 成功 $($status.success.Count)/$($files.Count), 失败 $($status.failed.Count)/$($files.Count)"
Write-Step "状态文件: $StatusFile"
Write-Step "Manifest 文件: $ManifestFile"

<#
.SYNOPSIS
  读取 batch-parse-status.json,只对失败的文件重新执行 parse-doc + embed-and-ingest。
.DESCRIPTION
  用于在主批量任务完成后,补救 pandoc 未装、MinerU 超时等导致的失败文件。
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

# MinerU 大 PDF 渲染超时
[Environment]::SetEnvironmentVariable("MINERU_PDF_RENDER_TIMEOUT", "1800", "Process")

# pandoc 路径
$pandocDir = "E:\tools\pandoc"
if (Test-Path $pandocDir) {
    $env:Path = "$pandocDir;" + $env:Path
    Write-Step "已添加 pandoc 到 PATH: $pandocDir"
}

if (-not (Test-Path $StatusFile)) { throw "状态文件不存在: $StatusFile" }

$status = Get-Content -Path $StatusFile -Encoding UTF8 | ConvertFrom-Json
$failed = $status.failed
if (-not $failed -or $failed.Count -eq 0) {
    Write-Step "没有失败文件需要重跑"
    return
}

Write-Step "发现 $($failed.Count) 个失败文件,开始重跑"

$parseScript = Join-Path $PSScriptRoot 'parse-doc.ps1'
$ingestScript = Join-Path $PSScriptRoot 'embed-and-ingest.ps1'
$sourceDir = "E:\新建文件夹\NA"

$newSuccess = [System.Collections.Generic.List[object]]::new()
$stillFailed = [System.Collections.Generic.List[object]]::new()
$skipped = [System.Collections.Generic.List[object]]::new()

foreach ($item in $failed) {
    $relPath = $item.file
    $fullPath = Join-Path $sourceDir $relPath
    $fileName = Split-Path $relPath -Leaf

    # 跳过 Office 临时文件 / macOS 资源叉 / 不支持类型
    if ($fileName -like '~$*' -or $fileName -like '._*') {
        Write-Warn "跳过 Office 临时文件 / macOS 资源叉: $relPath"
        $skipped.Add(@{ file = $relPath; reason = 'temp/resource-fork' })
        continue
    }
    $ext = [System.IO.Path]::GetExtension($fileName).ToLower()
    $supported = @('.docx','.pdf','.pptx','.xlsx','.txt','.md')
    if ($supported -notcontains $ext) {
        Write-Warn "跳过不支持类型 ($ext): $relPath"
        $skipped.Add(@{ file = $relPath; reason = "unsupported-extension:$ext" })
        continue
    }

    Write-Step "重跑: $relPath"

    try {
        if (-not (Test-Path -LiteralPath $fullPath)) {
            throw "文件不存在: $fullPath"
        }

        $hash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.Substring(0, 16)
        $docOutDir = Join-Path $OutputDir $hash
        New-Item -ItemType Directory -Force -Path $docOutDir | Out-Null

        & powershell -ExecutionPolicy Bypass -File $parseScript `
            -InputFile $fullPath `
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
        Write-Step "✅ 重跑成功: $relPath"

        # 每成功一个就增量写状态,避免总任务超时丢失进度
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

# 更新状态:失败的替换为仍失败的,跳过的单独记录(成功已在循环中增量写入)
$status.failed = $stillFailed
if (-not $status.PSObject.Properties.Item('skipped')) {
    $status | Add-Member -MemberType NoteProperty -Name 'skipped' -Value $skipped
} else {
    $status.skipped = $status.skipped + $skipped
}
$status.updatedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$status | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusFile -Encoding UTF8

Write-Step "重跑完成: 本次新成功 $($newSuccess.Count), 仍失败 $($stillFailed.Count), 跳过 $($skipped.Count)"

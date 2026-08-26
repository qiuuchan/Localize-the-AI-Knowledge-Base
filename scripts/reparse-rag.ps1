<#
.SYNOPSIS
    批量 reparse 知识库文档 — 读取 JSON manifest,逐条调用 reparse 路由并轮询状态。

.DESCRIPTION
    manifest 格式 (UTF-8 JSON 数组):
    [
      {"source":"progress.xlsx","upload_path":"1717000000_0_progress.xlsx"},
      {"source":"budget.xlsx","upload_path":"1717000000_1_budget.xlsx"}
    ]

    每条 task 轮询 /api/knowledge/tasks/{task_id},遇到 done 记录 chunk_count,
    遇到 failed 记录 error。最终以失败数量作为退出码。

.PARAMETER ManifestPath
    JSON manifest 文件路径 (必填)。

.PARAMETER BaseUrl
    后端地址,默认 http://127.0.0.1:8000。

.PARAMETER DatabaseId
    目标数据库 id,默认 default。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/reparse-rag.ps1 -ManifestPath data/reparse-manifest.json
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,

    [string]$BaseUrl = "http://127.0.0.1:8000",

    [string]$DatabaseId = "default"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $ManifestPath)) {
    Write-Error "Manifest 文件不存在: $ManifestPath"
    exit 1
}

$raw = Get-Content -Path $ManifestPath -Raw -Encoding UTF8
$items = $raw | ConvertFrom-Json

if ($null -eq $items -or $items.Count -eq 0) {
    Write-Host "Manifest 为空,无需处理。"
    exit 0
}

Write-Host "=== reparse-rag: $($items.Count) 条任务 ==="
Write-Host "BaseUrl: $BaseUrl | DatabaseId: $DatabaseId"
Write-Host ""

$failCount = 0
$doneCount = 0

foreach ($item in $items) {
    $source = $item.source
    $uploadPath = $item.upload_path
    Write-Host "[$source] 提交 reparse..."

    $encodedSource = [uri]::EscapeDataString($source)
    $encodedPath = [uri]::EscapeDataString($uploadPath)
    $postUrl = "$BaseUrl/api/knowledge/documents/$encodedSource/reparse?database_id=$DatabaseId&upload_path=$encodedPath"

    try {
        $resp = Invoke-WebRequest -Method Post -Uri $postUrl -UseBasicParsing -TimeoutSec 30
        $body = $resp.Content | ConvertFrom-Json
    }
    catch {
        Write-Host "  [FAIL] 提交失败: $_" -ForegroundColor Red
        $failCount++
        continue
    }

    $taskId = $body.task_id
    if (-not $taskId) {
        Write-Host "  [FAIL] 未返回 task_id" -ForegroundColor Red
        $failCount++
        continue
    }

    Write-Host "  task_id=$taskId, 轮询中..."

    $statusUrl = "$BaseUrl/api/knowledge/tasks/$taskId"
    $maxPolls = 120
    $pollInterval = 3
    $finalStatus = "timeout"

    for ($i = 0; $i -lt $maxPolls; $i++) {
        Start-Sleep -Seconds $pollInterval
        try {
            $pollResp = Invoke-WebRequest -Method Get -Uri $statusUrl -UseBasicParsing -TimeoutSec 15
            $taskBody = $pollResp.Content | ConvertFrom-Json
        }
        catch {
            continue
        }

        $taskStatus = $taskBody.status
        if ($taskStatus -eq "done") {
            $finalStatus = "done"
            $chunkCount = $taskBody.chunk_count
            Write-Host "  [DONE] chunk_count=$chunkCount" -ForegroundColor Green
            $doneCount++
            break
        }
        elseif ($taskStatus -eq "failed") {
            $finalStatus = "failed"
            $errMsg = $taskBody.error
            Write-Host "  [FAIL] $errMsg" -ForegroundColor Red
            $failCount++
            break
        }
    }

    if ($finalStatus -eq "timeout") {
        Write-Host "  [TIMEOUT] 超过 $($maxPolls * $pollInterval)s 未完成" -ForegroundColor Yellow
        $failCount++
    }
}

Write-Host ""
Write-Host "=== 完成: $doneCount 成功, $failCount 失败 ==="
exit $failCount

<#
.SYNOPSIS
  验证 parse-doc.ps1 的 frontmatter 提取与代码块/表格原子分块保护。

.NOTES
  PowerShell 5.1 兼容;不依赖外部 API 与容器。
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$parseScript = Join-Path (Join-Path (Join-Path $PSScriptRoot '..') 'scripts') 'parse-doc.ps1'
. $parseScript

$testMd = @'
---
title: "测试文档"
date: 2025-01-01
source: "手册"
type: "manual"
tags: [tag1, tag2]
---

# 引言

这是第一段。包含一些说明。

这是第二段。

```python
def hello():
    print("hello world")
    return 42
```

| 列A | 列B |
|-----|-----|
| 1   | 2   |

结尾段落。
'@

$chunks = Split-IntoChunks -Text $testMd -Source "test.md" -DefaultDate "2024-12-01"

$failed = New-Object System.Collections.Generic.List[string]

# 1. frontmatter 元数据传递到所有 chunk
$titleChunks = $chunks | Where-Object { $_.meta.title -eq '测试文档' }
if (-not $titleChunks) { $failed.Add("title 未提取或未传播") }

$dateOk = $chunks | Where-Object { $_.meta.date -eq '2025-01-01' } | Select-Object -First 1
if (-not $dateOk) { $failed.Add("date 未提取") }

$typeOk = $chunks | Where-Object { $_.meta.doc_type -eq 'manual' } | Select-Object -First 1
if (-not $typeOk) { $failed.Add("doc_type 未提取") }

$tagOk = $chunks | Where-Object { $_.meta.tags -like '*tag1*' } | Select-Object -First 1
if (-not $tagOk) { $failed.Add("tags 未提取") }

# 2. 代码块作为原子块,chunk_type=code,内容完整
$codeChunk = $chunks | Where-Object { $_.meta.chunk_type -eq 'code' } | Select-Object -First 1
if (-not $codeChunk) {
    $failed.Add("未识别到代码块 chunk")
} else {
    if ($codeChunk.text -notmatch '^```python') { $failed.Add("代码块 chunk 丢失起始围栏") }
    if ($codeChunk.text -notmatch 'print\("hello world"\)') { $failed.Add("代码块 chunk 内容被截断") }
    if ($codeChunk.text -notmatch 'return 42') { $failed.Add("代码块 chunk 末尾被截断") }
}

# 3. 表格作为原子块,chunk_type=table,内容完整
$tableChunk = $chunks | Where-Object { $_.meta.chunk_type -eq 'table' } | Select-Object -First 1
if (-not $tableChunk) {
    $failed.Add("未识别到表格 chunk")
} else {
    if ($tableChunk.text -notmatch '^\|\s*列A') { $failed.Add("表格 chunk 丢失表头") }
    if ($tableChunk.text -notmatch '\|\s*1\s*\|') { $failed.Add("表格 chunk 丢失数据行") }
}

# 4. frontmatter 不应再出现在正文 chunk 中
$bodyWithFm = $chunks | Where-Object { $_.text -match '^---\s*$' } | Select-Object -First 1
if ($bodyWithFm) { $failed.Add("frontmatter 仍留在正文 chunk 中") }

# 5. 无 frontmatter 时的默认值
$defaultMd = "普通文档内容。\n\n第二段。"
$defaultChunks = Split-IntoChunks -Text $defaultMd -Source "sample.txt" -DefaultDate "2024-06-01"
$dc = $defaultChunks | Select-Object -First 1
if ($dc.meta.title -ne 'sample') { $failed.Add("默认值 title 不是文件名(sample)") }
if ($dc.meta.doc_type -ne 'txt') { $failed.Add("默认值 doc_type 不是扩展名(txt)") }
if ($dc.meta.date -ne '2024-06-01') { $failed.Add("默认值 date 不是传入的 DefaultDate") }

if ($failed.Count -gt 0) {
    Write-Host "FAILED: 共 $($failed.Count) 项" -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "  - $f" }
    exit 1
}

Write-Host "PASSED: 共 $($chunks.Count) 个 chunks, frontmatter + 原子块保护 OK" -ForegroundColor Green
exit 0

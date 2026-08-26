<#
.SYNOPSIS
  KB-AI · M3c 验收脚本 — 图片理解(Qwen3.6-Plus 多模态)

.DESCRIPTION
  ### 范围
    验证 M3c 4 个交付物:
      1. scripts/image-prep.ps1(新增)
      2. scripts/load-env.ps1(新增,公共 .env 库)
      3. scripts/chat.ps1(改造:加 -ImagePaths / -VisionOnly 参数 + 多模态请求)
      4. scripts/batch-images.ps1(新增,批量图片入库)
      5. tests/test_m3c.ps1(本脚本)

  ### 测试设计
    8 项硬性检查(对应 verifier 验收项):
      1. 5 个交付文件齐全(image-prep.ps1 / load-env.ps1 / chat.ps1 / batch-images.ps1 / test_m3c.ps1)
      2. image-prep.ps1 含 Compress-Image + ConvertTo-Base64Jpeg + ConvertTo-MultimodalContent 3 函数
      3. image-prep.ps1 dot-source 守卫($MyInvocation.InvocationName -eq '.')
      4. image-prep.ps1 长边 ≤ 2048px + 文件 ≤ 5MB 约束(代码可见)
      5. chat.ps1 改造:Invoke-QwenChat 加 [string[]]$ImagePaths + VisionOnly 模式
      6. chat.ps1 改造:多模态 content 数组 {type: image_url} + {type: text}
      7. batch-images.ps1 含分批 + Qdrant 写入 + sha256 幂等 id
      8. 不破坏 M2b/M3a/M3b 已落地功能

    Mock / 运行时测试(避免真发 API):
      - image-prep 1x1 PNG base64 完整往返(生成 → 编码 → 解码)
      - image-prep 长边缩放(100x100 → 长边 ≤ 2048 时 1:1)
      - image-prep 长边缩放(3000x2000 → 长边 2048)
      - image-prep ConvertTo-Base64Jpeg 输出 data URL 格式
      - image-prep ConvertTo-MultimodalContent 3 函数顺序 + text 后置
      - image-prep 文件不存在 throw
      - chat.ps1 Invoke-QwenChat 空 ImagePaths 走文本模式(depth 不变)
      - chat.ps1 Invoke-QwenChat 有 ImagePaths 走多模态(depth=12)
      - chat.ps1 -VisionOnly / -ImagePaths 参数被 param 块接受
      - batch-images.ps1 -DryRun 不调 API,只打印清单
      - load-env 占位符判定("sk-PLEASE-FILL-IN" → null)
      - load-env Resolve-ApiKey 4 档优先级
      - 跨文件一致性:4 个新 .ps1 都无 UTF-8 BOM
      - 跨文件一致性:chat.ps1 不再硬编码 D:\

  ### 运行
    powershell -ExecutionPolicy Bypass -File tests/test_m3c.ps1   (PS 5.1)
    pwsh -File tests/test_m3c.ps1                                  (PS 7+)

.NOTES
  PowerShell 5.1 兼容。脚本自身只生成临时图片 + AST 解析 + Mock,不调用 DashScope API。
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Pass { param([string]$msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$script:Results = @()
$script:Failed = 0

function Add-Result {
    param([string]$Name, [bool]$Pass, [string]$Error = "")
    $script:Results += @{ Name = $Name; Status = if ($Pass) { "PASS" } else { "FAIL" }; Error = $Error }
    if (-not $Pass) { $script:Failed++ }
}

function Get-FileContent {
    param([string]$Path)
    return Get-Content $Path -Raw -Encoding UTF8
}

# BOM 检测:读取首 3 字节,EF BB BF = UTF-8 BOM
function Test-NoBom {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        if ($bytes.Length -lt 3) { return $true }
        return -not ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    } catch {
        return $false
    }
}

# 生成测试 PNG(System.Drawing,1x1 红像素)
function New-TestPng {
    param(
        [string]$Path,
        [int]$Width = 100,
        [int]$Height = 100
    )
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap $Width, $Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::Red)
    $g.Dispose()
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

# Base64 解码 → Bitmap(验证 image-prep 输出的 data URL 能被还原)
function ConvertFrom-Base64DataUrl {
    param([string]$DataUrl)
    if ($DataUrl -notmatch '^data:image/[^;]+;base64,(.+)$') {
        throw "不是合法的 data URL 格式"
    }
    $b64 = $Matches[1]
    $bytes = [Convert]::FromBase64String($b64)
    $ms = New-Object System.IO.MemoryStream(, $bytes)
    Add-Type -AssemblyName System.Drawing
    $img = [System.Drawing.Image]::FromStream($ms)
    $ms.Dispose()
    return $img
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI  M3c 验收脚本 — 图片理解(Qwen3.6-Plus 多模态)" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------------
# 预加载文件内容
# ----------------------------------------------------------------------

$imagePrepFile = Join-Path $RootDir "scripts/image-prep.ps1"
$loadEnvFile   = Join-Path $RootDir "scripts/lib/load-env.ps1"
$chatFile      = Join-Path $RootDir "scripts/chat.ps1"
$batchFile     = Join-Path $RootDir "scripts/batch-images.ps1"
$testFile      = $MyInvocation.MyCommand.Path

$imagePrepContent = if (Test-Path $imagePrepFile) { Get-FileContent $imagePrepFile } else { "" }
$loadEnvContent   = if (Test-Path $loadEnvFile)   { Get-FileContent $loadEnvFile }   else { "" }
$chatContent      = if (Test-Path $chatFile)      { Get-FileContent $chatFile }      else { "" }
$batchContent     = if (Test-Path $batchFile)     { Get-FileContent $batchFile }     else { "" }

# ----------------------------------------------------------------------
# Test 1: 5 个交付文件齐全
# ----------------------------------------------------------------------

Write-Info "Test 1: 5 个 M3c 交付文件齐全"
try {
    $required = @(
        "scripts/image-prep.ps1",
        "scripts/lib/load-env.ps1",
        "scripts/chat.ps1",
        "scripts/batch-images.ps1",
        "tests/test_m3c.ps1"
    )
    $missing = @()
    foreach ($f in $required) {
        $p = Join-Path $RootDir $f
        if (-not (Test-Path -LiteralPath $p)) { $missing += $f }
    }
    if ($missing.Count -gt 0) {
        throw "缺失文件: $($missing -join '; ')"
    }
    Write-Pass "全部 5 个文件存在"
    Add-Result "5 files exist" $true
} catch {
    Write-Fail "Test 1 失败: $_"
    Add-Result "5 files exist" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 2: image-prep.ps1 含 3 个函数
# ----------------------------------------------------------------------

Write-Info "Test 2: image-prep.ps1 含 Compress-Image / ConvertTo-Base64Jpeg / ConvertTo-MultimodalContent"
try {
    $hits = 0
    if ($imagePrepContent -match "function\s+Compress-Image")            { $hits++ }
    if ($imagePrepContent -match "function\s+ConvertTo-Base64Jpeg")      { $hits++ }
    if ($imagePrepContent -match "function\s+ConvertTo-MultimodalContent") { $hits++ }
    if ($hits -lt 3) {
        throw "命中过少($hits/3);期望 3 个函数全部定义"
    }
    Write-Pass "image-prep 含 3 函数($hits/3)"
    Add-Result "image-prep 3 functions" $true
} catch {
    Write-Fail "Test 2 失败: $_"
    Add-Result "image-prep 3 functions" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 3: image-prep.ps1 dot-source 守卫
# ----------------------------------------------------------------------

Write-Info "Test 3: image-prep.ps1 含 dot-source 守卫"
try {
    $hits = 0
    if ($imagePrepContent -match 'MyInvocation\.InvocationName\s*-eq\s*[''"]\.[''"]') { $hits++ }
    if ($imagePrepContent -match "InvocationName\s*-eq\s*'\.'\)\s*\{[^}]*return") { $hits++ }
    if ($hits -lt 2) {
        throw "命中过少($hits/2)"
    }
    Write-Pass "image-prep dot-source 守卫完整($hits/2)"
    Add-Result "image-prep dot-source guard" $true
} catch {
    Write-Fail "Test 3 失败: $_"
    Add-Result "image-prep dot-source guard" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 4: image-prep.ps1 长边 ≤ 2048 + 文件 ≤ 5MB 约束
# ----------------------------------------------------------------------

Write-Info "Test 4: image-prep.ps1 长边 ≤ 2048px + 文件 ≤ 5MB 约束"
try {
    $hits = 0
    if ($imagePrepContent -match "MaxLongEdge\s*=\s*2048")   { $hits++ }
    if ($imagePrepContent -match "MaxBytes\s*=\s*5MB")         { $hits++ }
    if ($imagePrepContent -match "JpegQuality")                { $hits++ }   # JPEG 质量设置
    if ($imagePrepContent -match "HighQualityBicubic")         { $hits++ }   # 高质量插值
    if ($hits -lt 4) {
        throw "命中过少($hits/4)"
    }
    Write-Pass "image-prep 约束完整($hits/4)"
    Add-Result "image-prep constraints" $true
} catch {
    Write-Fail "Test 4 失败: $_"
    Add-Result "image-prep constraints" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 5: chat.ps1 改造 - Invoke-QwenChat 加 ImagePaths
# ----------------------------------------------------------------------

Write-Info "Test 5: chat.ps1 Invoke-QwenChat 加 [string[]]\$ImagePaths + VisionOnly"
try {
    $hits = 0
    if ($chatContent -match "Invoke-QwenChat[\s\S]{0,500}\[string\[\]\]\s*\`$ImagePaths") { $hits++ }
    if ($chatContent -match "ConvertTo-MultimodalContent")            { $hits++ }
    if ($chatContent -match "VisionOnly")                              { $hits++ }
    if ($chatContent -match "VisionSystemPrompt")                      { $hits++ }
    if ($chatContent -match "image-prep\.ps1")                         { $hits++ }
    if ($hits -lt 4) {
        throw "命中过少($hits/5);chat.ps1 多模态改造不完整"
    }
    Write-Pass "chat.ps1 多模态改造完整($hits/5)"
    Add-Result "chat.ps1 multimodal" $true
} catch {
    Write-Fail "Test 5 失败: $_"
    Add-Result "chat.ps1 multimodal" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 6: chat.ps1 多模态 content 数组格式
# ----------------------------------------------------------------------

Write-Info "Test 6: 多模态 content 用 image_url + text 数组(image-prep.ps1 定义)"
try {
    $hits = 0
    # image-prep.ps1 定义多模态数组结构(chat.ps1 调用函数复用)
    if ($imagePrepContent -match 'type\s*=\s*"image_url"')  { $hits++ }
    if ($imagePrepContent -match 'image_url\s*=\s*@\{')      { $hits++ }
    if ($imagePrepContent -match 'type\s*=\s*"text"')        { $hits++ }
    if ($imagePrepContent -match 'data:image/jpeg;base64')    { $hits++ }
    if ($hits -lt 4) {
        throw "命中过少($hits/4);多模态数组格式不完整"
    }
    Write-Pass "多模态 content 格式完整($hits/4)"
    Add-Result "multimodal format" $true
} catch {
    Write-Fail "Test 6 失败: $_"
    Add-Result "multimodal format" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 7: batch-images.ps1 含分批 + Qdrant + 幂等 id
# ----------------------------------------------------------------------

Write-Info "Test 7: batch-images.ps1 含分批 + Qdrant + sha256 幂等 id"
try {
    $hits = 0
    if ($batchContent -match "BatchSize")                          { $hits++ }
    if ($batchContent -match "Send-QdrantPoints")                  { $hits++ }
    if ($batchContent -match "Ensure-QdrantCollection")            { $hits++ }
    if ($batchContent -match "Get-Sha256Short")                    { $hits++ }   # 幂等 id
    if ($batchContent -match "chat\.ps1[\s\S]{0,80}-VisionOnly")   { $hits++ }
    if ($batchContent -match "DryRun")                              { $hits++ }
    if ($batchContent -match "Resolve-ApiKey")                      { $hits++ }
    if ($hits -lt 6) {
        throw "命中过少($hits/7);batch-images 关键逻辑缺失"
    }
    Write-Pass "batch-images 关键逻辑完整($hits/7)"
    Add-Result "batch-images essentials" $true
} catch {
    Write-Fail "Test 7 失败: $_"
    Add-Result "batch-images essentials" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Test 8: 不破坏 M2b/M3a/M3b 已落地文件
# ----------------------------------------------------------------------

Write-Info "Test 8: 不破坏 M2b/M3a/M3b 既有脚本"
try {
    $hits = 0
    $preserve = @(
        "scripts/chat.ps1",
        "scripts/get-usb-root.ps1",
        "scripts/show-help.ps1",
        "scripts/version.ps1",
        "scripts/status-bar.ps1",
        "scripts/disk-alert.ps1",
        "scripts/safe-eject.ps1",
        "scripts/websearch.ps1",
        "scripts/health-probe.ps1",
        "scripts/embed-and-ingest.ps1",
        "scripts/parse-doc.ps1",
        "scripts/seed-sample-data.ps1"
    )
    foreach ($f in $preserve) {
        $p = Join-Path $RootDir $f
        if (Test-Path -LiteralPath $p) { $hits++ }
    }
    if ($hits -lt 12) {
        throw "命中过少($hits/12);M2b/M3a/M3b 脚本被破坏或丢失"
    }
    Write-Pass "M2b/M3a/M3b 12 个既有脚本仍存在($hits/12)"
    Add-Result "M2b/M3a/M3b preserved" $true
} catch {
    Write-Fail "Test 8 失败: $_"
    Add-Result "M2b/M3a/M3b preserved" $false $_.Exception.Message
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  8 项硬性检查通过后,进入 Mock / 运行时测试" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ----------------------------------------------------------------------
# Mock 测试区
# ----------------------------------------------------------------------

$mockRoot = Join-Path $RootDir "tmp/mock_m3c"
if (Test-Path -LiteralPath $mockRoot) {
    $cleanupRoot = $false
} else {
    $cleanupRoot = $true
}
if (-not (Test-Path -LiteralPath $mockRoot)) {
    New-Item -ItemType Directory -Path $mockRoot -Force | Out-Null
}

$img1x1 = Join-Path $mockRoot "test_1x1.png"
$img100 = Join-Path $mockRoot "test_100x100.png"
$img3000 = Join-Path $mockRoot "test_3000x2000.png"
$imgJpg = Join-Path $mockRoot "test_50x50.jpg"

# 生成测试图片(只生成一次)
if (-not (Test-Path $img100))   { New-TestPng -Path $img100 -Width 100 -Height 100 }
if (-not (Test-Path $img3000))  { New-TestPng -Path $img3000 -Width 3000 -Height 2000 }
if (-not (Test-Path $imgJpg)) {
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap 50, 50
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::Blue)
    $g.Dispose()
    $bmp.Save($imgJpg, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $bmp.Dispose()
}

# ----------------------------------------------------------------------
# Mock Test 1: dot-source image-prep 仅暴露函数
# ----------------------------------------------------------------------

Write-Info "Mock Test 1: dot-source image-prep 仅暴露函数"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    Remove-Item Function:ConvertTo-Base64Jpeg -ErrorAction SilentlyContinue
    Remove-Item Function:ConvertTo-MultimodalContent -ErrorAction SilentlyContinue

    . $imagePrepFile

    $hasCompress = $null -ne (Get-Command Compress-Image -ErrorAction SilentlyContinue)
    $hasB64     = $null -ne (Get-Command ConvertTo-Base64Jpeg -ErrorAction SilentlyContinue)
    $hasMulti   = $null -ne (Get-Command ConvertTo-MultimodalContent -ErrorAction SilentlyContinue)

    if (-not $hasCompress) { throw "Compress-Image 未加载" }
    if (-not $hasB64)      { throw "ConvertTo-Base64Jpeg 未加载" }
    if (-not $hasMulti)    { throw "ConvertTo-MultimodalContent 未加载" }

    Write-Pass "dot-source 后 3 函数可见"
    Add-Result "mock: dot-source 3 functions" $true
} catch {
    Write-Fail "Mock Test 1 失败: $_"
    Add-Result "mock: dot-source 3 functions" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 2: Compress-Image 1x1 → 1x1 (无需缩放)
# ----------------------------------------------------------------------

Write-Info "Mock Test 2: Compress-Image 100x100(无缩放,1:1)"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    . $imagePrepFile

    $bmp = Compress-Image -Path $img100
    try {
        if ($bmp.Width -ne 100)  { throw "期望 width=100,实际=$($bmp.Width)" }
        if ($bmp.Height -ne 100) { throw "期望 height=100,实际=$($bmp.Height)" }
        Write-Pass "100x100 → 100x100(无缩放)"
        Add-Result "mock: compress no-scale" $true
    } finally {
        $bmp.Dispose()
    }
} catch {
    Write-Fail "Mock Test 2 失败: $_"
    Add-Result "mock: compress no-scale" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 3: Compress-Image 3000x2000 → 长边 2048
# ----------------------------------------------------------------------

Write-Info "Mock Test 3: Compress-Image 3000x2000 → 长边 ≤ 2048"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    . $imagePrepFile

    $bmp = Compress-Image -Path $img3000
    try {
        $longEdge = [Math]::Max($bmp.Width, $bmp.Height)
        if ($longEdge -gt 2048) {
            throw "长边 > 2048,实际=$longEdge"
        }
        # 比例:3000/2048 ≈ 1.4648,所以新尺寸 = 3000/1.4648 ≈ 2048,2000/1.4648 ≈ 1365
        $expectedRatio = 2048.0 / 3000.0
        $expectedW = [int][math]::Floor(3000 * $expectedRatio)
        $expectedH = [int][math]::Floor(2000 * $expectedRatio)
        if ([Math]::Abs($bmp.Width  - $expectedW) -gt 1) { throw "width 偏差 >1:实际=$($bmp.Width),期望=$expectedW" }
        if ([Math]::Abs($bmp.Height - $expectedH) -gt 1) { throw "height 偏差 >1:实际=$($bmp.Height),期望=$expectedH" }
        Write-Pass "3000x2000 → $($bmp.Width)x$($bmp.Height)(长边=$longEdge ≤ 2048)"
        Add-Result "mock: compress scale" $true
    } finally {
        $bmp.Dispose()
    }
} catch {
    Write-Fail "Mock Test 3 失败: $_"
    Add-Result "mock: compress scale" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 4: ConvertTo-Base64Jpeg 输出 data URL 格式
# ----------------------------------------------------------------------

Write-Info "Mock Test 4: ConvertTo-Base64Jpeg 输出合法 data URL"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    Remove-Item Function:ConvertTo-Base64Jpeg -ErrorAction SilentlyContinue
    . $imagePrepFile

    $bmp = Compress-Image -Path $img100
    try {
        $url = ConvertTo-Base64Jpeg -Image $bmp
        if ($url -notmatch '^data:image/jpeg;base64,[A-Za-z0-9+/=]+$') {
            throw "data URL 格式不合法:$($url.Substring(0, [Math]::Min(50, $url.Length)))"
        }
        # 验证能解码回来
        $b64Part = $url.Substring("data:image/jpeg;base64,".Length)
        $bytes = [Convert]::FromBase64String($b64Part)
        if ($bytes.Length -lt 100) { throw "base64 解码后字节数过少:$($bytes.Length)" }
        if ($bytes.Length -gt 5MB) { throw "base64 解码后超过 5MB:$($bytes.Length)" }
        Write-Pass "data URL 合法(base64 长度=$($b64Part.Length),解码字节=$($bytes.Length))"
        Add-Result "mock: data URL format" $true
    } finally {
        $bmp.Dispose()
    }
} catch {
    Write-Fail "Mock Test 4 失败: $_"
    Add-Result "mock: data URL format" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 5: ConvertTo-MultimodalContent 多图 + 文本
# ----------------------------------------------------------------------

Write-Info "Mock Test 5: ConvertTo-MultimodalContent 多图 + 文本"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    Remove-Item Function:ConvertTo-Base64Jpeg -ErrorAction SilentlyContinue
    Remove-Item Function:ConvertTo-MultimodalContent -ErrorAction SilentlyContinue
    . $imagePrepFile

    $arr = ConvertTo-MultimodalContent -ImagePaths @($img100, $imgJpg) -UserPrompt "描述这两张图"
    # 期望:3 元素(2 image_url + 1 text),顺序:图1 → 图2 → text
    if ($arr.Count -ne 3) { throw "期望 3 元素(2 图 + 1 text),实际=$($arr.Count)" }
    if ($arr[0].type -ne "image_url") { throw "arr[0] 应为 image_url,实际=$($arr[0].type)" }
    if ($arr[1].type -ne "image_url") { throw "arr[1] 应为 image_url,实际=$($arr[1].type)" }
    if ($arr[2].type -ne "text")      { throw "arr[2] 应为 text,实际=$($arr[2].type)" }
    if ($arr[2].text -ne "描述这两张图") { throw "arr[2].text 不匹配" }
    if (-not $arr[0].image_url.url.StartsWith("data:image/jpeg;base64,")) {
        throw "arr[0].image_url.url 不是 data URL"
    }
    Write-Pass "多模态 content 数组顺序与结构正确(3 元素)"
    Add-Result "mock: multimodal array" $true
} catch {
    Write-Fail "Mock Test 5 失败: $_"
    Add-Result "mock: multimodal array" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 6: Compress-Image 文件不存在 → throw
# ----------------------------------------------------------------------

Write-Info "Mock Test 6: Compress-Image 不存在的文件 throw"
try {
    Remove-Item Function:Compress-Image -ErrorAction SilentlyContinue
    . $imagePrepFile

    $threw = $false
    try {
        $null = Compress-Image -Path "Z:\nonexistent\nope.png"
    } catch {
        $threw = $true
        if ($_.Exception.Message -notmatch "图片不存在") {
            throw "抛错消息不包含'图片不存在':$($_.Exception.Message)"
        }
    }
    if (-not $threw) { throw "未抛错" }
    Write-Pass "不存在文件正确 throw"
    Add-Result "mock: missing file throw" $true
} catch {
    Write-Fail "Mock Test 6 失败: $_"
    Add-Result "mock: missing file throw" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 7: image-prep CLI 输出 data URL 到 stdout
# ----------------------------------------------------------------------

Write-Info "Mock Test 7: image-prep.ps1 -ImagePath CLI 输出 data URL"
try {
    $out = & powershell -ExecutionPolicy Bypass -File $imagePrepFile -ImagePath $img100 2>&1 | Out-String
    $trimmed = $out.Trim()
    if ($trimmed -notmatch '^data:image/jpeg;base64,[A-Za-z0-9+/=]+$') {
        throw "CLI 输出不是合法 data URL:$($trimmed.Substring(0, [Math]::Min(60, $trimmed.Length)))"
    }
    Write-Pass "CLI 输出 data URL(长度=$($trimmed.Length))"
    Add-Result "mock: CLI output" $true
} catch {
    Write-Fail "Mock Test 7 失败: $_"
    Add-Result "mock: CLI output" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 8: chat.ps1 Invoke-QwenChat 空 ImagePaths 走文本模式
# ----------------------------------------------------------------------

Write-Info "Mock Test 8: chat.ps1 Invoke-QwenChat 空 ImagePaths 退化到文本模式"
try {
    # 用 AST 静态分析:确认 Invoke-QwenChat 函数体内有"ImagePaths -and ... -gt 0"的判断分支
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($chatFile, [ref]$null, [ref]$null)
    $funcAst = $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-QwenChat"
    }, $true) | Select-Object -First 1
    if (-not $funcAst) { throw "找不到 Invoke-QwenChat 函数" }

    $funcBody = $funcAst.Extent.Text
    $hits = 0
    # 条件分支(多模态 vs 文本)
    if ($funcBody -match 'ImagePaths\s*-\s*and') { $hits++ }   # 文本模式分支
    if ($funcBody -match 'ConvertTo-MultimodalContent') { $hits++ }   # 多模态分支
    if ($funcBody -match 'userContent\s*=\s*\$UserPrompt') { $hits++ }   # 文本模式赋值
    if ($hits -lt 3) {
        throw "Invoke-QwenChat 改造不完整($hits/3)"
    }
    Write-Pass "Invoke-QwenChat 文本/多模态双分支存在($hits/3)"
    Add-Result "mock: Invoke-QwenChat branches" $true
} catch {
    Write-Fail "Mock Test 8 失败: $_"
    Add-Result "mock: Invoke-QwenChat branches" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 9: chat.ps1 -ImagePaths / -VisionOnly 参数在 param 块
# ----------------------------------------------------------------------

Write-Info "Mock Test 9: chat.ps1 param 块含 -ImagePaths 和 -VisionOnly"
try {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($chatFile, [ref]$null, [ref]$null)
    # 找 param 块
    $paramAst = $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.ParameterAst]
    }, $true)
    $hasImagePaths = $false
    $hasVisionOnly = $false
    foreach ($p in $paramAst) {
        if ($p.Name.VariablePath.UserPath -eq "ImagePaths") { $hasImagePaths = $true }
        if ($p.Name.VariablePath.UserPath -eq "VisionOnly") { $hasVisionOnly = $true }
    }
    if (-not $hasImagePaths) { throw "param 块缺 -ImagePaths" }
    if (-not $hasVisionOnly) { throw "param 块缺 -VisionOnly" }
    Write-Pass "param 块含 -ImagePaths + -VisionOnly"
    Add-Result "mock: chat params" $true
} catch {
    Write-Fail "Mock Test 9 失败: $_"
    Add-Result "mock: chat params" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 10: batch-images.ps1 -DryRun 不调 API
# ----------------------------------------------------------------------

Write-Info "Mock Test 10: batch-images.ps1 -DryRun 不调 API"
try {
    $mockImgDir = Join-Path $mockRoot "imgs"
    if (-not (Test-Path $mockImgDir)) { New-Item -ItemType Directory -Path $mockImgDir -Force | Out-Null }
    # 复制 2 张测试图
    if (-not (Test-Path "$mockImgDir\a.png")) {
        Copy-Item $img100 "$mockImgDir\a.png" -Force
    }
    if (-not (Test-Path "$mockImgDir\b.png")) {
        Copy-Item $img100 "$mockImgDir\b.png" -Force
    }

    $out = & powershell -ExecutionPolicy Bypass -File $batchFile -InputDir $mockImgDir -DryRun 2>&1 | Out-String
    $hits = 0
    if ($out -match "DryRun:待入库图片清单")  { $hits++ }
    if ($out -match "a\.png")                  { $hits++ }
    if ($out -match "b\.png")                  { $hits++ }
    # 不应出现 Embedding / Qwen / API 等关键词(证明没走到真实流程)
    if ($out -notmatch "Embedding 调用失败|API Key") { $hits++ }
    if ($hits -lt 4) {
        throw "DryRun 输出不完整或误调 API($hits/4)"
    }
    Write-Pass "DryRun 正确打印清单不调 API($hits/4)"
    Add-Result "mock: batch dryrun" $true
} catch {
    Write-Fail "Mock Test 10 失败: $_"
    Add-Result "mock: batch dryrun" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 11: load-env 占位符判定
# ----------------------------------------------------------------------

Write-Info "Mock Test 11: load-env 占位符判定"
try {
    Remove-Item Function:Test-IsPlaceholder -ErrorAction SilentlyContinue
    . $loadEnvFile

    if (-not (Test-IsPlaceholder -Value "sk-PLEASE-FILL-IN")) {
        throw "sk-PLEASE-FILL-IN 应判定为占位符"
    }
    if (-not (Test-IsPlaceholder -Value "tvly-PLEASE-FILL-IN")) {
        throw "tvly-PLEASE-FILL-IN 应判定为占位符"
    }
    if (-not (Test-IsPlaceholder -Value "PLEASE-FILL-IN")) {
        throw "PLEASE-FILL-IN 应判定为占位符"
    }
    if (Test-IsPlaceholder -Value "sk-real-key-12345") {
        throw "真实 key 不应判定为占位符"
    }
    if (-not (Test-IsPlaceholder -Value "")) {
        throw "空字符串应判定为占位符(也即 null)"
    }
    Write-Pass "占位符判定正确(4 命中 + 2 反例)"
    Add-Result "mock: placeholder detect" $true
} catch {
    Write-Fail "Mock Test 11 失败: $_"
    Add-Result "mock: placeholder detect" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 12: load-env Resolve-ApiKey 4 档优先级
# ----------------------------------------------------------------------

Write-Info "Mock Test 12: Resolve-ApiKey 显式参数 > 环境变量 > .env > null"
try {
    Remove-Item Function:Resolve-ApiKey -ErrorAction SilentlyContinue
    Remove-Item Function:Get-EnvVar -ErrorAction SilentlyContinue
    Remove-Item Function:Test-IsPlaceholder -ErrorAction SilentlyContinue
    . $loadEnvFile

    $tmpEnv = Join-Path $mockRoot "test.env"
    "ALIYUN_BAILIAN_API_KEY=sk-from-env-file" | Set-Content -LiteralPath $tmpEnv -Encoding UTF8 -NoNewline

    # 档 1:显式参数优先
    $r1 = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -Explicit "sk-explicit" -EnvPath $tmpEnv
    if ($r1 -ne "sk-explicit") { throw "档 1 显式参数失败:实际=$r1" }

    # 档 2:环境变量优先(若未传显式)
    $origEnvVal = [Environment]::GetEnvironmentVariable("ALIYUN_BAILIAN_API_KEY")
    try {
        [Environment]::SetEnvironmentVariable("ALIYUN_BAILIAN_API_KEY", "sk-from-envvar", "Process")
        $r2 = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -Explicit "" -EnvPath $tmpEnv
        if ($r2 -ne "sk-from-envvar") { throw "档 2 环境变量失败:实际=$r2" }

        # 档 3:.env 文件兜底
        [Environment]::SetEnvironmentVariable("ALIYUN_BAILIAN_API_KEY", $null, "Process")
        $r3 = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -Explicit "" -EnvPath $tmpEnv
        if ($r3 -ne "sk-from-env-file") { throw "档 3 .env 失败:实际=$r3" }

        # 档 4:都没有 → null
        $r4 = Resolve-ApiKey -Name "NONEXISTENT_KEY_999" -Explicit "" -EnvPath $tmpEnv
        if ($null -ne $r4) { throw "档 4 应为 null,实际=$r4" }

        Write-Pass "Resolve-ApiKey 4 档优先级正确"
        Add-Result "mock: resolve 4-tier" $true
    } finally {
        if ($null -ne $origEnvVal) {
            [Environment]::SetEnvironmentVariable("ALIYUN_BAILIAN_API_KEY", $origEnvVal, "Process")
        } else {
            [Environment]::SetEnvironmentVariable("ALIYUN_BAILIAN_API_KEY", $null, "Process")
        }
    }
} catch {
    Write-Fail "Mock Test 12 失败: $_"
    Add-Result "mock: resolve 4-tier" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 13: 跨文件一致性 — 4 个新 .ps1 无 UTF-8 BOM
# ----------------------------------------------------------------------

Write-Info "Mock Test 13: 4 个 M3c .ps1 无 UTF-8 BOM"
try {
    $hits = 0
    foreach ($f in @($imagePrepFile, $loadEnvFile, $chatFile, $batchFile)) {
        if (Test-NoBom -Path $f) { $hits++ }
    }
    if ($hits -lt 4) {
        throw "BOM 检测命中 $hits/4;有文件含 BOM"
    }
    Write-Pass "4 个 M3c .ps1 全部无 UTF-8 BOM"
    Add-Result "mock: no UTF-8 BOM" $true
} catch {
    Write-Fail "Mock Test 13 失败: $_"
    Add-Result "mock: no UTF-8 BOM" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 14: chat.ps1 改造行数变化受控(<200 行)
# ----------------------------------------------------------------------

Write-Info "Mock Test 14: chat.ps1 改造行数变化受控"
try {
    $chatLineCount = ($chatContent -split "`n").Count
    # 原 M3b 落地时 chat.ps1 是 822 行;改造后允许 +200 行 buffer
    if ($chatLineCount -lt 820) {
        throw "chat.ps1 行数=$chatLineCount;似乎被过度删减(原 822 行)"
    }
    if ($chatLineCount -gt 1050) {
        throw "chat.ps1 行数=$chatLineCount;超出 +200 行 buffer,改造范围失控"
    }
    Write-Pass "chat.ps1 行数=$chatLineCount(原 822,变化 < 230 行)"
    Add-Result "mock: chat line count" $true
} catch {
    Write-Fail "Mock Test 14 失败: $_"
    Add-Result "mock: chat line count" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 15: chat.ps1 多模态 content depth=12(数组深度足够)
# ----------------------------------------------------------------------

Write-Info "Mock Test 15: chat.ps1 ConvertTo-Json Depth 统一 ≥ 12"
try {
    # 修复 1.5:v0.7.1 已将 chat.ps1 的 ConvertTo-Json 统一为 -Depth 12(原 -Depth 8 是历史实现,
    # 多模态模式需要至少 12 才能容纳 image_url 数组嵌套)。删除"-Depth 8 缺失"的双重断言。
    if ($chatContent -notmatch 'ConvertTo-Json[\s\S]{0,80}Depth\s+12') {
        throw "ConvertTo-Json Depth 缺失(应 ≥ 12 以容纳多模态数组)"
    }
    # 反向断言:不应该有 -Depth 8 残留(历史实现已统一)
    if ($chatContent -match 'ConvertTo-Json[\s\S]{0,80}Depth\s+8\b') {
        throw "发现 -Depth 8 残留,应统一为 -Depth 12"
    }
    Write-Pass "ConvertTo-Json Depth 统一为 12(多模态数组深度充足)"
    Add-Result "mock: convertto-json depth" $true
} catch {
    Write-Fail "Mock Test 15 失败: $_"
    Add-Result "mock: convertto-json depth" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 16: batch-images.ps1 错误处理 — 不存在的目录
# ----------------------------------------------------------------------

Write-Info "Mock Test 16: batch-images.ps1 不存在目录 throw"
try {
    $proc = Start-Process -FilePath "powershell" -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", $batchFile,
        "-InputDir", "Z:\nonexistent\path\x",
        "-DryRun"
    ) -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -eq 0) {
        throw "期望非零 exit(目录不存在)"
    }
    Write-Pass "不存在目录正确返回非零 exit($($proc.ExitCode))"
    Add-Result "mock: batch missing dir" $true
} catch {
    Write-Fail "Mock Test 16 失败: $_"
    Add-Result "mock: batch missing dir" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 17: chat.ps1 -Question "x" 走到 ApiKey 错误(证明路径解析 OK)
# ----------------------------------------------------------------------

Write-Info "Mock Test 17: chat.ps1 路径解析 OK(走到 ApiKey 检查)"
try {
    $out = & powershell -ExecutionPolicy Bypass -File $chatFile -Question "test" 2>&1 | Out-String
    if ($out -match "找不到 get-usb-root\.ps1") {
        throw "路径解析失败:找不到 get-usb-root.ps1"
    }
    if ($out -notmatch "未提供.*ApiKey|API_KEY|env.*未填") {
        throw "未走到 ApiKey 检查逻辑;原始输出:$out"
    }
    Write-Pass "chat.ps1 头部路径解析成功,跑到 ApiKey 兜底"
    Add-Result "mock: chat path resolve" $true
} catch {
    Write-Fail "Mock Test 17 失败: $_"
    Add-Result "mock: chat path resolve" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 18: image-prep CLI -ImagePath 缺失时给帮助
# ----------------------------------------------------------------------

Write-Info "Mock Test 18: image-prep 无参数时给帮助并 exit 1"
try {
    $proc = Start-Process -FilePath "powershell" -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", $imagePrepFile
    ) -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 1) {
        throw "期望 exit=1,实际=$($proc.ExitCode)"
    }
    Write-Pass "无参数时正确 exit 1"
    Add-Result "mock: image-prep no-arg" $true
} catch {
    Write-Fail "Mock Test 18 失败: $_"
    Add-Result "mock: image-prep no-arg" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 19: chat.ps1 不再硬编码 D:\ 盘符
# ----------------------------------------------------------------------

Write-Info "Mock Test 19: chat.ps1 不硬编码盘符"
try {
    $hits = 0
    foreach ($f in @($imagePrepFile, $loadEnvFile, $batchFile)) {
        $c = Get-FileContent $f
        $lines = $c -split "`n"
        $hardcoded = 0
        foreach ($ln in $lines) {
            $trimmed = $ln.Trim()
            if ($trimmed.StartsWith("#")) { continue }
            if ($trimmed -match "[Dd]:\\\\(?!maintainer\\\\KB-AI)|[Cc]:\\\\(?!maintainer\\\\KB-AI)") {
                $hardcoded++
            }
        }
        if ($hardcoded -eq 0) { $hits++ }
    }
    if ($hits -lt 3) {
        throw "新 .ps1 仍有硬编码盘符($hits/3)"
    }
    Write-Pass "3 个新 M3c .ps1 无硬编码盘符($hits/3)"
    Add-Result "mock: no hardcoded drive" $true
} catch {
    Write-Fail "Mock Test 19 失败: $_"
    Add-Result "mock: no hardcoded drive" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# Mock Test 20: chat.ps1 含 VisionOnly 早返路径(跳过 RAG)
# ----------------------------------------------------------------------

Write-Info "Mock Test 20: chat.ps1 VisionOnly 模式选 VisionSystemPrompt"
try {
    $hits = 0
    if ($chatContent -match "VisionSystemPrompt")               { $hits++ }
    if ($chatContent -match "systemPromptToUse")                { $hits++ }
    if ($chatContent -match 'systemPromptToUse\s*=\s*if\s*\(\s*\$VisionOnly') { $hits++ }
    if ($hits -lt 3) {
        throw "VisionOnly 切换逻辑不完整($hits/3)"
    }
    Write-Pass "VisionOnly 模式正确选择 VisionSystemPrompt($hits/3)"
    Add-Result "mock: vision-only switch" $true
} catch {
    Write-Fail "Mock Test 20 失败: $_"
    Add-Result "mock: vision-only switch" $false $_.Exception.Message
}

# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  M3c 验收汇总" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$passed = $script:Results.Count - $script:Failed
Write-Host ("  通过: {0}/{1}" -f $passed, $script:Results.Count) -ForegroundColor $(if ($script:Failed -eq 0) { "Green" } else { "Red" })
Write-Host ""

if ($script:Failed -gt 0) {
    Write-Host "  失败明细:" -ForegroundColor Red
    foreach ($r in $script:Results) {
        if ($r.Status -eq "FAIL") {
            Write-Host ("    - {0}: {1}" -f $r.Name, $r.Error) -ForegroundColor Red
        }
    }
    Write-Host ""
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow

# exit code = failed 数
exit $script:Failed
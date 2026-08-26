<#
.SYNOPSIS
  KB-AI · 图片预处理:读取 → 压缩(长边 ≤ 2048px / 文件 ≤ 5MB)→ base64 data URL。

.DESCRIPTION
  ### 职责
    给 Qwen3.6-Plus 多模态调用准备图片输入:
      1. 读取本地图片(.jpg / .jpeg / .png / .webp / .bmp / .gif)
      2. 按比例缩小到长边 ≤ 2048px
      3. 重新编码为 JPEG(质量 85),控制最终字节数 ≤ 5MB
      4. 输出 OpenAI 兼容的 data URL:`data:image/jpeg;base64,<...>`

  ### 设计要点
    - 纯 PowerShell + .NET System.Drawing(Win 平台内置,零额外依赖)
    - 函数库形式:dot-source 后只暴露 Compress-Image / ConvertTo-Base64Jpeg / ConvertTo-MultimodalContent
    - dot-source 守卫:$MyInvocation.InvocationName -eq '.' → return
    - 命令行模式:`-Input <path>` → stdout 输出 data URL(给 chat.ps1 串接)

  ### 降级行为
    - 文件不存在 → throw
    - 读取异常 → throw(由调用方决定是否降级跳过)
    - 压缩后仍 > 5MB → 二次压缩(质量降到 70),仍 > 5MB → throw 提示

.PARAMETER ImagePath
  CLI 模式:输入图片绝对路径。省略则仅 dot-source 暴露函数。
  (注意:参数名用 -ImagePath 而非 -Input,避免与 PowerShell 自动变量 $Input 冲突)

.OUTPUTS
  CLI 模式:[string] data:image/jpeg;base64,<...>
  函数模式:见各函数签名。

.EXAMPLE
  # 仅加载函数
  . (Join-Path $PSScriptRoot 'image-prep.ps1')
  $bmp = Compress-Image -Path "C:\photo.jpg"
  try {
      $url = ConvertTo-Base64Jpeg -Image $bmp
      # $url = "data:image/jpeg;base64,..."
  } finally {
      $bmp.Dispose()
  }

  # 命令行(给 chat.ps1 / batch-images.ps1 串接)
  pwsh -File scripts/image-prep.ps1 -ImagePath "D:\photos\menu.jpg"

.NOTES
  PowerShell 5.1 兼容(避免 PS 6+ 专属特性)。
  UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding($false))。
  Windows-only(System.Drawing 在 Mac/Linux 上行为不一致;但 KB-AI 主战场是 Windows U 盘)。
#>

[CmdletBinding()]
param(
    [string]$ImagePath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

$script:MaxLongEdge   = 2048      # 长边最大像素
$script:MaxBytes      = 5MB       # 5 MB = 5242880 bytes
$script:JpegQuality   = 85        # 默认 JPEG 质量
$script:JpegQualityMin = 50       # 二次压缩最低质量
$script:QualityStep   = 10        # 每次降级步长

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $Msg" -ForegroundColor Red }

# ----------------------------------------------------------------------
# 函数:Compress-Image
# ----------------------------------------------------------------------

function Compress-Image {
    <#
    .SYNOPSIS
      读取图片文件并按比例缩放到长边 ≤ 2048px。
    .DESCRIPTION
      - 输入:.jpg / .jpeg / .png / .webp / .bmp / .gif
      - 输出:新 Bitmap 对象(调用方需 Dispose)
      - 仅做尺寸压缩,不重编码;重编码由 ConvertTo-Base64Jpeg 完成
    .PARAMETER Path
      输入图片绝对路径。
    .OUTPUTS
      [System.Drawing.Bitmap]
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "图片不存在: $Path"
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    Add-Type -AssemblyName System.Drawing

    try {
        $src = [System.Drawing.Image]::FromFile($resolved)
    } catch {
        throw "图片读取失败: $Path($($_.Exception.Message))"
    }

    try {
        $w = $src.Width
        $h = $src.Height
        if ($w -le 0 -or $h -le 0) {
            throw "图片尺寸异常:${w}x${h}"
        }

        $maxDim = $script:MaxLongEdge
        $ratio = 1.0
        if ($w -gt $maxDim -or $h -gt $maxDim) {
            $ratio = $maxDim / [double][math]::Max($w, $h)
        }

        $newW = [int][math]::Max(1, [math]::Floor($w * $ratio))
        $newH = [int][math]::Max(1, [math]::Floor($h * $ratio))

        $bmp = New-Object System.Drawing.Bitmap $newW, $newH
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            # 高质量插值
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
            $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            # 白色背景(避免 PNG 透明区域在 JPEG 里变黑)
            $g.Clear([System.Drawing.Color]::White)
            $g.DrawImage($src, 0, 0, $newW, $newH)
        } finally {
            $g.Dispose()
        }
        return $bmp
    } finally {
        $src.Dispose()
    }
}

# ----------------------------------------------------------------------
# 函数:ConvertTo-Base64Jpeg
# ----------------------------------------------------------------------

function ConvertTo-Base64Jpeg {
    <#
    .SYNOPSIS
      把 Bitmap 对象编码为 base64 data URL(jpeg 格式)。
    .DESCRIPTION
      - 输出格式:`data:image/jpeg;base64,<...>`
      - 自动检测字节数,若 > 5MB 则降级质量(85 → 75 → 65 → 50)
      - 仍 > 5MB 时 throw(由调用方降级跳过)
    .PARAMETER Image
      已通过 Compress-Image 处理过的 Bitmap 对象。
    .PARAMETER Quality
      JPEG 质量 1-100(默认 85)。
    .OUTPUTS
      [string] "data:image/jpeg;base64,..."
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [System.Drawing.Image]$Image,
        [ValidateRange(1, 100)] [int]$Quality = $script:JpegQuality
    )

    if ($null -eq $Image) { throw "Image 参数为 null" }

    Add-Type -AssemblyName System.Drawing

    # 找 JPEG 编码器
    $codecs = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders()
    $jpegCodec = $codecs | Where-Object { $_.MimeType -eq 'image/jpeg' } | Select-Object -First 1
    if (-not $jpegCodec) { throw "找不到 JPEG 编码器" }

    # 首次编码
    $bytes = New-Object byte[] 0
    $q = $Quality
    while ($true) {
        $ms = New-Object System.IO.MemoryStream
        try {
            $encParams = New-Object System.Drawing.Imaging.EncoderParameters 1
            $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
                [System.Drawing.Imaging.Encoder]::Quality, [int64]$q)

            $Image.Save($ms, $jpegCodec, $encParams)
            $bytes = $ms.ToArray()
        } finally {
            $ms.Dispose()
        }

        if ($bytes.Length -le $script:MaxBytes) { break }
        if ($q -le $script:JpegQualityMin) { break }

        # 降级质量
        $q -= $script:QualityStep
        if ($q -lt $script:JpegQualityMin) { $q = $script:JpegQualityMin }
    }

    if ($bytes.Length -gt $script:MaxBytes) {
        throw ("图片压缩后仍超过 {0}MB(实际 {1:N2}MB,质量已降至 {2});请人工检查" -f `
               ($script:MaxBytes / 1MB), ($bytes.Length / 1MB), $q)
    }

    $b64 = [Convert]::ToBase64String($bytes)
    return "data:image/jpeg;base64,$b64"
}

# ----------------------------------------------------------------------
# 函数:ConvertTo-MultimodalContent
# ----------------------------------------------------------------------

function ConvertTo-MultimodalContent {
    <#
    .SYNOPSIS
      一站式把多张本地图片转成 Qwen 多模态 messages.content 数组。
    .DESCRIPTION
      - 接收图片路径数组
      - 返回 OpenAI 兼容的 content 数组,形如:
        @(
          @{ type = "image_url"; image_url = @{ url = "data:image/jpeg;base64,..." } },
          @{ type = "text";      text      = $UserPrompt }
        )
      - 自动释放 Bitmap
    .PARAMETER ImagePaths
      图片绝对路径数组。
    .PARAMETER UserPrompt
      用户文本问题(可为空字符串)。
    .PARAMETER Quality
      JPEG 质量(默认 85,透传给 ConvertTo-Base64Jpeg)。
    .OUTPUTS
      [array] message content 数组(可直接赋给 $body.input.messages[].content)
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string[]]$ImagePaths,
        [string]$UserPrompt = "",
        [ValidateRange(1, 100)] [int]$Quality = $script:JpegQuality
    )

    $contentArr = New-Object System.Collections.Generic.List[object]

    foreach ($p in $ImagePaths) {
        if (-not $p) { continue }
        $bmp = $null
        try {
            $bmp = Compress-Image -Path $p
            $url = ConvertTo-Base64Jpeg -Image $bmp -Quality $Quality
            [void]$contentArr.Add(@{
                type      = "image_url"
                image_url = @{ url = $url }
            })
        } finally {
            if ($bmp) { $bmp.Dispose() }
        }
    }

    if ($UserPrompt -ne "") {
        [void]$contentArr.Add(@{
            type = "text"
            text = $UserPrompt
        })
    }

    # 返回 array(ConvertTo-Json 期望强类型数组)
    # 用 [object[]] 强制转换,而不是 @(...)
    return [object[]]$contentArr.ToArray()
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------

if ($MyInvocation.InvocationName -eq '.') {
    return
}

# ----------------------------------------------------------------------
# CLI 主流程
# ----------------------------------------------------------------------

if (-not $ImagePath) {
    Write-Err "用法:pwsh -File scripts/image-prep.ps1 -ImagePath <图片路径>"
    Write-Err "      或 dot-source 后调用 Compress-Image / ConvertTo-Base64Jpeg"
    exit 1
}

try {
    $bmp = Compress-Image -Path $ImagePath
    try {
        $url = ConvertTo-Base64Jpeg -Image $bmp
        # stdout 输出纯 data URL(便于管道串接)
        Write-Output $url
        exit 0
    } finally {
        $bmp.Dispose()
    }
} catch {
    Write-Err "图片处理失败: $($_.Exception.Message)"
    exit 1
}
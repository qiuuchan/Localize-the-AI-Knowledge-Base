<#
.SYNOPSIS
  KB-AI · 图片描述生成:调用百炼 Qwen-VL 为单张图片生成中文文本描述。

.DESCRIPTION
  输入本地图片路径,输出一段纯文本描述。描述包含:
    - 可见文字提取(海报/截图/菜单等)
    - 图表数据趋势和关键数字
    - 场景/人物/物体描述(照片类)
  输出可直接作为 chunk 文本写入 knowledge base。

.PARAMETER ImagePath
  图片绝对路径(.png/.jpg/.jpeg/.webp/.bmp/.gif)

.PARAMETER Model
  百炼 vision 模型,默认 qwen-vl-plus(性价比最高)。可选 qwen-vl-max-latest。

.PARAMETER MaxTokens
  描述最大 token 数,默认 1500。

.EXAMPLE
  pwsh -File scripts/image-caption.ps1 -ImagePath "E:\\data\\uploads\\menu.jpg"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ImagePath,
    [string]$Model = "qwen-vl-max",
    [int]$MaxTokens = 1500
)

$ErrorActionPreference = "Stop"

# 加载 .env 与 API key 解析
. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')

# 加载图片压缩/转 base64 函数
# image-prep.ps1 也有 $ImagePath 参数,点源时会覆盖当前值,先保存
$imagePrepScript = Join-Path $PSScriptRoot 'image-prep.ps1'
$originalImagePath = $ImagePath
. $imagePrepScript
$ImagePath = $originalImagePath

# 关闭默认代理,避免 HTTPS 握手问题(同 chat.ps1)
[System.Net.WebRequest]::DefaultWebProxy = $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 读取 API Key(参数 > 环境变量 > .env)
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
$key = Resolve-ApiKey -Name 'ALIYUN_BAILIAN_API_KEY' -EnvPath $envPath
if (-not $key) {
    throw "ALIYUN_BAILIAN_API_KEY 未配置或仍为占位符"
}

# 若 .env 配置了 CAPTION_MODEL 且调用方未显式指定,则用 .env 值
if (-not $PSBoundParameters.ContainsKey('Model')) {
    $envModel = Get-EnvVar -EnvPath $envPath -Name 'CAPTION_MODEL'
    if ($envModel -and -not (Test-IsPlaceholder -Value $envModel)) {
        $Model = $envModel
    }
}

if (-not (Test-Path -LiteralPath $ImagePath)) {
    throw "图片不存在: $ImagePath"
}

$systemPrompt = @'
你是一名资料整理助手。请仔细观察图片，并用中文详细描述图片内容。
要求：
1. 如果是文字/海报/截图/菜单，请提取全部可见文字，并说明排版重点。
2. 如果是图表/数据图/仪表盘，请说明数据趋势、关键数字和结论。
3. 如果是照片/场景截图，请描述场景、人物、物体和其中文字。
4. 输出纯文本段落，不要 Markdown 标题或代码块，便于后续检索。
'@

$userPrompt = '请详细描述这张图片的内容。'

try {
    $contentArr = ConvertTo-MultimodalContent -ImagePaths @($ImagePath) -UserPrompt $userPrompt

    $body = @{
        model    = $Model
        messages = @(
            @{ role = "system"; content = $systemPrompt },
            @{ role = "user";   content = $contentArr }
        )
        max_tokens = $MaxTokens
    } | ConvertTo-Json -Depth 12 -Compress

    $headers = @{ "Authorization" = "Bearer $key" }
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    $resp = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -Body $bodyBytes `
              -ContentType "application/json; charset=utf-8" -TimeoutSec 120 -UseBasicParsing

    if ($resp.StatusCode -ne 200) {
        throw "Vision API HTTP $($resp.StatusCode): $($resp.Content)"
    }

    $j = (Read-ResponseAsUtf8 -Response $resp) | ConvertFrom-Json
    $caption = $j.choices[0].message.content
    if (-not $caption) {
        throw "Vision API 返回空描述"
    }
    Write-Output $caption
} catch {
    $code = ""
    $body = ""
    if ($_.Exception.Response) {
        $code = [int]$_.Exception.Response.StatusCode
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $body = $reader.ReadToEnd()
        $reader.Close()
    }
    throw "图片描述生成失败($code): $body $($_.Exception.Message)"
}

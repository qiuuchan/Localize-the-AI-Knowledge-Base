<#
.SYNOPSIS
  KB-AI · 批量图片入库(M3c):扫描目录 → 调 Qwen3.6-Plus 视觉描述 → 写入 Qdrant 向量库

.DESCRIPTION
  ### 流程
    1. 扫描 -InputDir 下所有图片(.jpg/.jpeg/.png/.webp/.bmp/.gif,递归)
    2. 按 -BatchSize 分批(默认 5 张/批,Qwen 单次多模态上限)
    3. 调 chat.ps1 -VisionOnly -ImagePaths <paths> -Question <描述提示>
       → 拿到中文描述文本(200-500 字)
    4. 用 embed-and-ingest 模式:文本 → embedding → 写 Qdrant collection(默认 kb_ai_images)
    5. 进度条 + 失败降级(单图失败不阻塞整批)

  ### 设计要点
    - 复用 image-prep.ps1 的 Compress-Image(chat.ps1 内部调用,这里不需要直接调)
    - 复用 embed-and-ingest.ps1 的 Qwen3-Embedding API(同一函数 inline 复用)
    - 复用 chat.ps1 的 VisionOnly 模式(跳过 RAG,直接生成描述)
    - 幂等性:Qdrant point id = sha256(image_path),重复跑不重复入库

  ### 失败处理
    - 单张图片读取失败 → WARN 跳过,继续下一张
    - chat.ps1 调用失败(超时/API 限流) → WARN 跳过该批,继续下一批
    - Qdrant 写入失败 → throw(整批失败;用户需手动重跑)

.PARAMETER InputDir
  必填:图片所在目录(支持递归扫描)。

.PARAMETER Collection
  可选:Qdrant collection 名称(默认 kb_ai_images,与文本 kb_ai_chunks 分离)。

.PARAMETER QdrantUrl
  可选:Qdrant REST 根地址(默认 http://localhost:6333)。

.PARAMETER ApiKey
  可选:阿里云百炼 API Key;缺省从 .env 读。

.PARAMETER BatchSize
  可选:每批图片数(默认 5;Qwen 多模态单次上限约 8,M3c 留 buffer)。

.PARAMETER VisionPrompt
  可选:图片描述提示词(默认中文,描述菜品/场景/文字信息便于检索)。

.PARAMETER EmbedBatchSize
  可选:每次 embedding 的文本数(默认 10,Qwen3 限制)。

.PARAMETER WriteBatchSize
  可选:每次 Qdrant upsert 的 point 数(默认 100)。

.PARAMETER DryRun
  开关:只扫描 + 打印图片清单,不实际调 API / 写 Qdrant。

.EXAMPLE
  # 入库 D:\photos\menu 下的所有菜单图
  pwsh -File scripts/batch-images.ps1 -InputDir "D:\photos\menu"

  # DryRun(只看不传)
  pwsh -File scripts/batch-images.ps1 -InputDir "D:\photos\menu" -DryRun

.NOTES
  PowerShell 5.1 兼容。UTF-8 无 BOM。
  chat.ps1 必须存在并支持 -VisionOnly -ImagePaths 参数(M3c)。
  image-prep.ps1 由 chat.ps1 自动 dot-source,无需本脚本显式引用。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$InputDir,
    [string]$Collection = "kb_ai_images",
    [string]$QdrantUrl = "http://localhost:6333",
    [string]$ApiKey,
    # 修复 2.8:BatchSize 默认 5 → 1(每图单独描述)。
    # 原共享描述会让同批 5 张图各分到相同描述,无法区分哪项信息属于哪张图。
    # 接受性能回归(每图多 1 次 Qwen 调用)换正确性。manifest 跳过(按 mtime + size)待补
    [ValidateRange(1, 8)] [int]$BatchSize = 1,
    [string]$VisionPrompt = "请用中文详细描述这张图片。提取关键信息用于检索:菜品名称、食材、烹饪方式、份量、文字内容(如菜单/价格/活动)。控制在 300-500 字。",
    [ValidateRange(1, 10)] [int]$EmbedBatchSize = 10,
    [ValidateRange(1, 100)] [int]$WriteBatchSize = 100,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $Msg" -ForegroundColor Red }

# ----------------------------------------------------------------------
# 路径解析 + 依赖加载
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'get-usb-root.ps1')
$rootDir = Get-UsbRoot
$envPath = Join-Path $rootDir ".env"

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
$resolvedKey = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -Explicit $ApiKey -EnvPath $envPath
if (-not $resolvedKey -and -not $DryRun) {
    Write-Err "未提供 -ApiKey,且 .env 中 ALIYUN_BAILIAN_API_KEY 未填或仍是占位符"
    Write-Err "请编辑 $envPath 填入真实 Key,或传 -ApiKey 参数"
    exit 1
}
if ($resolvedKey) {
    $ApiKey = $resolvedKey
    Write-Step "API Key 加载完成(长度=$($ApiKey.Length))"
}

$chatScript = Join-Path $PSScriptRoot 'chat.ps1'
if (-not (Test-Path -LiteralPath $chatScript)) {
    Write-Err "找不到 chat.ps1: $chatScript(M3c 必须)"
    exit 1
}

# 解析 InputDir(支持相对路径)
if (-not [System.IO.Path]::IsPathRooted($InputDir)) {
    $InputDir = Join-Path $rootDir $InputDir
}
if (-not (Test-Path -LiteralPath $InputDir)) {
    Write-Err "找不到输入目录: $InputDir"
    exit 1
}

# ----------------------------------------------------------------------
# 1. 扫描图片
# ----------------------------------------------------------------------

Write-Step "扫描目录: $InputDir"
$includeExt = @('*.jpg', '*.jpeg', '*.png', '*.webp', '*.bmp', '*.gif')
$imgs = Get-ChildItem -Path $InputDir -Include $includeExt -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 0 } |
        Sort-Object FullName

Write-Step "找到 $($imgs.Count) 张图片"
if ($imgs.Count -eq 0) {
    Write-Warn "目录下没有图片,退出"
    exit 0
}

if ($DryRun) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "  DryRun:待入库图片清单(不会调 API)" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
    foreach ($img in $imgs) {
        $rel = $img.FullName.Substring($InputDir.Length).TrimStart('\', '/')
        $sizeMB = "{0:N2}" -f ($img.Length / 1MB)
        Write-Host ("  [{0,7} MB] {1}" -f $sizeMB, $rel) -ForegroundColor Gray
    }
    exit 0
}

# ----------------------------------------------------------------------
# 2. 分批调 chat.ps1 VisionOnly 模式生成描述
# ----------------------------------------------------------------------

function Get-Sha256Short {
    param([string]$Text, [int]$Len = 32)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = $sha.ComputeHash($bytes)
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $hash) { [void]$sb.Append($b.ToString("x2")) }
    return $sb.ToString().Substring(0, $Len)
}

# 修复 3.2:删除未使用的 Format-PathsArg 函数(从未被调用,且若调用则 -replace '\\', '\\' 未转义双引号,存在命令注入向量)
# function Format-PathsArg { ... } — 已删除

$results = New-Object System.Collections.Generic.List[object]
$failures = 0
$totalBatches = [Math]::Ceiling($imgs.Count / [double]$BatchSize)

for ($b = 0; $b -lt $imgs.Count; $b += $BatchSize) {
    $end = [Math]::Min($b + $BatchSize, $imgs.Count)
    $batch = $imgs[$b..($end - 1)]
    $batchPaths = @($batch | ForEach-Object { $_.FullName })

    $batchIdx = [Math]::Floor($b / $BatchSize) + 1
    Write-Step "[批 $batchIdx/$totalBatches] $($batch.Count) 张图片"

    # 调 chat.ps1
    $tmpOut = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(),
        "kb_ai_batch_" + [System.IO.Path]::GetRandomFileName() + ".json")
    try {
        # OutputJson 模式 → 写到文件,避免长 base64 污染 stdout
        $args = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $chatScript,
            "-Question", $VisionPrompt,
            "-VisionOnly",
            "-OutputJson"
        )
        foreach ($p in $batchPaths) { $args += @("-ImagePaths", $p) }

        $proc = Start-Process -FilePath "powershell" -ArgumentList $args `
                    -Wait -PassThru -NoNewWindow -RedirectStandardOutput $tmpOut
        if ($proc.ExitCode -ne 0) {
            throw "chat.ps1 exit $($proc.ExitCode)"
        }

        $content = Get-Content $tmpOut -Raw -Encoding UTF8
        if (-not $content) { throw "chat.ps1 输出为空" }
        # JSON 可能在 [STEP]/[WARN] 日志后,从第一个 { 截取
        $jsonStart = $content.IndexOf('{')
        if ($jsonStart -lt 0) { throw "找不到 JSON 起始 {:$content" }
        $jsonText = $content.Substring($jsonStart).Trim()
        $resp = $jsonText | ConvertFrom-Json -ErrorAction Stop
        $desc = [string]$resp.content
        if (-not $desc) { throw "返回 content 为空:$jsonText" }

        # 给 batch 里的每张图各生成一条 chunk(共享同一条描述)
        foreach ($p in $batchPaths) {
            $imgFile = Get-Item -LiteralPath $p
            $rel = $imgFile.FullName.Substring($InputDir.Length).TrimStart('\', '/')
            [void]$results.Add(@{
                image_path = $imgFile.FullName
                source     = "image://" + $rel
                text       = "[图片:$rel] " + $desc
                meta       = @{
                    source_file = $imgFile.FullName
                    image_bytes = $imgFile.Length
                    image_mtime = $imgFile.LastWriteTime.ToString("o")
                    section     = "image"
                }
            })
        }
        Write-Step "  → 描述 OK(长度=$($desc.Length))"
    } catch {
        Write-Warn "  → 批次失败,跳过 $($batch.Count) 张图:$($_.Exception.Message)"
        $failures += $batch.Count
    } finally {
        Remove-Item $tmpOut -Force -ErrorAction SilentlyContinue
    }
}

Write-Step ""
Write-Step "描述生成完成:$($results.Count) 条,失败 $failures 张"
if ($results.Count -eq 0) {
    Write-Err "没有成功描述的图片,无法入库"
    exit 1
}

# ----------------------------------------------------------------------
# 3. Embedding + 写 Qdrant(复用 embed-and-ingest 模式)
# ----------------------------------------------------------------------

function Invoke-QwenEmbedding {
    param(
        [string[]]$Texts,
        [string]$Key
    )
    $url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    $body = @{
        model = "text-embedding-v3"
        input = @{ texts = $Texts }
        parameters = @{ dimension = 1024 }
    } | ConvertTo-Json -Depth 6 -Compress
    $headers = @{
        "Authorization" = "Bearer $Key"
        "Content-Type"  = "application/json"
    }
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -Body $body `
                  -TimeoutSec 60 -UseBasicParsing
        if ($resp.StatusCode -ne 200) {
            throw "Embedding HTTP $($resp.StatusCode): $($resp.Content)"
        }
        $j = $resp.Content | ConvertFrom-Json
        $vecs = @()
        foreach ($e in $j.output.embeddings) { $vecs += ,@($e.embedding) }
        return $vecs
    } catch {
        $code = ""
        $body = ""
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $body = $reader.ReadToEnd()
            $reader.Close()
        }
        # 修复 3.1:throw 前 redact Bearer token
        $body = Redact-Bearer -Text $body
        throw "Embedding 调用失败($code): $body"
    }
}

function Test-QdrantReachable {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri "$Url/health" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Ensure-QdrantCollection {
    param([string]$Url, [string]$Name, [int]$Dim = 1024)
    try {
        $r = Invoke-WebRequest -Uri "$Url/collections/$Name" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Step "Collection 已存在: $Name"
            return
        }
    } catch { }
    $body = @{
        name = $Name
        vectors = @{ size = $Dim; distance = "Cosine" }
    } | ConvertTo-Json
    $headers = @{ "Content-Type" = "application/json" }
    try {
        $resp = Invoke-WebRequest -Uri "$Url/collections/$Name" -Method Put `
                  -Headers $headers -Body $body -TimeoutSec 30 -UseBasicParsing
        if ($resp.StatusCode -in 200, 201) {
            Write-Step "创建 collection: $Name(dim=$Dim)"
        } else {
            throw "创建失败 HTTP $($resp.StatusCode): $($resp.Content)"
        }
    } catch {
        throw "Qdrant 创建 collection 失败: $($_.Exception.Message)"
    }
}

function Send-QdrantPoints {
    param(
        [string]$Url,
        [string]$Name,
        [array]$Points
    )
    $body = @{ points = $Points } | ConvertTo-Json -Depth 12 -Compress
    $headers = @{ "Content-Type" = "application/json" }
    $resp = Invoke-WebRequest -Uri "$Url/collections/$Name/points" -Method Post `
              -Headers $headers -Body $body -TimeoutSec 60 -UseBasicParsing
    if ($resp.StatusCode -in 200, 201) { return $true }
    throw "Qdrant upsert HTTP $($resp.StatusCode): $($resp.Content)"
}

# 检查 Qdrant 可达
if (-not (Test-QdrantReachable -Url $QdrantUrl)) {
    Write-Err "Qdrant 不可达: $QdrantUrl"
    Write-Err "请先双击 start.bat 启动 docker compose(Qdrant 容器)"
    exit 1
}
Ensure-QdrantCollection -Url $QdrantUrl -Name $Collection -Dim 1024

# Embedding + 写库
$writeBatch = New-Object System.Collections.Generic.List[object]
$doneCount = 0
for ($start = 0; $start -lt $results.Count; $start += $EmbedBatchSize) {
    $end = [Math]::Min($start + $EmbedBatchSize, $results.Count)
    $slice = $results[$start..($end - 1)]
    $texts = @($slice | ForEach-Object { $_.text })

    Write-Step "Embedding [$($start + 1)..$end]/$($results.Count)"
    try {
        $vecs = Invoke-QwenEmbedding -Texts $texts -Key $ApiKey
    } catch {
        Write-Err "Embedding 批次失败:$($_.Exception.Message)"
        throw
    }

    if ($vecs.Count -ne $slice.Count) {
        throw "Embedding 返回向量数 ($($vecs.Count)) 与请求数 ($($slice.Count)) 不一致"
    }

    for ($k = 0; $k -lt $slice.Count; $k++) {
        $item = $slice[$k]
        $pid = Get-Sha256Short $item.source
        $point = @{
            id      = $pid
            vector  = $vecs[$k]
            payload = @{
                text        = $item.text
                source      = $item.source
                source_file = $item.meta.source_file
                image_bytes = $item.meta.image_bytes
                image_mtime = $item.meta.image_mtime
                section     = $item.meta.section
            }
        }
        [void]$writeBatch.Add($point)
    }
    $doneCount += $slice.Count

    if ($writeBatch.Count -ge $WriteBatchSize) {
        Send-QdrantPoints -Url $QdrantUrl -Name $Collection -Points @($writeBatch) | Out-Null
        Write-Step "  → 写入 Qdrant: $($writeBatch.Count) points(累计 $doneCount/$($results.Count))"
        $writeBatch.Clear()
    }
}

if ($writeBatch.Count -gt 0) {
    Send-QdrantPoints -Url $QdrantUrl -Name $Collection -Points @($writeBatch) | Out-Null
    Write-Step "  → 写入 Qdrant: $($writeBatch.Count) points(累计 $doneCount/$($results.Count))"
    $writeBatch.Clear()
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  批量入库完成:$($results.Count) 张图 → collection '$Collection'" -ForegroundColor Green
if ($failures -gt 0) {
    Write-Host "  失败:$failures 张(已跳过)" -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Green
exit 0
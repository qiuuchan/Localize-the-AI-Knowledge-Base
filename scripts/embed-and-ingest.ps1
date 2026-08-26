<#
.SYNOPSIS
  读取 chunks.jsonl → 调 Qwen3-Embedding API → 批量写入 Qdrant(6333 REST)。

.DESCRIPTION
  - chunks 来源:parse-doc.ps1 输出的 <doc-id>\chunks.jsonl
  - embedding 模型:text-embedding-v3(阿里云百炼 qwen3-embedding 兼容 id),dimension 1024
  - Qdrant 端口:6333(HTTP REST),不用 6334 gRPC(简化 PS 调用)
  - 批大小:embed 一次最多 10 chunks;Qdrant 一次 write 最多 100 points
  - 幂等性:point id = sha256(source|chunk_index),重复跑不重复入库
  - 找不到 Qdrant 时给出清晰提示,不静默失败

.PARAMETER ChunksFile
  必填:parse-doc.ps1 输出的 chunks.jsonl 绝对路径。

.PARAMETER Collection
  必填:Qdrant collection 名称(默认 kb_ai_chunks)。

.PARAMETER QdrantUrl
  可选:Qdrant REST 根地址;缺省 http://localhost:6333。

.PARAMETER ApiKey
  可选:阿里云百炼 API Key;缺省从 .env 读 ALIYUN_BAILIAN_API_KEY。

.PARAMETER EmbedBatchSize
  可选:每次调 embedding API 的 chunk 数(≤10,Qwen3 限制)。

.PARAMETER WriteBatchSize
  可选:每次 upsert 到 Qdrant 的 point 数(≤100,U 盘 SSD 友好)。

.EXAMPLE
  pwsh -File scripts/embed-and-ingest.ps1 `
       -ChunksFile "<private>\KB-AI\cache\parsed\abc123\chunks.jsonl" `
       -Collection "kb_ai_chunks"

.NOTES
  PowerShell 7+ 兼容(utf8NoBOM 编码输出)。
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]  [string]$ChunksFile,
    [Parameter(Mandatory = $true)]  [string]$Collection,
    [string]$QdrantUrl = "http://localhost:6333",
    [string]$ApiKey,
    [ValidateRange(1, 10)]  [int]$EmbedBatchSize = 10,
    [ValidateRange(1, 100)] [int]$WriteBatchSize = 100,
    [switch]$SkipCache = $false,    # T-RAG-1: 强制跳过 embedding cache 重 embed
    [string]$CacheFile = "",         # T-RAG-1: 自定义 cache 路径,默认 $rootDir/data/embedding-cache.jsonl
    [switch]$SkipKeywordIndex = $false,  # v0.7.2: 跳过 SQLite 关键词索引写入
    [string]$DbPath = "",            # v0.7.2: SQLite db 路径,默认 $rootDir/data/db.sqlite
    [ValidateRange(1, 36500)] [double]$TemporalHalfLifeDays = 365, # v0.8.2: 时间加权半衰期(天)
    [string]$ManifestFile = ""       # v0.8.2: 输出 source_file -> point_ids 映射,供批量清理旧点
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# ----------------------------------------------------------------------
# 公共库(v0.7.1 抽离):日志 / .env / UTF-8 写入 / SHA256 短哈希
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'lib/load-env.ps1')
. (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')
. (Join-Path $PSScriptRoot 'lib/Tokenizer.ps1')
. (Join-Path $PSScriptRoot 'lib/Invoke-SqliteExec.ps1')

# ----------------------------------------------------------------------
# 加载 .env(若未传 ApiKey)
# ----------------------------------------------------------------------

if (-not $ApiKey) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $rootDir = Split-Path -Parent $scriptDir
    $envPath = Join-Path $rootDir ".env"
    $k = Get-EnvVar -EnvPath $envPath -Name "ALIYUN_BAILIAN_API_KEY"
    # 修复 2.1:用公共库 Test-IsPlaceholder 统一占位符识别
    if ($k -and -not (Test-IsPlaceholder -Value $k)) {
        $ApiKey = $k
        Write-Step "从 .env 读取 ALIYUN_BAILIAN_API_KEY(长度=$($ApiKey.Length))"
    } else {
        Write-Err "未提供 -ApiKey,且 .env 中 ALIYUN_BAILIAN_API_KEY 未填或仍是占位符"
        Write-Err "请编辑 $envPath 填入真实 Key,或传 -ApiKey 参数"
        exit 1
    }
}

# ----------------------------------------------------------------------
# v0.8.2: 时间加权辅助函数
# ----------------------------------------------------------------------

# 允许 .env 覆盖半衰期(参数优先级最高)
$envHalfLife = Get-EnvVar -EnvPath (Join-Path (Split-Path -Parent $PSScriptRoot) ".env") -Name "TEMPORAL_HALF_LIFE_DAYS"
if ($envHalfLife) {
    try {
        $hl = [double]::Parse($envHalfLife)
        if ($hl -gt 0) { $TemporalHalfLifeDays = $hl }
    } catch {}
}

function Get-TemporalWeight {
    <#
    .SYNOPSIS  根据 days_old 计算时间衰减权重
    .PARAMETER DaysOld
      距今天数
    .PARAMETER HalfLife
      半衰期(天),默认 $TemporalHalfLifeDays
    #>
    param(
        [int]$DaysOld,
        [double]$HalfLife = $TemporalHalfLifeDays
    )
    if ($HalfLife -le 0) { return 1.0 }
    # 指数衰减:新资料权重接近 1,旧资料逐步衰减但不低于 0.1
    $w = [math]::Exp(-$DaysOld / $HalfLife)
    if ($w -lt 0.1) { $w = 0.1 }
    return [math]::Round($w, 6)
}

# ----------------------------------------------------------------------
# 读 chunks.jsonl
# ----------------------------------------------------------------------

if (-not (Test-Path $ChunksFile)) {
    Write-Err "找不到 chunks 文件: $ChunksFile"
    exit 1
}
$lines = Get-Content -Path $ChunksFile -Encoding UTF8
# 修复 2.5:用 List[object] 替代 @() 数组,避免 += 的 O(N²) 数组复制(N=10K 时 5 千万次元素复制)
$chunks = New-Object System.Collections.Generic.List[object]
foreach ($ln in $lines) {
    if ([string]::IsNullOrWhiteSpace($ln)) { continue }
    $j = $ln | ConvertFrom-Json
    [void]$chunks.Add($j)
}
Write-Step "载入 $($chunks.Count) chunks"

if ($chunks.Count -eq 0) {
    Write-Err "chunks 文件为空,无需入库"
    exit 1
}

# ----------------------------------------------------------------------
# T-RAG-1: Embedding cache(本地去重,长期省一半 embedding 费用)
# ----------------------------------------------------------------------

# 解析 CacheFile 路径(默认 $rootDir/data/embedding-cache.jsonl)
if (-not $CacheFile) {
    $scriptDirForCache = Split-Path -Parent $MyInvocation.MyCommand.Path
    $rootDirForCache = Split-Path -Parent $scriptDirForCache
    $CacheFile = Join-Path $rootDirForCache "data/embedding-cache.jsonl"
}
$cacheDir = Split-Path -Parent $CacheFile
if (-not (Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
}

# v0.7.2: 解析 DbPath(默认 $rootDir/data/db.sqlite)
if (-not $DbPath) {
    $scriptDirForDb = Split-Path -Parent $MyInvocation.MyCommand.Path
    $rootDirForDb = Split-Path -Parent $scriptDirForDb
    $DbPath = Join-Path $rootDirForDb "data/db.sqlite"
}
$dbDir = Split-Path -Parent $DbPath
if (-not (Test-Path $dbDir)) {
    New-Item -ItemType Directory -Force -Path $dbDir | Out-Null
}

# 加载 cache 到 hashtable(text → vector)
function Get-EmbeddingCache {
    param([string]$Path)
    $cache = @{}
    if (-not (Test-Path $Path)) { return $cache }
    try {
        Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
            if ([string]::IsNullOrWhiteSpace($_)) { return }
            try {
                $j = $_ | ConvertFrom-Json
                if ($j.text -and $j.vector) {
                    $cache[$j.text] = @($j.vector)
                }
            } catch {
                # 损坏行跳过(配合 v1 锁版的 §6 风险缓解:cache 损坏自动重建)
            }
        }
    } catch {
        Write-Warn "cache 文件读取失败,自动重建: $Path"
    }
    return $cache
}

# 写入一条 cache entry(text + vector)
function Add-EmbeddingCache {
    param([string]$Path, [string]$Text, [array]$Vector)
    $entry = @{
        text   = $Text
        vector = $Vector
        ts     = (Get-Date).ToString("o")
        model  = "text-embedding-v3"
    } | ConvertTo-Json -Compress -Depth 6
    Add-Utf8NoBomLine -Path $Path -Line $entry
}

# ----------------------------------------------------------------------
# Qwen3-Embedding API(qwen3-embedding 走 text-embedding-v3 id,1024 维)
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
    } | ConvertTo-Json -Depth 6
    $headers = @{
        "Authorization" = "Bearer $Key"
    }
    # v0.7.2: PowerShell 5.1 默认用 ANSI 发送 string body,中文会乱码;必须转 UTF-8 byte[]
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -Body $bodyBytes `
                 -ContentType "application/json; charset=utf-8" -TimeoutSec 60 -UseBasicParsing
        if ($resp.StatusCode -ne 200) {
            throw "Embedding API 返回 HTTP $($resp.StatusCode): $($resp.Content)"
        }
        $j = (Read-ResponseAsUtf8 -Response $resp) | ConvertFrom-Json
        # 响应:output.embeddings[*].embedding
        $vecs = @()
        foreach ($e in $j.output.embeddings) {
            $vecs += ,@($e.embedding)
        }
        # v0.7.2: 强制返回 array-of-arrays,防止单条 embedding 被 PowerShell 解包成标量
        return ,$vecs
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
        throw "Embedding 调用失败($code): $body $_"
    }
}

# ----------------------------------------------------------------------
# Qdrant REST API
# ----------------------------------------------------------------------

function Test-QdrantReachable {
    param([string]$Url)
    try {
        # v0.7.2: Qdrant v1.7.0 健康端点是 /(返回 200 + 版本信息),/health 返回 404
        $r = Invoke-WebRequest -Uri "$Url/" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Ensure-QdrantCollection {
    param([string]$Url, [string]$Name, [int]$Dim = 1024)
    # GET /collections/{name}
    try {
        $r = Invoke-WebRequest -Uri "$Url/collections/$Name" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Step "Collection 已存在: $Name"
            return
        }
    } catch {
        # 404 = 不存在 → 创建
    }
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
    $body = @{ points = $Points } | ConvertTo-Json -Depth 10
    # v0.7.2: PowerShell 5.1 默认用 ANSI 发送 string body,中文会乱码;必须转 UTF-8 byte[]
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    # v0.7.2:Qdrant v1.7.0 upsert 用 PUT /collections/{name}/points,POST 是 retrieve-by-ids
    $resp = Invoke-WebRequest -Uri "$Url/collections/$Name/points" -Method Put `
             -ContentType "application/json; charset=utf-8" -Body $bodyBytes -TimeoutSec 60 -UseBasicParsing
    if ($resp.StatusCode -in 200, 201) {
        return $true
    } else {
        throw "Qdrant upsert HTTP $($resp.StatusCode): $($resp.Content)"
    }
}

# v0.7.2: SQLite 关键词索引初始化
function Initialize-KeywordIndex {
    param([string]$DbPath)
    Invoke-SqliteExec -DbPath $DbPath -Sql @"
CREATE TABLE IF NOT EXISTS keyword_index (
    word TEXT NOT NULL,
    point_id TEXT NOT NULL,
    source TEXT,
    text TEXT,
    PRIMARY KEY (word, point_id)
);
CREATE INDEX IF NOT EXISTS idx_keyword_word ON keyword_index(word);
"@
}

# v0.7.2: 批量写入 keyword_index(失败只 warn,不中断主流程)
function Send-KeywordIndexRows {
    param(
        [string]$DbPath,
        [System.Collections.Generic.List[object]]$Rows,
        [int]$BatchSize
    )
    if ($Rows.Count -eq 0) { return }
    for ($i = 0; $i -lt $Rows.Count; $i += $BatchSize) {
        $slice = $Rows.GetRange($i, [Math]::Min($BatchSize, $Rows.Count - $i))
        $placeholders = ($slice | ForEach-Object { "(?,?,?,?)" }) -join ","
        $flatParams = New-Object System.Collections.ArrayList
        foreach ($row in $slice) {
            [void]$flatParams.Add($row[0])
            [void]$flatParams.Add($row[1])
            [void]$flatParams.Add($row[2])
            [void]$flatParams.Add($row[3])
        }
        Invoke-SqliteExec -DbPath $DbPath `
            -Sql "INSERT OR REPLACE INTO keyword_index(word, point_id, source, text) VALUES $placeholders" `
            -Params $flatParams.ToArray() | Out-Null
    }
}

# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

# 1. 校验 Qdrant 可达
if (-not (Test-QdrantReachable -Url $QdrantUrl)) {
    Write-Err "Qdrant 不可达: $QdrantUrl"
    Write-Err "请先双击 start.bat 启动 docker compose(Qdrant 容器)"
    exit 1
}

# 2. 确保 collection 存在
Ensure-QdrantCollection -Url $QdrantUrl -Name $Collection -Dim 1024

# v0.7.2: 确保 SQLite 关键词索引表存在
if (-not $SkipKeywordIndex) {
    Initialize-KeywordIndex -DbPath $DbPath
}

# 3. embedding + 入库(含 T-RAG-1 cache)
$totalChunks = $chunks.Count
$doneChunks = 0
$writeBatch = New-Object System.Collections.Generic.List[object]
$keywordRows = New-Object System.Collections.Generic.List[object]   # v0.7.2
$cacheHits = 0
$cacheMisses = 0
$manifest = @{}  # v0.8.2: source_file -> point_id[]

# 加载 cache(T-RAG-1)
if ($SkipCache) {
    Write-Step "T-RAG-1: -SkipCache 启用,跳过 cache"
    $cache = @{}
} else {
    $cache = Get-EmbeddingCache -Path $CacheFile
    Write-Step "T-RAG-1: 已加载 embedding cache,$($cache.Count) 条 (cache file: $CacheFile)"
}

function Flush-WriteBatch {
    param(
        [string]$QdrantUrl,
        [string]$Collection,
        [System.Collections.Generic.List[object]]$Batch,
        [int]$WriteBatchSize,
        [string]$DbPath,
        [System.Collections.Generic.List[object]]$KeywordRows,
        [switch]$SkipKeywordIndex
    )
    if ($Batch.Count -eq 0) { return }
    # 按 WriteBatchSize 切片
    for ($i = 0; $i -lt $Batch.Count; $i += $WriteBatchSize) {
        $slice = $Batch.GetRange($i, [Math]::Min($WriteBatchSize, $Batch.Count - $i))
        Send-QdrantPoints -Url $QdrantUrl -Name $Collection -Points $slice
        Write-Step "  → 写入 Qdrant: $($slice.Count) points(累计 $([Math]::Min($i + $WriteBatchSize, $Batch.Count))/$($Batch.Count))"
    }
    # v0.7.2: 同步写入 keyword_index(失败只 warn,不中断主流程)
    if (-not $SkipKeywordIndex -and $KeywordRows -and $KeywordRows.Count -gt 0 -and $DbPath) {
        try {
            Send-KeywordIndexRows -DbPath $DbPath -Rows $KeywordRows -BatchSize $WriteBatchSize
            Write-Step "  → 写入 keyword_index: $($KeywordRows.Count) 行"
        } catch {
            Write-Warn "keyword_index 写入失败(不影响 Qdrant): $_"
        }
        $KeywordRows.Clear()
    }
    $Batch.Clear()
}

for ($start = 0; $start -lt $totalChunks; $start += $EmbedBatchSize) {
    $end = [Math]::Min($start + $EmbedBatchSize, $totalChunks)
    $slice = $chunks[$start..($end - 1)]
    $texts = @($slice | ForEach-Object { $_.text })

    # T-RAG-7: 防御性截断,embedding API 单条上限 8192(阿里云报错阈值)
    $maxEmbedLen = 8000
    for ($ti = 0; $ti -lt $texts.Count; $ti++) {
        if ($texts[$ti].Length -gt $maxEmbedLen) {
            Write-Warn "chunk 文本过长($($texts[$ti].Length) > $maxEmbedLen),截断后嵌入: source=$($slice[$ti].source)"
            $texts[$ti] = $texts[$ti].Substring(0, $maxEmbedLen)
            $slice[$ti].text = $texts[$ti]
        }
    }

    # T-RAG-1: 区分 cache hit / miss
    $textsToFetch = @()
    $fetchIndices = @()
    for ($t = 0; $t -lt $texts.Count; $t++) {
        if (-not $SkipCache -and $cache.ContainsKey($texts[$t])) {
            $cacheHits++
        } else {
            $textsToFetch += $texts[$t]
            $fetchIndices += $t
        }
    }
    # 修复 2.7:cacheMisses 累计(原 = 赋值被下一批覆盖,90% 命中率被误报为 47%)
    $cacheMisses += $textsToFetch.Count

    # 仅对 cache miss 调 API
    $apiVecs = @()
    if ($textsToFetch.Count -gt 0) {
        Write-Step "Embedding chunks [$($start + 1)..$end]/$totalChunks (cache: hit=$cacheHits, miss=$cacheMisses)"
        try {
            $apiVecs = Invoke-QwenEmbedding -Texts $textsToFetch -Key $ApiKey
        } catch {
            Write-Err "Embedding 批次失败:$($_.Exception.Message)"
            throw
        }
        # 写回 cache
        if (-not $SkipCache) {
            for ($i = 0; $i -lt $apiVecs.Count; $i++) {
                Add-EmbeddingCache -Path $CacheFile -Text $textsToFetch[$i] -Vector $apiVecs[$i]
                # 修复 2.7:同步更新内存 cache(避免同批/下批相同文本再次调 API)
                $cache[$textsToFetch[$i]] = $apiVecs[$i]
            }
        }
    } else {
        Write-Step "Embedding chunks [$($start + 1)..$end]/$totalChunks (全部 cache 命中,跳过 API)"
    }

    # 合并 cache + API 结果,按原顺序组装 vecs
    $vecs = @()
    $apiIdx = 0
    for ($t = 0; $t -lt $texts.Count; $t++) {
        if (-not $SkipCache -and $cache.ContainsKey($texts[$t])) {
            $vecs += ,@($cache[$texts[$t]])
        } else {
            $vecs += ,@($apiVecs[$apiIdx])
            $apiIdx++
        }
    }

    if ($vecs.Count -ne $slice.Count) {
        throw "Embedding 返回向量数 ($($vecs.Count)) 与请求数 ($($slice.Count)) 不一致"
    }

    for ($k = 0; $k -lt $slice.Count; $k++) {
        $c = $slice[$k]
        # 修复 2.6:point ID 改用内容哈希(source + text),而非位置哈希(start + k)。
        # 位置哈希导致:文档头部插入新 chunk 后,后续所有 chunk 位置改变,产生近 N 个新 ID,旧 ID 残留
        # v0.7.2:Qdrant v1.7.0 只接受 integer/UUID 格式 point id,把 32 位内容哈希转成 UUID
        $pointId = Format-AsUuid -Hex (Get-Sha256Short "$($c.source)|$($c.text)")
        $daysOld = if ($c.meta.days_old -ne $null) { [int]$c.meta.days_old } else { 0 }
        $temporalWeight = Get-TemporalWeight -DaysOld $daysOld
        $srcFile = $c.meta.source_file
        $point = @{
            id      = $pointId
            vector  = $vecs[$k]
            payload = @{
                text             = $c.text
                source           = $c.source
                source_file      = $srcFile
                section          = $c.meta.section
                header_path      = ($c.meta.header_path)
                title            = ($c.meta.title)
                date             = ($c.meta.date)
                days_old         = $daysOld
                temporal_weight  = $temporalWeight
                doc_source       = ($c.meta.doc_source)
                doc_type         = ($c.meta.doc_type)
                tags             = ($c.meta.tags)
                chunk_type       = ($c.meta.chunk_type)
                certainty        = ($c.meta.certainty)
            }
        }
        [void]$writeBatch.Add($point)
        # v0.8.2: 收集 manifest
        if (-not $manifest.ContainsKey($srcFile)) { $manifest[$srcFile] = New-Object System.Collections.Generic.List[string] }
        [void]$manifest[$srcFile].Add($pointId)


        # v0.7.2: 收集关键词倒排行
        if (-not $SkipKeywordIndex) {
            $tokens = Get-Tokens -Text $c.text
            foreach ($tok in $tokens) {
                [void]$keywordRows.Add(@($tok, $pointId, $c.source, $c.text))
            }
        }
    }
    $doneChunks += $slice.Count

    # 写一批
    if ($writeBatch.Count -ge $WriteBatchSize) {
        Flush-WriteBatch -QdrantUrl $QdrantUrl -Collection $Collection `
                         -Batch $writeBatch -WriteBatchSize $WriteBatchSize `
                         -DbPath $DbPath -KeywordRows $keywordRows -SkipKeywordIndex:$SkipKeywordIndex
    }
}

# 收尾
if ($writeBatch.Count -gt 0) {
    Flush-WriteBatch -QdrantUrl $QdrantUrl -Collection $Collection `
                     -Batch $writeBatch -WriteBatchSize $WriteBatchSize `
                     -DbPath $DbPath -KeywordRows $keywordRows -SkipKeywordIndex:$SkipKeywordIndex
}

Write-Host ""
# v0.7.2: 统计 keyword_index 总行数(用于验证)
$keywordTotal = 0
if (-not $SkipKeywordIndex -and $DbPath -and (Test-Path $DbPath)) {
    try {
        $kwStat = Invoke-SqliteExec -DbPath $DbPath -Sql "SELECT COUNT(*) AS cnt FROM keyword_index"
        if ($kwStat -and $kwStat.cnt) { $keywordTotal = [int]$kwStat.cnt }
    } catch {
        # 统计失败不影响主流程
    }
}

# v0.8.2: 写入/更新 manifest(source_file -> point_ids)
if ($ManifestFile) {
    try {
        $manifestObj = @{
            collection = $Collection
            updatedAt  = (Get-Date).ToString("o")
            sources    = @{}
        }
        if (Test-Path $ManifestFile) {
            $existing = Get-Content $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existing.sources) {
                foreach ($k in $existing.sources.PSObject.Properties.Name) {
                    $manifestObj.sources[$k] = $existing.sources.$k
                }
            }
        }
        foreach ($k in $manifest.Keys) {
            $manifestObj.sources[$k] = @($manifest[$k])
        }
        $manifestDir = Split-Path -Parent $ManifestFile
        if (-not (Test-Path $manifestDir)) { New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null }
        $manifestObj | ConvertTo-Json -Depth 5 | Set-Content -Path $ManifestFile -Encoding UTF8
        Write-Step "更新 manifest: $($manifest.Count) 个 source → $ManifestFile"
    } catch {
        Write-Warn "manifest 写入失败(不影响入库): $_"
    }
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "  入库完成:$totalChunks chunks → collection '$Collection'" -ForegroundColor Green
Write-Host "  T-RAG-1 cache 统计:hit=$cacheHits, miss=$cacheMisses, hit_rate=$([math]::Round($cacheHits / [Math]::Max(1, $cacheHits + $cacheMisses) * 100, 1))%" -ForegroundColor Green
if (-not $SkipKeywordIndex) {
    Write-Host "  keyword_index 统计:累计 $keywordTotal 行" -ForegroundColor Green
}
Write-Host "============================================================" -ForegroundColor Green
exit 0